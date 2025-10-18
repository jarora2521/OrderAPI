import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
import uvicorn
from typing import Dict, Any
import requests
import threading
import time

from app.orderbook import OrderBookEngine
from app.persistence import (
    append_event,
    restore_from_snapshot,
    write_snapshot,
    replay_wal,
    rebuild_heaps,
)

# matcher service endpoint: prefer env var so containers can talk by service name
# locally defaults to 127.0.0.1:9000, in docker-compose we'll set MATCHER_URL to "http://matcher:9000/events"
MATCHER_URL = os.getenv("MATCHER_URL", "http://127.0.0.1:9000/events")

def _send_event_to_matcher(event: dict):
    """Send event to matcher in background (fire-and-forget)."""
    def _worker(ev):
        try:
            # short timeout so it won't block the API for long
            requests.post(MATCHER_URL, json=ev, timeout=1.0)
        except Exception:
            # ignore network errors for now
            pass

    t = threading.Thread(target=_worker, args=(event,), daemon=True)
    t.start()


app = FastAPI(title="OrderAPI")

# serve the demo static UI at /web (so you can open http://127.0.0.1:8000/web/index.html)
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

# allow browser access (helps when testing from file or other origins)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# mount the web/ directory
app.mount("/web", StaticFiles(directory="web"), name="web")


# single engine instance for this simple project
engine = OrderBookEngine()

# trade queue: used to broadcast new trades to websocket clients
trade_queue: asyncio.Queue = asyncio.Queue()

# helper to push new trades into queue after operations
def _enqueue_new_trades(old_len: int):
    # put any new trades since old_len into the queue
    for t in engine.trades[old_len:]:
        payload = {
            "trade_id": t.trade_id,
            "execution_timestamp": t.timestamp,
            "price": engine._from_cents(t.price_cents),
            "qty": t.qty,
            "bid_order_id": t.buy_order_id,
            "ask_order_id": t.sell_order_id,
        }
        try:
            trade_queue.put_nowait(payload)
        except asyncio.QueueFull:
            # if queue full, drop (simple behavior)
            pass

# ---------------- Startup: restore, replay, rebuild, match, persist trades ----------------
restore_from_snapshot(engine)
replayed = replay_wal(engine)
rebuild_heaps(engine)
print(f"✅ Replayed {replayed} WAL events on startup (heaps rebuilt).")

# run the matcher once for each product so restored crossable orders trade
old_len = len(engine.trades)
for pid in list(engine.buy_heaps.keys()):
    engine._match_product(pid)

# enqueue new trades to websockets and persist them to WAL
_enqueue_new_trades(old_len)
for t in engine.trades[old_len:]:
    append_event({
        "type": "trade",
        "ts": t.timestamp,
        "trade": {
            "trade_id": t.trade_id,
            "price_cents": t.price_cents,
            "price": engine._from_cents(t.price_cents),
            "qty": t.qty,
            "buy_order_id": t.buy_order_id,
            "sell_order_id": t.sell_order_id,
            "timestamp": t.timestamp
        }
    })

# ------------------- REST endpoints -------------------

@app.post("/orders")
async def place_order(payload: Dict[str, Any]):
    """
    body: { product_id: str, side: 1|-1, price: float, qty: int }
    returns: { order_id: str }
    """
    try:
        product_id = payload["product_id"]
        side = int(payload["side"])
        price = float(payload["price"])
        qty = int(payload["qty"])
    except Exception:
        raise HTTPException(status_code=400, detail="invalid payload")

    old_len = len(engine.trades)
    oid = engine.place_order(product_id, side, price, qty)

    # persist the place event to WAL
    append_event({
        "type": "place",
        "ts": time.time(),
        "order": {
            "order_id": oid,
            "product_id": product_id,
            "side": side,
            "price": price,
            "qty": qty
        }
    })

    # forward event to matcher service (non-blocking)
    _send_event_to_matcher({"type":"place", "order": {"order_id": oid, "product_id": product_id, "side": side, "price": price, "qty": qty}})

    # enqueue any new trades for websocket broadcasting
    _enqueue_new_trades(old_len)

    # persist new trades to WAL as well
    for t in engine.trades[old_len:]:
        append_event({
            "type": "trade",
            "ts": t.timestamp,
            "trade": {
                "trade_id": t.trade_id,
                "price_cents": t.price_cents,
                "price": engine._from_cents(t.price_cents),
                "qty": t.qty,
                "buy_order_id": t.buy_order_id,
                "sell_order_id": t.sell_order_id,
                "timestamp": t.timestamp
            }
        })

    return {"order_id": oid}

@app.put("/orders/{order_id}")
async def modify_order(order_id: str, payload: Dict[str, Any]):
    """
    body: { price: float }
    """
    if "price" not in payload:
        raise HTTPException(status_code=400, detail="missing price")

    # record trades length before modifying (modification can trigger matching)
    old_len = len(engine.trades)
    success = engine.modify_order(order_id, float(payload["price"]))

    # persist modify event to WAL
    append_event({
        "type": "modify",
        "ts": time.time(),
        "order_id": order_id,
        "new_price": float(payload["price"])
    })

    # forward modify to matcher service (non-blocking)
    _send_event_to_matcher({"type":"modify", "order_id": order_id, "new_price": float(payload["price"])})

    # enqueue any new trades and persist them
    _enqueue_new_trades(old_len)
    for t in engine.trades[old_len:]:
        append_event({
            "type": "trade",
            "ts": t.timestamp,
            "trade": {
                "trade_id": t.trade_id,
                "price_cents": t.price_cents,
                "price": engine._from_cents(t.price_cents),
                "qty": t.qty,
                "buy_order_id": t.buy_order_id,
                "sell_order_id": t.sell_order_id,
                "timestamp": t.timestamp
            }
        })

    return {"success": bool(success)}

@app.delete("/orders/{order_id}")
async def cancel_order(order_id: str):
    # record trades length before cancel (cancel does not create trades normally)
    success = engine.cancel_order(order_id)

    # persist cancel event to WAL
    append_event({
        "type": "cancel",
        "ts": time.time(),
        "order_id": order_id
    })

    # forward cancel to matcher service (non-blocking)
    _send_event_to_matcher({"type":"cancel", "order_id": order_id})

    return {"success": bool(success)}

@app.get("/orders/{order_id}")
async def get_order(order_id: str):
    o = engine.fetch_order(order_id)
    if o is None:
        raise HTTPException(status_code=404, detail="order not found")
    return o

@app.get("/orders")
async def get_all_orders():
    return engine.list_orders()

@app.get("/trades")
async def get_trades():
    return engine.list_trades()

# ------------------- WebSocket endpoints -------------------

# simple trade broadcaster websocket
@app.websocket("/ws/trades")
async def ws_trades(ws: WebSocket):
    await ws.accept()
    try:
        while True:
            payload = await trade_queue.get()
            await ws.send_json(payload)
    except WebSocketDisconnect:
        return

# orderbook snapshot websocket per product: sends 5-level snapshot every second
@app.websocket("/ws/book/{product_id}")
async def ws_book_snapshot(ws: WebSocket, product_id: str):
    await ws.accept()
    try:
        while True:
            snap = engine.get_orderbook_snapshot(product_id, depth=5)
            await ws.send_json(snap)
            await asyncio.sleep(1.0)
    except WebSocketDisconnect:
        return

# ------------------- quick health route -------------------
@app.get("/health")
async def health():
    return {"status": "ok"}

if __name__ == "__main__":
    # run with: python -m app.main OR uvicorn app.main:app --reload
    uvicorn.run("app.main:app", host="127.0.0.1", port=8000, reload=True)

# ---------------- Snapshot background task ----------------
SNAPSHOT_INTERVAL = 30  # seconds

async def _snapshot_loop():
    # background loop to persist a snapshot periodically
    while True:
        try:
            write_snapshot(engine)
        except Exception:
            # ignore snapshot errors for now
            pass
        await asyncio.sleep(SNAPSHOT_INTERVAL)

@app.on_event("startup")
async def _startup_tasks():
    # start the snapshot background task when FastAPI starts
    asyncio.create_task(_snapshot_loop())
