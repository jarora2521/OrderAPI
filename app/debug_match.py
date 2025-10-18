from app.orderbook import OrderBookEngine
from app.persistence import restore_from_snapshot, replay_wal, rebuild_heaps
import json, sys

e = OrderBookEngine()
restore_from_snapshot(e)
replayed = replay_wal(e)
rebuild_heaps(e)

print("Replayed events:", replayed)
print("Trades BEFORE matching:", len(e.trades))

# run the matcher on PROD1
e._match_product("PROD1")

print("Trades AFTER matching:", len(e.trades))
for t in e.trades:
    print(json.dumps({
        "trade_id": t.trade_id,
        "timestamp": t.timestamp,
        "price": t.price_cents/100.0,
        "qty": t.qty,
        "buy_order_id": t.buy_order_id,
        "sell_order_id": t.sell_order_id
    }))
