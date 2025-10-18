from app.orderbook import OrderBookEngine
from app.persistence import restore_from_snapshot, replay_wal, WAL_PATH, SNAPSHOT_PATH
import json, os, sys

print("SNAPSHOT PATH:", SNAPSHOT_PATH)
print("WAL PATH:", WAL_PATH)
print("---- snapshot file exists? ----", os.path.exists(SNAPSHOT_PATH))
print("---- wal file exists? ----", os.path.exists(WAL_PATH))

e = OrderBookEngine()
print("\n>>> After new engine created: orders =", len(e.orders), "trades =", len(e.trades))

# load snapshot
restore_from_snapshot(e)
print(">>> After restore_from_snapshot: orders =", len(e.orders), "trades =", len(e.trades))
if len(e.orders) > 0:
    print("Sample order ids from snapshot:", list(e.orders.keys())[:5])

# replay wal
applied = replay_wal(e)
print(">>> replay_wal returned:", applied)
print(">>> After replay_wal: orders =", len(e.orders), "trades =", len(e.trades))
if len(e.orders) > 0:
    for oid, o in list(e.orders.items())[:10]:
        print(" order:", oid, "price_cents:", o.price_cents, "remaining:", o.remaining_qty, "alive:", o.alive)

# print wal content for extra visibility
print("\n---- WAL CONTENT (first 10 lines) ----")
if os.path.exists(WAL_PATH):
    with open(WAL_PATH, "r", encoding="utf8") as f:
        for i, line in enumerate(f):
            if i >= 10: break
            print(line.strip())
else:
    print("(no wal)")

# print snapshot content briefly
print("\n---- SNAPSHOT CONTENT ----")
if os.path.exists(SNAPSHOT_PATH):
    with open(SNAPSHOT_PATH, "r", encoding="utf8") as f:
        try:
            j = json.load(f)
            print(json.dumps(j, indent=2)[:1000])
        except Exception as ex:
            print("snapshot read error:", ex)
else:
    print("(no snapshot)")
