import heapq
import time
import uuid
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional

# Simple order & trade dataclasses
@dataclass
class Order:
    order_id: str
    product_id: str
    side: int            # 1 for buy, -1 for sell
    price_cents: int     # price stored as integer cents
    qty: int
    remaining_qty: int
    timestamp: float
    version: int = 1
    alive: bool = True
    executed_qty: int = 0
    executed_value_cents: int = 0  # sum(price_cents * qty) for executed portion

@dataclass
class Trade:
    trade_id: str
    timestamp: float
    price_cents: int
    qty: int
    buy_order_id: str
    sell_order_id: str

class OrderBookEngine:
    def __init__(self):
        # heaps per product: product_id -> heap list
        # buy heap is max-heap implemented with negative price
        self.buy_heaps: Dict[str, List[Tuple[int, float, str, int]]] = {}
        self.sell_heaps: Dict[str, List[Tuple[int, float, str, int]]] = {}

        # master order map and trades
        self.orders: Dict[str, Order] = {}
        self.trades: List[Trade] = []

    # --- utilities ---
    def _ensure_product(self, product_id: str):
        if product_id not in self.buy_heaps:
            self.buy_heaps[product_id] = []
            self.sell_heaps[product_id] = []

    def _to_cents(self, price: float) -> int:
        return int(round(price * 100))

    def _from_cents(self, cents: int) -> float:
        return cents / 100.0

    def _now(self) -> float:
        return time.time()

    def _next_order_id(self) -> str:
        return str(uuid.uuid4())

    def _next_trade_id(self) -> str:
        return str(uuid.uuid4())

    # --- core API ---
    def place_order(self, product_id: str, side: int, price: float, qty: int) -> str:
        """
        Place a limit order. Returns order_id.
        """
        assert side in (1, -1)
        assert qty > 0
        assert price > 0

        self._ensure_product(product_id)
        order_id = self._next_order_id()
        price_cents = self._to_cents(price)
        ts = self._now()
        order = Order(
            order_id=order_id,
            product_id=product_id,
            side=side,
            price_cents=price_cents,
            qty=qty,
            remaining_qty=qty,
            timestamp=ts
        )
        self.orders[order_id] = order

        # push to heap
        if side == 1:
            # buy heap: use negative price for max-heap
            heapq.heappush(self.buy_heaps[product_id], (-price_cents, order.timestamp, order_id, order.version))
        else:
            # sell heap: min-heap by price
            heapq.heappush(self.sell_heaps[product_id], (price_cents, order.timestamp, order_id, order.version))

        # attempt to match as much as possible for this product
        self._match_product(product_id)
        return order_id

    def modify_order(self, order_id: str, new_price: float) -> bool:
        """
        Modify price of an active order. Uses lazy update via versioning:
        increments version and pushes new heap entry with updated price.
        """
        if order_id not in self.orders:
            return False
        order = self.orders[order_id]
        if not order.alive or order.remaining_qty <= 0:
            return False

        # update order price and bump version
        new_price_cents = self._to_cents(new_price)
        order.price_cents = new_price_cents
        order.version += 1
        order.timestamp = self._now()  # update timestamp so modified order is treated as newer
        product_id = order.product_id

        # push updated entry into the appropriate heap
        if order.side == 1:
            heapq.heappush(self.buy_heaps[product_id], (-order.price_cents, order.timestamp, order_id, order.version))
        else:
            heapq.heappush(self.sell_heaps[product_id], (order.price_cents, order.timestamp, order_id, order.version))

        # try matching, modification may allow immediate match
        self._match_product(product_id)
        return True

    def cancel_order(self, order_id: str) -> bool:
        """
        Cancel an order: mark inactive and zero remaining quantity.
        Lazy deletion will skip heap entries for old versions.
        """
        if order_id not in self.orders:
            return False
        order = self.orders[order_id]
        if not order.alive or order.remaining_qty <= 0:
            return False
        order.alive = False
        order.version += 1
        order.remaining_qty = 0
        return True

    def fetch_order(self, order_id: str) -> Optional[Dict]:
        """
        Return order details per spec: order_price, order_quantity,
        average_traded_price, traded_quantity, order_alive.
        """
        if order_id not in self.orders:
            return None
        o = self.orders[order_id]
        avg_price = 0.0
        if o.executed_qty > 0:
            avg_price = self._from_cents(o.executed_value_cents // o.executed_qty)
        return {
            "order_id": o.order_id,
            "product_id": o.product_id,
            "order_price": self._from_cents(o.price_cents),
            "order_quantity": o.qty,
            "average_traded_price": avg_price,
            "traded_quantity": o.executed_qty,
            "order_alive": bool(o.alive and o.remaining_qty > 0)
        }

    def list_orders(self) -> List[Dict]:
        out = []
        for o in self.orders.values():
            out.append(self.fetch_order(o.order_id))
        return out

    def list_trades(self) -> List[Dict]:
        out = []
        for t in self.trades:
            out.append({
                "trade_id": t.trade_id,
                "execution_timestamp": t.timestamp,
                "price": self._from_cents(t.price_cents),
                "qty": t.qty,
                "bid_order_id": t.buy_order_id,
                "ask_order_id": t.sell_order_id
            })
        return out

    # --- matching logic ---
    def _pop_valid_buy(self, product_id: str) -> Optional[Order]:
        heap = self.buy_heaps[product_id]
        while heap:
            neg_price, ts, oid, ver = heap[0]
            heapq.heappop(heap)
            if oid not in self.orders:
                continue
            o = self.orders[oid]
            # valid if version matches and still alive and has remaining qty
            if o.version == ver and o.alive and o.remaining_qty > 0:
                return o
            # otherwise skip (lazy deletion)
        return None

    def _pop_valid_sell(self, product_id: str) -> Optional[Order]:
        heap = self.sell_heaps[product_id]
        while heap:
            price, ts, oid, ver = heap[0]
            heapq.heappop(heap)
            if oid not in self.orders:
                continue
            o = self.orders[oid]
            if o.version == ver and o.alive and o.remaining_qty > 0:
                return o
        return None

    def _peek_valid_buy(self, product_id: str) -> Optional[Order]:
        heap = self.buy_heaps[product_id]
        while heap:
            neg_price, ts, oid, ver = heap[0]
            o = self.orders.get(oid)
            if o and o.version == ver and o.alive and o.remaining_qty > 0:
                return o
            # pop stale entry
            heapq.heappop(heap)
        return None

    def _peek_valid_sell(self, product_id: str) -> Optional[Order]:
        heap = self.sell_heaps[product_id]
        while heap:
            price, ts, oid, ver = heap[0]
            o = self.orders.get(oid)
            if o and o.version == ver and o.alive and o.remaining_qty > 0:
                return o
            heapq.heappop(heap)
        return None

    def _match_product(self, product_id: str):
        """
        Repeatedly match top-of-book buy and sell while they cross.
        Trade price is the maker (resting) order's price: whichever order has earlier timestamp.
        """
        self._ensure_product(product_id)
        while True:
            best_buy = self._peek_valid_buy(product_id)
            best_sell = self._peek_valid_sell(product_id)
            if not best_buy or not best_sell:
                break
            # buy price and sell price in cents
            buy_p = best_buy.price_cents
            sell_p = best_sell.price_cents
            if buy_p < sell_p:
                break  # no match
            # we have a match
            # determine maker (resting) by timestamp: earlier timestamp is resting
            if best_buy.timestamp <= best_sell.timestamp:
                # buy was resting, so trade price = buy price (maker)
                trade_price = best_buy.price_cents
            else:
                trade_price = best_sell.price_cents

            trade_qty = min(best_buy.remaining_qty, best_sell.remaining_qty)
            trade = Trade(
                trade_id=self._next_trade_id(),
                timestamp=self._now(),
                price_cents=trade_price,
                qty=trade_qty,
                buy_order_id=best_buy.order_id,
                sell_order_id=best_sell.order_id
            )
            self.trades.append(trade)

            # update orders executed quantities and remaining qty
            # buyer
            best_buy.executed_qty += trade_qty
            best_buy.executed_value_cents += trade_qty * trade_price
            best_buy.remaining_qty -= trade_qty
            if best_buy.remaining_qty <= 0:
                best_buy.alive = False

            # seller
            best_sell.executed_qty += trade_qty
            best_sell.executed_value_cents += trade_qty * trade_price
            best_sell.remaining_qty -= trade_qty
            if best_sell.remaining_qty <= 0:
                best_sell.alive = False

            # After updating, we popped nothing from heaps here (we only peeked).
            # To remove exhausted orders from top entries we pop them by calling pop helpers:
            if best_buy.remaining_qty <= 0:
                # pop valid buy (which will remove the matching heap entry)
                self._pop_valid_buy(product_id)

            if best_sell.remaining_qty <= 0:
                self._pop_valid_sell(product_id)

            # Note: if both still have remaining >0 (shouldn't happen because trade_qty is min),
            # we continue the loop. Otherwise matching continues until no cross.

    # --- snapshot helper: top N levels, aggregated by price ---
    def get_orderbook_snapshot(self, product_id: str, depth: int = 5) -> Dict:
        """
        Returns top 'depth' levels for bids and asks as lists of {price, quantity}.
        Aggregates remaining_qty per price level.
        """
        self._ensure_product(product_id)
        bids: Dict[int, int] = {}
        asks: Dict[int, int] = {}
        # iterate over active orders for the product and aggregate
        for o in self.orders.values():
            if o.product_id != product_id:
                continue
            if not o.alive or o.remaining_qty <= 0:
                continue
            if o.side == 1:
                bids[o.price_cents] = bids.get(o.price_cents, 0) + o.remaining_qty
            else:
                asks[o.price_cents] = asks.get(o.price_cents, 0) + o.remaining_qty

        # prepare top levels
        top_bids = sorted(bids.items(), key=lambda x: -x[0])[:depth]
        top_asks = sorted(asks.items(), key=lambda x: x[0])[:depth]

        return {
            "bids": [{"price": self._from_cents(p), "qty": q} for p, q in top_bids],
            "asks": [{"price": self._from_cents(p), "qty": q} for p, q in top_asks],
            "timestamp": self._now()
        }

# If you want to test the engine quickly from REPL:
# from app.orderbook import OrderBookEngine
# e = OrderBookEngine()
# id1 = e.place_order("PROD1", 1, 120.0, 5)   # buy 5 @ 120
# id2 = e.place_order("PROD1", -1, 115.0, 3)  # sell 3 @ 115 -> should match 3
# print(e.list_trades())
