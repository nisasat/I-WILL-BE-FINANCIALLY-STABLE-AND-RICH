"""Shared strategy base class."""

import logging

import backtrader as bt


class BaseStrategy(bt.Strategy):
    """Base class with logging and order/trade bookkeeping."""

    def __init__(self):
        self.logger = logging.getLogger(f"bot.strategy.{type(self).__name__}")
        self.trade_pnls: list[float] = []

    def log(self, msg: str) -> None:
        dt = self.datas[0].datetime.date(0)
        self.logger.info("%s %s", dt.isoformat(), msg)

    def notify_order(self, order: bt.Order) -> None:
        if order.status in (order.Completed,):
            side = "BUY" if order.isbuy() else "SELL"
            self.log(
                f"{side} {order.data._name} x{order.executed.size:+.0f} "
                f"@ {order.executed.price:.2f}"
            )
        elif order.status in (order.Canceled, order.Margin, order.Rejected):
            self.log(f"order {order.getstatusname()} on {order.data._name}")

    def notify_trade(self, trade: bt.Trade) -> None:
        if trade.isclosed:
            self.trade_pnls.append(trade.pnlcomm)
            self.log(f"trade closed {trade.data._name}: pnl={trade.pnlcomm:.2f}")
