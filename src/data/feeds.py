"""Backtrader data feed adapters."""

import backtrader as bt
import pandas as pd


class PandasOHLCV(bt.feeds.PandasData):
    """PandasData feed for our lowercase OHLCV frames (no open interest)."""

    params = (
        ("datetime", None),  # use the index
        ("open", "open"),
        ("high", "high"),
        ("low", "low"),
        ("close", "close"),
        ("volume", "volume"),
        ("openinterest", None),
    )


def make_feed(df: pd.DataFrame, name: str) -> PandasOHLCV:
    """Wrap an OHLCV DataFrame (DatetimeIndex) as a named backtrader feed."""
    if not isinstance(df.index, pd.DatetimeIndex):
        raise ValueError(f"feed '{name}' requires a DatetimeIndex")
    feed = PandasOHLCV(dataname=df)
    feed._name = name
    return feed
