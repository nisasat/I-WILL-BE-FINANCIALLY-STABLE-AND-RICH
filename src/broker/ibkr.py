"""Thin ib_insync wrapper for IBKR connection, contracts, and orders.

Requires TWS or IB Gateway running locally. Always validate against a paper
account (port 7497 / 4002) before pointing at live.
"""

import logging

logger = logging.getLogger("bot.ibkr")


class IBKRClient:
    def __init__(self, host: str = "127.0.0.1", port: int = 7497, client_id: int = 1):
        from ib_insync import IB  # imported lazily so backtests don't need it

        self.ib = IB()
        self.host = host
        self.port = port
        self.client_id = client_id
        self._contracts: dict[str, object] = {}

    def connect(self) -> None:
        self.ib.connect(self.host, self.port, clientId=self.client_id)
        logger.info("connected to IBKR %s:%s (client %s)", self.host, self.port, self.client_id)

    def disconnect(self) -> None:
        if self.ib.isConnected():
            self.ib.disconnect()

    def contract(self, symbol: str):
        """Qualified continuous-front-month future for 'NQ' or 'ES' (CME)."""
        if symbol not in self._contracts:
            from ib_insync import ContFuture

            cont = ContFuture(symbol, exchange="CME", currency="USD")
            (qualified,) = self.ib.qualifyContracts(cont)
            self._contracts[symbol] = qualified
        return self._contracts[symbol]

    def daily_bars(self, symbol: str, lookback_days: int = 180):
        """Daily historical bars as a DataFrame (RTH only)."""
        from ib_insync import util

        bars = self.ib.reqHistoricalData(
            self.contract(symbol),
            endDateTime="",
            durationStr=f"{lookback_days} D",
            barSizeSetting="1 day",
            whatToShow="TRADES",
            useRTH=True,
        )
        df = util.df(bars)
        if df is None or df.empty:
            raise RuntimeError(f"no historical bars returned for {symbol}")
        return df.set_index("date")[["open", "high", "low", "close", "volume"]]

    def market_order(self, symbol: str, size: int):
        """Place a market order; positive size buys, negative sells. Blocks until done."""
        from ib_insync import MarketOrder

        action = "BUY" if size > 0 else "SELL"
        order = MarketOrder(action, abs(size))
        trade = self.ib.placeOrder(self.contract(symbol), order)
        while not trade.isDone():
            self.ib.waitOnUpdate(timeout=10)
        logger.info("%s %s x%d -> %s", action, symbol, abs(size), trade.orderStatus.status)
        return trade

    def position(self, symbol: str) -> int:
        for pos in self.ib.positions():
            if pos.contract.symbol == symbol:
                return int(pos.position)
        return 0
