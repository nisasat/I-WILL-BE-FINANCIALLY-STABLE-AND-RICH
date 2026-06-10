# Futures Trading Bot

A Python 3.11 futures trading bot scaffold that uses
[`backtrader`](https://www.backtrader.com/) for backtesting and
[`ib_insync`](https://github.com/erdewit/ib_insync) for live integration with
Interactive Brokers (IBKR).

The implemented strategy trades the **NQ/ES spread** (mean reversion on the
beta-hedged log spread between Nasdaq-100 and S&P 500 E-mini futures):

- rolling OLS hedge ratio of `log(NQ)` on `log(ES)` (`beta_lookback` bars)
- z-score of the spread over `z_lookback` bars
- enter long spread (long NQ / short ES) at `z <= -entry_z`, short spread at
  `z >= entry_z`
- exit on reversion (`|z| <= exit_z`), blow-out stop (`|z| >= stop_z`), or a
  time stop (`max_holding_bars`)
- ES leg sized to dollar-hedge the NQ leg using the contract multipliers
  ($20/pt NQ, $50/pt ES)
- a risk manager caps per-leg contracts and halts entries after a daily loss
  limit is breached

The same signal engine (`src/strategies/signals.py`) drives both the
backtrader backtest and the live IBKR loop, so what you backtest is what you
trade.

> **Disclaimer:** futures trading involves substantial risk of loss; losses
> can exceed your deposit. A profitable backtest — especially on synthetic
> data — is *not* evidence of future profitability. Always validate on real
> historical data, then paper trade before risking capital.

## Requirements

- Python 3.11
- An Interactive Brokers account with TWS or IB Gateway running locally for
  live/paper trading (not needed for backtesting).

## Setup

```bash
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy `config/settings.yaml.example` to `config/settings.yaml` and fill in your
local values. The real `settings.yaml` is git-ignored so that credentials and
account-specific parameters never get committed.

```bash
cp config/settings.yaml.example config/settings.yaml
```

## Directory layout

```
.
├── README.md                 This file.
├── requirements.txt          Python dependencies (backtrader, ib_insync, ...).
├── .gitignore                Ignores config/settings.yaml and logs/.
├── config/
│   ├── settings.yaml         Local config (git-ignored).
│   └── settings.yaml.example Template committed to the repo.
├── logs/                     Runtime logs (git-ignored).
├── src/
│   ├── __init__.py
│   ├── main.py               Entry point for live / backtest runs.
│   ├── data/                 Market-data feeds and historical loaders.
│   │   ├── __init__.py
│   │   ├── feeds.py          Real-time/backtest data feed adapters.
│   │   └── historical.py     Historical data fetching and caching.
│   ├── strategies/           Trading strategies (to be implemented).
│   │   ├── __init__.py
│   │   └── base.py           Base strategy class.
│   ├── backtest/             Backtrader wiring.
│   │   ├── __init__.py
│   │   └── runner.py         Cerebro engine runner.
│   ├── broker/               Broker integrations.
│   │   ├── __init__.py
│   │   └── ibkr.py           ib_insync IBKR client wrapper.
│   ├── execution/            Order routing / live execution.
│   │   ├── __init__.py
│   │   └── live.py           Live trading loop.
│   ├── risk/                 Risk management.
│   │   ├── __init__.py
│   │   └── manager.py        Position sizing, stops, limits.
│   └── utils/                Shared helpers.
│       ├── __init__.py
│       ├── config.py         YAML config loading.
│       └── logger.py         Logging setup.
└── tests/
    ├── __init__.py
    └── test_placeholder.py
```

## Module responsibilities

- **`src/main.py`** — CLI entry point. Dispatches to backtest or live mode.
- **`src/data/`** — Abstractions over historical and real-time market data.
  `feeds.py` wraps backtrader data feeds; `historical.py` is responsible for
  downloading and caching bar data.
- **`src/strategies/`** — Strategy implementations. `base.py` will hold a shared
  base class on top of `backtrader.Strategy`.
- **`src/backtest/`** — Glue code that builds a `Cerebro` instance, attaches
  data, strategy, broker, analyzers, and runs the backtest.
- **`src/broker/ibkr.py`** — Thin wrapper around `ib_insync.IB` to manage
  connection, contracts, and order placement against IBKR.
- **`src/execution/live.py`** — Runtime loop for live/paper trading: connects
  to IBKR, feeds bars into the strategy, and routes orders.
- **`src/risk/manager.py`** — Position sizing and risk guards that sit between
  strategy signals and order execution.
- **`src/utils/`** — Config loading (`config.py`) and logging setup
  (`logger.py`) shared across the rest of the code.

## Running

Backtest on real NQ=F / ES=F data (downloaded via yfinance and cached under
`data/historical/`):

```bash
python -m src.main backtest --start 2020-01-01 --end 2026-06-01
```

Backtest on synthetic cointegrated data (no network required — useful for
development and CI):

```bash
python -m src.main backtest --synthetic --bars 1500 --seed 42
```

Live/paper trading (requires TWS or IB Gateway running; the CLI refuses live
ports unless you pass `--i-know-this-is-live`):

```bash
python -m src.main live --poll 3600
```

Strategy, risk, and broker parameters live in `config/settings.yaml` (see the
example file).

## TradingView (Pine Script)

`pine/nq_es_spread_strategy.pine` is a Pine v6 port of the same strategy for
TradingView:

1. Open a **CME_MINI:NQ1!** chart (daily timeframe matches the defaults) and
   paste the script into the Pine Editor.
2. TradingView strategies can only place orders on the chart's own symbol, so
   the Strategy Tester executes the **NQ leg only** — treat its PnL as an
   approximation of half the spread.
3. To trade the full spread, create an alert on the strategy with
   `{{strategy.order.alert_message}}` in the message body: every entry/exit
   emits JSON describing **both legs**, including the dollar-neutral ES hedge
   size (e.g. `{"action":"enter_long_spread","NQ":"BUY 1","ES":"SELL 2",...}`),
   ready for a webhook → broker bridge.

Inputs mirror `config/settings.yaml` (beta/z lookbacks, entry/exit/stop
z-scores, time stop, contract multipliers, daily loss halt).

## Tests

```bash
pytest
```
