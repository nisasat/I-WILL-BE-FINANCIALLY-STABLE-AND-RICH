"""Historical data: yfinance download with CSV caching, plus a synthetic
cointegrated NQ/ES pair generator for offline development and testing.

Contract specs used throughout the project:
    NQ: $20 per index point, 0.25 tick
    ES: $50 per index point, 0.25 tick
"""

from pathlib import Path

import numpy as np
import pandas as pd

YAHOO_SYMBOLS = {"NQ": "NQ=F", "ES": "ES=F"}
MULTIPLIERS = {"NQ": 20.0, "ES": 50.0}

OHLCV_COLS = ["open", "high", "low", "close", "volume"]


def _cache_path(cache_dir: str | Path, symbol: str, interval: str) -> Path:
    return Path(cache_dir) / f"{symbol}_{interval}.csv"


def load_history(
    symbol: str,
    start: str,
    end: str,
    interval: str = "1d",
    cache_dir: str | Path = "data/historical",
) -> pd.DataFrame:
    """Return an OHLCV DataFrame for *symbol* ('NQ' or 'ES').

    Tries the local CSV cache first; falls back to yfinance and writes the
    cache. Raises RuntimeError when neither source can satisfy the request
    (e.g. no network) — callers may then use `generate_synthetic_pair`.
    """
    path = _cache_path(cache_dir, symbol, interval)
    if path.exists():
        df = pd.read_csv(path, index_col=0, parse_dates=True)
        df = df.loc[start:end]
        if not df.empty:
            return df[OHLCV_COLS]

    try:
        import yfinance as yf

        raw = yf.download(
            YAHOO_SYMBOLS[symbol],
            start=start,
            end=end,
            interval=interval,
            progress=False,
            auto_adjust=False,
        )
    except Exception as exc:  # pragma: no cover - network dependent
        raise RuntimeError(f"download failed for {symbol}: {exc}") from exc

    if raw is None or raw.empty:
        raise RuntimeError(
            f"no data for {symbol} ({YAHOO_SYMBOLS[symbol]}) — network may be "
            "unavailable; use --synthetic or pre-populate the cache dir"
        )

    if isinstance(raw.columns, pd.MultiIndex):
        raw.columns = raw.columns.get_level_values(0)
    raw.columns = [str(c).lower() for c in raw.columns]
    df = raw[OHLCV_COLS].dropna()

    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path)
    return df


def load_pair(
    start: str,
    end: str,
    interval: str = "1d",
    cache_dir: str | Path = "data/historical",
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load NQ and ES history aligned on a common index."""
    nq = load_history("NQ", start, end, interval, cache_dir)
    es = load_history("ES", start, end, interval, cache_dir)
    idx = nq.index.intersection(es.index)
    return nq.loc[idx], es.loc[idx]


def generate_synthetic_pair(
    n_bars: int = 1500,
    start: str = "2020-01-01",
    seed: int = 42,
    beta: float = 1.12,
    spread_theta: float = 0.06,
    spread_sigma: float = 0.004,
    es_start: float = 3200.0,
    nq_start: float = 8800.0,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Generate a realistic cointegrated (NQ, ES) daily OHLCV pair.

    ES follows a geometric random walk with drift; NQ tracks beta * log(ES)
    plus an Ornstein-Uhlenbeck spread, so the log spread mean-reverts the way
    the real pair (mostly) does. Useful for development and unit tests when
    market data is unavailable.
    """
    rng = np.random.default_rng(seed)

    es_ret = rng.normal(0.00045, 0.012, n_bars)  # ~11% annual drift, ~19% vol
    log_es = np.log(es_start) + np.cumsum(es_ret)

    # OU spread: ds = -theta * s * dt + sigma * dW
    spread = np.zeros(n_bars)
    for t in range(1, n_bars):
        spread[t] = (
            spread[t - 1]
            - spread_theta * spread[t - 1]
            + rng.normal(0.0, spread_sigma)
        )

    alpha = np.log(nq_start) - beta * np.log(es_start)
    log_nq = alpha + beta * log_es + spread

    index = pd.bdate_range(start=start, periods=n_bars)

    def _ohlcv(log_close: np.ndarray) -> pd.DataFrame:
        close = np.exp(log_close)
        intrabar = np.abs(rng.normal(0.004, 0.002, n_bars))
        open_ = np.concatenate([[close[0]], close[:-1]]) * (
            1 + rng.normal(0, 0.001, n_bars)
        )
        high = np.maximum(open_, close) * (1 + intrabar)
        low = np.minimum(open_, close) * (1 - intrabar)
        volume = rng.integers(150_000, 600_000, n_bars).astype(float)
        return pd.DataFrame(
            {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
            index=index,
        )

    return _ohlcv(log_nq), _ohlcv(log_es)
