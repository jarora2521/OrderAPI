import os, sys, time
# make local service files importable (services/matcher)
HERE = os.path.dirname(__file__)
sys.path.insert(0, HERE)

from fastapi import FastAPI, HTTPException
import uvicorn
from typing import Dict, Any

# import local engine + persistence (these were copied into this folder)
from orderbook import OrderBookEngine
from persistence import append_event, write_snapshot, restore_from_snapshot, replay_wal, rebuild_heaps

app = FastAPI(title="MatcherService")

# single engine instance for this matcher process
engine = OrderBookEngine()

# restore state and replay WAL if present, rebuild heaps
restore_from_snapshot(engine)
replayed = replay_wal(engine)
rebuild_heaps(engine)

@app.post("/events")
def ingest_event(ev: Dict[str, Any]):
    """
    Accepts events produced by API service (place/modify/cancel) in the same simple JSON
    format used by the app persistence. Returns simple status.
    Example:
      {"type":"place", "order": {...}}
      {"type":"modify", "order_id": "...", "new_price": 120.0}
      {"type":"cancel", "order_id":"..."}
    """
    et = ev.get("type")
    if et == "place":
        od = ev.get("order", {})
        pid = od.get("product_id")
        side = int(od.get("side", 0))
        price = float(od.get("price", 0.0))
        qty = int(od.get("qty", 0))
        if not pid or side not in (1, -1) or qty <= 0:
            raise HTTPException(status_code=400, detail="invalid place payload")
        oid = engine.place_order(pid, side, price, qty)
        # persist and return id
        append_event({"type":"place","ts":time.time(),"order":{"order_id":oid,"product_id":pid,"side":side,"price":price,"qty":qty}})
        return {"status":"ok","order_id":oid}
    elif et == "modify":
        oid = ev.get("order_id")
        new_price = float(ev.get("new_price", 0.0))
        ok = engine.modify_order(oid, new_price)
        append_event({"type":"modify","ts":time.time(),"order_id":oid,"new_price":new_price})
        return {"status":"ok","success": bool(ok)}
    elif et == "cancel":
        oid = ev.get("order_id")
        ok = engine.cancel_order(oid)
        append_event({"type":"cancel","ts":time.time(),"order_id":oid})
        return {"status":"ok","success": bool(ok)}
    else:
        raise HTTPException(status_code=400, detail="unknown event type")

@app.get("/orders")
def list_orders():
    return engine.list_orders()

@app.get("/trades")
def list_trades():
    return engine.list_trades()

@app.get("/health")
def health():
    return {"status":"ok"}

if __name__ == "__main__":
    # run with: python services/matcher/main.py
    uvicorn.run("services.matcher.main:app", host="0.0.0.0", port=9000, reload=False)
