"""A single-symbol limit order book matched on price-time priority."""
from __future__ import annotations

import heapq
from collections import deque
from typing import Deque, Dict, List, Optional, Tuple

from .models import Order, OrderStatus, OrderType, Side, Trade


class OrderBook:
    """Maintains resting bids/asks for one symbol and matches incoming orders.

    Bids are kept in a max-heap (by negating price) and asks in a min-heap,
    so the best price on each side is always at the top. Within a price
    level, orders are stored in a FIFO deque, giving strict price-time
    priority: better prices trade first, and among equal prices, the order
    that arrived first trades first.
    """

    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self._bid_prices: List[float] = []  # heap of negated prices (max-heap)
        self._ask_prices: List[float] = []  # heap of prices (min-heap)
        self._bids: Dict[float, Deque[Order]] = {}
        self._asks: Dict[float, Deque[Order]] = {}
        self._orders: Dict[int, Order] = {}  # resting order id -> Order

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def submit(self, order: Order) -> List[Trade]:
        """Match an incoming order against the book, resting any remainder."""
        if order.symbol != self.symbol:
            raise ValueError(f"Order symbol {order.symbol!r} does not match book {self.symbol!r}")

        trades = self._match(order)

        if order.remaining > 0:
            if order.order_type == OrderType.LIMIT:
                self._rest(order)
            else:
                # Unfilled market order quantity has no price to rest at.
                order.status = OrderStatus.CANCELLED

        return trades

    def cancel(self, order_id: int) -> bool:
        """Remove a resting order from the book. Returns False if not found."""
        order = self._orders.get(order_id)
        if order is None:
            return False

        book = self._bids if order.side == Side.BUY else self._asks
        level = book.get(order.price)
        if level is not None:
            try:
                level.remove(order)
            except ValueError:
                pass
            if not level:
                del book[order.price]

        order.status = OrderStatus.CANCELLED
        del self._orders[order_id]
        return True

    def best_bid(self) -> Optional[float]:
        self._clean(self._bid_prices, self._bids, negate=True)
        return -self._bid_prices[0] if self._bid_prices else None

    def best_ask(self) -> Optional[float]:
        self._clean(self._ask_prices, self._asks, negate=False)
        return self._ask_prices[0] if self._ask_prices else None

    def spread(self) -> Optional[float]:
        bid, ask = self.best_bid(), self.best_ask()
        if bid is None or ask is None:
            return None
        return ask - bid

    def depth(self, levels: int = 5) -> Dict[str, List[Tuple[float, float]]]:
        """Top `levels` price levels per side as (price, total quantity)."""
        bid_prices = sorted(self._bids.keys(), reverse=True)[:levels]
        ask_prices = sorted(self._asks.keys())[:levels]
        return {
            "bids": [(p, sum(o.remaining for o in self._bids[p])) for p in bid_prices],
            "asks": [(p, sum(o.remaining for o in self._asks[p])) for p in ask_prices],
        }

    def get_order(self, order_id: int) -> Optional[Order]:
        return self._orders.get(order_id)

    # ------------------------------------------------------------------ #
    # Internals
    # ------------------------------------------------------------------ #
    def _rest(self, order: Order) -> None:
        book = self._bids if order.side == Side.BUY else self._asks
        heap = self._bid_prices if order.side == Side.BUY else self._ask_prices
        key = -order.price if order.side == Side.BUY else order.price

        if order.price not in book:
            book[order.price] = deque()
            heapq.heappush(heap, key)
        book[order.price].append(order)
        self._orders[order.id] = order

    def _match(self, incoming: Order) -> List[Trade]:
        trades: List[Trade] = []
        is_buy = incoming.side == Side.BUY
        opposite_book = self._asks if is_buy else self._bids
        opposite_heap = self._ask_prices if is_buy else self._bid_prices
        negate = not is_buy  # the bid heap stores negated prices

        while incoming.remaining > 0:
            self._clean(opposite_heap, opposite_book, negate=negate)
            if not opposite_heap:
                break

            best_price = -opposite_heap[0] if negate else opposite_heap[0]

            if incoming.order_type == OrderType.LIMIT:
                crosses = (
                    incoming.price >= best_price if is_buy else incoming.price <= best_price
                )
                if not crosses:
                    break

            level = opposite_book[best_price]
            resting = level[0]  # oldest order at this price level

            fill_qty = min(incoming.remaining, resting.remaining)
            incoming.remaining -= fill_qty
            resting.remaining -= fill_qty

            buy_id = incoming.id if is_buy else resting.id
            sell_id = resting.id if is_buy else incoming.id
            trades.append(
                Trade(
                    symbol=self.symbol,
                    price=best_price,
                    quantity=fill_qty,
                    buy_order_id=buy_id,
                    sell_order_id=sell_id,
                )
            )

            if resting.remaining == 0:
                resting.status = OrderStatus.FILLED
                level.popleft()
                del self._orders[resting.id]
                if not level:
                    del opposite_book[best_price]
            else:
                resting.status = OrderStatus.PARTIALLY_FILLED

        if incoming.remaining == 0:
            incoming.status = OrderStatus.FILLED
        elif incoming.remaining < incoming.quantity:
            incoming.status = OrderStatus.PARTIALLY_FILLED

        return trades

    @staticmethod
    def _clean(heap: List[float], book: Dict[float, Deque[Order]], negate: bool) -> None:
        """Drop stale heap entries whose price level has become empty."""
        while heap:
            price = -heap[0] if negate else heap[0]
            if price in book and book[price]:
                break
            heapq.heappop(heap)
