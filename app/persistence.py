import os
import json
from typing import Any, Dict

DATA_DIR = os.path.join(os.path.dirname(__file__), "..", "data")
WAL_PATH = os.path.join(DATA_DIR, "wal.log")
SNAPSHOT_PATH = os.path.join(DATA_DIR, "snapshot.json")

def _ensure_data_dir():
    os.makedirs(DATA_DIR, exist_ok=True)

def append_event(event: Dict[str, Any]) -> None:
    """
    Append a JSON line to the WAL. Event should be a dict containing at least {"type": "...", "ts": ...}
    Example events: {"type":"place","order":{...}}, {"type":"modify","order_id":"...","new_price":...}, {"type":"trade","trade":{...}}
    """
    _ensure_data_dir()
    with open(WAL_PATH, "a", encoding="utf8") as f:
        f.write(json.dumps(event, ensure_ascii=False) + "\n")

def write_snapshot(engine) -> None:
    """
    Write full snapshot of engine.orders and engine.trades to SNAPSHOT_PATH (overwrites).
    Engine is expected to have 'orders' dict and 'trades' list.
    """
    _ensure_data_dir()
    snapshot = {
        "orders": {},
        "trades": []
    }
    # orders: serialize minimal state for restore
    for oid, o in engine.orders.items():
        snapshot["orders"][oid] = {
            "order_id": o.order_id,
            "product_id": o.product_id,
            "side": o.side,
            "price_cents": o.price_cents,
            "qty": o.qty,
            "remaining_qty": o.remaining_qty,
            "timestamp": o.timestamp,
            "version": o.version,
            "alive": o.alive,
            "executed_qty": o.executed_qty,
            "executed_value_cents": o.executed_value_cents
        }
    # trades
    for t in engine.trades:
        snapshot["trades"].append({
            "trade_id": t.trade_id,
            "timestamp": t.timestamp,
            "price_cents": t.price_cents,
            "qty": t.qty,
            "buy_order_id": t.buy_order_id,
            "sell_order_id": t.sell_order_id
        })
    with open(SNAPSHOT_PATH, "w", encoding="utf8") as f:
        json.dump(snapshot, f, ensure_ascii=False, indent=2)

def restore_from_snapshot(engine) -> None:
    """
    Load snapshot file (if present) and populate engine.orders and engine.trades.
    Note: does not replay WAL yet. We will add WAL replay in a next step.
    """
    if not os.path.exists(SNAPSHOT_PATH):
        return
    with open(SNAPSHOT_PATH, "r", encoding="utf8") as f:
        snapshot = json.load(f)
    engine.orders.clear()
    engine.trades.clear()
    # reconstruct orders
    from app.orderbook import Order, Trade
    for oid, od in snapshot.get("orders", {}).items():
        o = Order(
            order_id=od["order_id"],
            product_id=od["product_id"],
            side=od["side"],
            price_cents=od["price_cents"],
            qty=od["qty"],
            remaining_qty=od.get("remaining_qty", od["qty"]),
            timestamp=od.get("timestamp", 0.0),
            version=od.get("version", 1),
            alive=od.get("alive", True),
            executed_qty=od.get("executed_qty", 0),
            executed_value_cents=od.get("executed_value_cents", 0)
        )
        engine.orders[oid] = o
    # reconstruct trades
    for td in snapshot.get("trades", []):
        t = Trade(
            trade_id=td["trade_id"],
            timestamp=td["timestamp"],
            price_cents=td["price_cents"],
            qty=td["qty"],
            buy_order_id=td["buy_order_id"],
            sell_order_id=td["sell_order_id"]
        )
        engine.trades.append(t)

def replay_wal(engine) -> int:
    """
    Replay WAL (wal.log) onto the given engine.
    Returns number of events applied (approx).
    This function is defensive: it skips duplicate trades and skips placing orders
    if they already exist (so replay is idempotent).
    """
    if not os.path.exists(WAL_PATH):
        return 0

    from app.orderbook import Order, Trade

    applied = 0
    seen_trades = {t.trade_id for t in engine.trades}

    with open(WAL_PATH, "r", encoding="utf8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                ev = json.loads(line)
            except Exception:
                continue

            etype = ev.get("type")
            if etype == "place":
                od = ev.get("order", {})
                oid = od.get("order_id")
                if not oid:
                    continue
                # if order already exists, skip
                if oid in engine.orders:
                    continue
                # construct Order object and insert (minimal fields)
                o = Order(
                    order_id=od["order_id"],
                    product_id=od["product_id"],
                    side=int(od["side"]),
                    price_cents=int(round(float(od["price"]) * 100)),
                    qty=int(od["qty"]),
                    remaining_qty=int(od["qty"]),
                    timestamp=float(ev.get("ts", 0.0)),
                    version=1,
                    alive=True,
                    executed_qty=0,
                    executed_value_cents=0
                )
                engine.orders[o.order_id] = o
                # ensure product heaps exist (we won't push heap entries for replay;
                # heaps are populated lazily by snapshot/peek functions)
                engine._ensure_product(o.product_id)
                applied += 1

            elif etype == "modify":
                oid = ev.get("order_id")
                new_price = ev.get("new_price")
                if not oid or oid not in engine.orders:
                    continue
                try:
                    # update order in place
                    o = engine.orders[oid]
                    o.price_cents = int(round(float(new_price) * 100))
                    o.version = o.version + 1
                    o.timestamp = float(ev.get("ts", o.timestamp))
                    applied += 1
                except Exception:
                    continue

            elif etype == "cancel":
                oid = ev.get("order_id")
                if not oid or oid not in engine.orders:
                    continue
                o = engine.orders[oid]
                if not o.alive:
                    continue
                o.alive = False
                o.remaining_qty = 0
                o.version = o.version + 1
                applied += 1

            elif etype == "trade":
                td = ev.get("trade") or ev.get("trade", {})
                tid = td.get("trade_id")
                if not tid or tid in seen_trades:
                    continue
                # create Trade object and apply to engine
                try:
                    price_cents = int(td.get("price_cents", int(round(float(td.get("price", 0.0)) * 100))))
                    qty = int(td.get("qty", 0))
                    buy_oid = td.get("buy_order_id") or td.get("bid_order_id") or td.get("buy_order_id")
                    sell_oid = td.get("sell_order_id") or td.get("ask_order_id") or td.get("sell_order_id")
                    t = Trade(
                        trade_id=tid,
                        timestamp=float(td.get("timestamp", ev.get("ts", 0.0))),
                        price_cents=price_cents,
                        qty=qty,
                        buy_order_id=buy_oid,
                        sell_order_id=sell_oid
                    )
                    engine.trades.append(t)
                    seen_trades.add(tid)
                    # update buyer/seller order stats if present
                    if buy_oid in engine.orders:
                        bo = engine.orders[buy_oid]
                        bo.executed_qty += qty
                        bo.executed_value_cents += qty * price_cents
                        bo.remaining_qty = max(0, bo.remaining_qty - qty)
                        if bo.remaining_qty == 0:
                            bo.alive = False
                    if sell_oid in engine.orders:
                        so = engine.orders[sell_oid]
                        so.executed_qty += qty
                        so.executed_value_cents += qty * price_cents
                        so.remaining_qty = max(0, so.remaining_qty - qty)
                        if so.remaining_qty == 0:
                            so.alive = False
                    applied += 1
                except Exception:
                    continue

            else:
                # unknown event type -> skip
                continue

    return applied

def rebuild_heaps(engine):
    """
    Rebuild buy_heaps and sell_heaps from engine.orders so the matcher can see resting orders.
    """
    import heapq

    # Ensure the engine has the expected heap maps
    if not hasattr(engine, "buy_heaps"):
        engine.buy_heaps = {}
    if not hasattr(engine, "sell_heaps"):
        engine.sell_heaps = {}

    # Clear existing heaps for all known products
    for pid in list(engine.buy_heaps.keys()):
        engine.buy_heaps[pid].clear()
    for pid in list(engine.sell_heaps.keys()):
        engine.sell_heaps[pid].clear()

    # Ensure product entries exist for every product referenced by orders
    for o in engine.orders.values():
        engine._ensure_product(o.product_id)

    # Push active orders into the appropriate heaps using the same tuple format used by the engine
    # buy heap uses negative price for max-heap and stores ( -price_cents, timestamp, order_id, version )
    # sell heap uses ( price_cents, timestamp, order_id, version )
    for o in engine.orders.values():
        if not o.alive or o.remaining_qty <= 0:
            continue
        if o.side == 1:
            heapq.heappush(engine.buy_heaps[o.product_id], (-o.price_cents, o.timestamp, o.order_id, o.version))
        else:
            heapq.heappush(engine.sell_heaps[o.product_id], (o.price_cents, o.timestamp, o.order_id, o.version))


