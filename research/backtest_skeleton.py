"""Standalone pandas/numpy backtest skeleton for the ORB + VWAP strategy.

EDUCATIONAL USE ONLY. NOT FINANCIAL ADVICE. Hypothetical performance is not
indicative of future results. Futures trading involves substantial risk of loss.

This is deliberately independent of the backtrader scaffold in src/ — it is a
research harness for fast iteration, walk-forward testing, and Monte Carlo
robustness checks before anything goes near live wiring.

Expected input: 5-minute OHLCV bars for a *continuous, back-adjusted* futures
series (e.g. MES/ES from Databento, Polygon, or your broker), with a
timezone-aware datetime index in America/New_York.

    df columns: open, high, low, close, volume

Fill model (must match the Pine version so results are comparable):
  * signals evaluated on bar close, filled at NEXT bar open
  * slippage: SLIPPAGE_TICKS per side, always adverse
  * stops/targets checked against bar high/low; if both hit in one bar,
    assume the STOP hit first (conservative)
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ----------------------------------------------------------------------------
# Contract / cost specification (MES defaults — change for ES)
# ----------------------------------------------------------------------------
TICK_SIZE = 0.25
POINT_VALUE = 5.0            # $/point for MES ($50 for ES)
TICK_VALUE = TICK_SIZE * POINT_VALUE
COMMISSION_PER_SIDE = 1.25   # $/contract/side, all-in — set to your broker
SLIPPAGE_TICKS = 1           # re-run with 2 before trusting anything

# ----------------------------------------------------------------------------
# Strategy parameters (keep this dict small — every knob is overfitting surface)
# ----------------------------------------------------------------------------
PARAMS = dict(
    or_start="09:30", or_end="10:00",       # opening-range window (ET)
    entry_end="13:30",                      # no new entries after this
    flat_time="15:55",                      # everything flat here
    atr_len=14,                             # intraday ATR, 5-min bars
    or_min_frac=0.15, or_max_frac=0.70,     # OR width vs daily ATR(14)
    stop_atr_mult=1.5,
    target_r=2.0,
    be_trigger_r=1.0,
    risk_pct=0.5,                           # % of equity risked per trade
    max_contracts=10,
    max_trades_day=2,
    max_day_loss_pct=1.5,                   # circuit breaker
)


def load_data(path: str) -> pd.DataFrame:
    """Load 5-min OHLCV bars, restrict to RTH, attach a session date column."""
    df = pd.read_parquet(path)  # or read_csv + tz_localize/tz_convert
    df = df.between_time("09:30", "15:59")
    df["session"] = df.index.date
    return df


def add_indicators(df: pd.DataFrame, p: dict) -> pd.DataFrame:
    """Vectorized indicator prep: ATR, session VWAP, OR levels, daily ATR."""
    # Intraday ATR (Wilder)
    tr = np.maximum(df.high - df.low,
                    np.maximum((df.high - df.close.shift()).abs(),
                               (df.low - df.close.shift()).abs()))
    df["atr"] = tr.ewm(alpha=1 / p["atr_len"], adjust=False).mean()

    # Session-anchored VWAP
    pv = (df[["high", "low", "close"]].mean(axis=1) * df.volume)
    df["vwap"] = pv.groupby(df.session).cumsum() / df.volume.groupby(df.session).cumsum()

    # Opening range per session, only valid after the OR window closes
    in_or = (df.index.time >= pd.Timestamp(p["or_start"]).time()) & \
            (df.index.time < pd.Timestamp(p["or_end"]).time())
    df["or_high"] = df.high.where(in_or).groupby(df.session).cummax()
    df["or_low"] = df.low.where(in_or).groupby(df.session).cummin()
    df["or_done"] = ~in_or & df.or_high.notna()

    # Daily ATR(14) from RTH daily bars, shifted so day N uses data through N-1
    daily = df.groupby("session").agg(h=("high", "max"), l=("low", "min"), c=("close", "last"))
    dtr = np.maximum(daily.h - daily.l,
                     np.maximum((daily.h - daily.c.shift()).abs(),
                                (daily.l - daily.c.shift()).abs()))
    daily_atr = dtr.ewm(alpha=1 / 14, adjust=False).mean().shift(1)
    df["daily_atr"] = df.session.map(daily_atr)
    return df


def run_backtest(df: pd.DataFrame, p: dict, equity0: float = 25_000,
                 blackout_dates: set | None = None) -> pd.DataFrame:
    """Event-loop simulation. Returns a trades DataFrame.

    The loop is intentionally explicit (not vectorized) so the fill model,
    breakeven logic, and daily circuit breaker are unambiguous and auditable.
    """
    blackout_dates = blackout_dates or set()
    equity = equity0
    trades: list[dict] = []
    pos = 0                     # +qty long, -qty short, 0 flat
    entry_px = stop_px = target_px = risk_pts = np.nan
    day = None
    day_start_eq = equity
    trades_today = 0
    long_taken = short_taken = halted = False
    pending = None              # (side, qty, risk_pts) to fill at next bar open

    for bar in df.itertuples():
        t = bar.Index
        if t.date() != day:                      # new session: reset state
            day, day_start_eq, trades_today = t.date(), equity, 0
            long_taken = short_taken = halted = False
            pending = None

        # ---- fill pending entry at this bar's open ----
        if pending is not None and pos == 0:
            side, qty, rp = pending
            slip = SLIPPAGE_TICKS * TICK_SIZE * (1 if side > 0 else -1)
            entry_px = bar.open + slip
            pos, risk_pts = side * qty, rp
            stop_px = entry_px - side * rp
            target_px = entry_px + side * p["target_r"] * rp
            equity -= qty * COMMISSION_PER_SIDE
            trades_today += 1
            pending = None

        # ---- manage open position: stop first (conservative), then target ----
        if pos != 0:
            side, qty = np.sign(pos), abs(pos)
            hit_stop = bar.low <= stop_px if side > 0 else bar.high >= stop_px
            hit_tgt = bar.high >= target_px if side > 0 else bar.low <= target_px
            flat_now = t.time() >= pd.Timestamp(p["flat_time"]).time() or halted
            exit_px = np.nan
            if hit_stop:
                exit_px = stop_px - side * SLIPPAGE_TICKS * TICK_SIZE
            elif hit_tgt:
                exit_px = target_px           # limit order: no slippage
            elif flat_now:
                exit_px = bar.close - side * SLIPPAGE_TICKS * TICK_SIZE
            if not np.isnan(exit_px):
                pnl = side * (exit_px - entry_px) * POINT_VALUE * qty - qty * COMMISSION_PER_SIDE
                equity += pnl
                trades.append(dict(exit_time=t, side=int(side), qty=int(qty),
                                   entry=entry_px, exit=exit_px, pnl=pnl, equity=equity))
                pos = 0
            elif side * (bar.close - entry_px) >= p["be_trigger_r"] * risk_pts:
                # Breakeven only on a full bar close beyond +be_trigger_r
                stop_px = max(stop_px, entry_px) if side > 0 else min(stop_px, entry_px)

        # ---- circuit breaker ----
        halted = halted or (equity - day_start_eq) <= -p["max_day_loss_pct"] / 100 * day_start_eq

        # ---- signal generation on bar close (filled next bar open) ----
        ok = (bar.or_done and not halted and pos == 0 and pending is None
              and t.date() not in blackout_dates
              and trades_today < p["max_trades_day"]
              and pd.Timestamp(p["or_end"]).time() <= t.time() < pd.Timestamp(p["entry_end"]).time()
              and not np.isnan(bar.daily_atr)
              and p["or_min_frac"] * bar.daily_atr <= (bar.or_high - bar.or_low) <= p["or_max_frac"] * bar.daily_atr)
        if ok:
            rp = p["stop_atr_mult"] * bar.atr
            qty = min(p["max_contracts"], int(equity * p["risk_pct"] / 100 / (rp * POINT_VALUE)))
            if qty >= 1:
                if not long_taken and bar.close > bar.or_high and bar.close > bar.vwap:
                    pending, long_taken = (+1, qty, rp), True
                elif not short_taken and bar.close < bar.or_low and bar.close < bar.vwap:
                    pending, short_taken = (-1, qty, rp), True

    return pd.DataFrame(trades)


def metrics(trades: pd.DataFrame, equity0: float = 25_000) -> dict:
    """Core evaluation metrics. Judge nothing on fewer than ~300 trades."""
    if trades.empty:
        return {}
    wins, losses = trades.pnl[trades.pnl > 0], trades.pnl[trades.pnl <= 0]
    eq = trades.equity
    dd = (eq - eq.cummax())
    daily = trades.set_index("exit_time").pnl.resample("1D").sum().dropna()
    return dict(
        n_trades=len(trades),
        win_rate=len(wins) / len(trades),
        profit_factor=wins.sum() / max(1e-9, -losses.sum()),
        expectancy_usd=trades.pnl.mean(),
        max_drawdown_usd=dd.min(),
        max_drawdown_pct=(dd / eq.cummax()).min(),
        sharpe_daily_ann=daily.mean() / max(1e-9, daily.std()) * np.sqrt(252),
        total_return_pct=(eq.iloc[-1] - equity0) / equity0,
    )


def walk_forward(df: pd.DataFrame, train_years: int = 2, test_months: int = 6):
    """Rolling walk-forward: optimize on train window, evaluate on the next
    unseen test window, roll forward, concatenate ONLY the test segments.

    TODO: grid over a SMALL set (stop_atr_mult in {1.25, 1.5, 2.0},
    target_r in {1.5, 2.0, 2.5}) — nothing else. If the concatenated
    out-of-sample equity curve isn't acceptable, the strategy fails. Do not
    go back and add filters until it passes; that is curve-fitting.
    """
    raise NotImplementedError


def monte_carlo(trades: pd.DataFrame, n: int = 5000, equity0: float = 25_000):
    """Bootstrap trade order to estimate drawdown distribution.

    Report the 95th-percentile max drawdown — size the account so you can
    survive it financially AND psychologically.
    """
    rng = np.random.default_rng(0)
    max_dds = []
    for _ in range(n):
        eq = equity0 + rng.permutation(trades.pnl.values).cumsum()
        max_dds.append((eq - np.maximum.accumulate(eq)).min())
    return np.percentile(max_dds, [50, 95, 99])


if __name__ == "__main__":
    df = add_indicators(load_data("data/mes_5min.parquet"), PARAMS)
    trades = run_backtest(df, PARAMS)
    print(pd.Series(metrics(trades)))
    if len(trades) >= 100:
        print("MC max-DD p50/p95/p99:", monte_carlo(trades))
