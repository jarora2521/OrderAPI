from app.orderbook import OrderBookEngine

e = OrderBookEngine()
id1 = e.place_order("PROD1", 1, 120.0, 5)
id2 = e.place_order("PROD1", -1, 115.0, 3)
id3 = e.place_order("PROD1", -1, 119.0, 2)

print("Orders:")
for o in e.list_orders():
    print(o)
print("\nTrades:")
for t in e.list_trades():
    print(t)
print("\nSnapshot:")
print(e.get_orderbook_snapshot("PROD1"))
