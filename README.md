# Futures Trading Bot

A Python 3.11 futures trading bot scaffold that uses
[`backtrader`](https://www.backtrader.com/) for backtesting and
[`ib_insync`](https://github.com/erdewit/ib_insync) for live integration with
Interactive Brokers (IBKR).

The first strategy — an Opening-Range Breakout with VWAP and volatility
filters for /MES — is fully specified in [`docs/STRATEGY.md`](docs/STRATEGY.md),
with a ready-to-use TradingView implementation in
[`pinescript/orb_vwap_mes.pine`](pinescript/orb_vwap_mes.pine) and a
standalone pandas/numpy research backtester in
[`research/backtest_skeleton.py`](research/backtest_skeleton.py). The
`src/` backtrader/IBKR scaffold is the eventual home for live wiring once the
strategy survives validation.

> **Educational use only — not financial advice.** Hypothetical or past
> performance is not indicative of future results. Futures trading involves
> substantial risk of loss.

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

Scripts and entry points will be added as strategies are implemented. For now,
everything in `src/` is intentionally empty.

## Tests

```bash
pytest
```
