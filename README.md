# Order Matching Engine

A simple price-time priority order matching engine in pure Python (no dependencies).

## Features

- Limit and market orders, on the buy or sell side
- Price-time priority matching (best price first; FIFO within a price level)
- Partial fills, order resting, and cancellation
- Multiple independent order books, keyed by symbol
- Book depth snapshots (`best_bid`, `best_ask`, `spread`, `depth`)
- A stream of execution events: every `Trade` is immutable (frozen), appended
  to an engine-wide, queryable log, and broadcast to live subscribers

## Structure

```
matching_engine/
  models.py      Order, Trade, Side, OrderType, OrderStatus
  order_book.py  OrderBook — matching logic for a single symbol
  engine.py      MatchingEngine — routes orders to the right OrderBook
demo.py          Runnable walkthrough of typical usage
test_engine.py   Unit tests (unittest)
```

## Usage

```python
from matching_engine import MatchingEngine, Order, OrderType, Side

engine = MatchingEngine()

# Rest a sell limit order on the book
engine.submit_order(Order(side=Side.SELL, order_type=OrderType.LIMIT, price=101, quantity=5, symbol="BTC-USD"))

# A crossing buy order matches against it and returns the resulting trades
trades = engine.submit_order(Order(side=Side.BUY, order_type=OrderType.LIMIT, price=101, quantity=2, symbol="BTC-USD"))

# Market orders match against the best available price(s); any unfilled
# remainder is cancelled rather than resting on the book
engine.submit_order(Order(side=Side.BUY, order_type=OrderType.MARKET, quantity=10, symbol="BTC-USD"))

# Cancel a resting order by id
engine.cancel_order("BTC-USD", order_id=1)

# Inspect the book
engine.order_book("BTC-USD").depth(levels=5)

# Subscribe to the live execution stream — called synchronously as trades happen
engine.on_trade(lambda trade: print("executed:", trade))

# Or query the full, ordered trade history later (optionally filtered by symbol)
engine.trade_history(symbol="BTC-USD")
```

## Run it

```bash
python demo.py            # walkthrough demo
python -m unittest test_engine.py -v   # tests
```
