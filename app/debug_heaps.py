from app.orderbook import OrderBookEngine
from app.persistence import restore_from_snapshot, replay_wal, rebuild_heaps
import json

e = OrderBookEngine()
restore_from_snapshot(e)
replayed = replay_wal(e)
rebuild_heaps(e)

print("Replayed:", replayed)
print("--- ORDERS ---")
for oid,o in e.orders.items():
    print(f"{oid} | side={o.side} | price={o.price_cents/100:.2f} | rem={o.remaining_qty} | alive={o.alive} | ts={o.timestamp} | ver={o.version}")

print("\n--- BUY HEAPS (per product) ---")
for pid, heap in e.buy_heaps.items():
    print(f"product={pid} | entries={len(heap)}")
    # show top 5
    for i, item in enumerate(sorted(heap)[:5]):
        print(" ", i, item)

print("\n--- SELL HEAPS (per product) ---")
for pid, heap in e.sell_heaps.items():
    print(f"product={pid} | entries={len(heap)}")
    for i, item in enumerate(sorted(heap)[:5]):
        print(" ", i, item)

# peek best (using engine helpers if available)
def peek_buy(pid):
    b = e._peek_valid_buy(pid)
    return None if not b else (b.order_id, b.price_cents/100.0, b.remaining_qty)

def peek_sell(pid):
    s = e._peek_valid_sell(pid)
    return None if not s else (s.order_id, s.price_cents/100.0, s.remaining_qty)

print("\n--- TOP OF BOOK ---")
for pid in set(list(e.buy_heaps.keys()) + list(e.sell_heaps.keys())):
    print(pid, "best_buy:", peek_buy(pid), "best_sell:", peek_sell(pid))

