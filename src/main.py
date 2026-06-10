"""CLI entry point.

Backtest on real data (cached/yfinance):
    python -m src.main backtest --start 2020-01-01 --end 2026-06-01

Backtest on synthetic cointegrated data (no network needed):
    python -m src.main backtest --synthetic

Live/paper trading (requires TWS or IB Gateway):
    python -m src.main live
"""

import argparse

from .utils.config import load_config
from .utils.logger import setup_logger


def cmd_backtest(args: argparse.Namespace, config: dict) -> None:
    from .backtest.runner import format_results, run_backtest
    from .data import historical

    if args.synthetic:
        nq, es = historical.generate_synthetic_pair(n_bars=args.bars, seed=args.seed)
        source = f"synthetic ({args.bars} bars, seed {args.seed})"
    else:
        nq, es = historical.load_pair(
            args.start, args.end, cache_dir=config["data"]["historical_dir"]
        )
        source = f"{args.start} → {args.end}"

    print(f"Running NQ/ES pairs backtest on {source}: {len(nq)} bars")
    results = run_backtest(nq, es, config)
    print(format_results(results))


def cmd_live(args: argparse.Namespace, config: dict) -> None:
    from .execution.live import LiveTrader

    port = int(config["ibkr"]["port"])
    if port in (7496, 4001) and not args.i_know_this_is_live:
        raise SystemExit(
            f"port {port} is a LIVE trading port. Re-run with "
            "--i-know-this-is-live if you really mean it; otherwise use a "
            "paper port (7497 TWS / 4002 Gateway) in config/settings.yaml."
        )
    LiveTrader(config).run(poll_seconds=args.poll)


def main() -> None:
    parser = argparse.ArgumentParser(description="NQ/ES futures spread trading bot")
    parser.add_argument("--config", default="config/settings.yaml")
    sub = parser.add_subparsers(dest="command", required=True)

    p_bt = sub.add_parser("backtest", help="run a backtest")
    p_bt.add_argument("--start", default="2020-01-01")
    p_bt.add_argument("--end", default="2026-01-01")
    p_bt.add_argument("--synthetic", action="store_true", help="use synthetic data")
    p_bt.add_argument("--bars", type=int, default=1500, help="synthetic bar count")
    p_bt.add_argument("--seed", type=int, default=42, help="synthetic RNG seed")
    p_bt.set_defaults(func=cmd_backtest)

    p_live = sub.add_parser("live", help="run live/paper trading via IBKR")
    p_live.add_argument("--poll", type=int, default=3600, help="poll interval seconds")
    p_live.add_argument("--i-know-this-is-live", action="store_true")
    p_live.set_defaults(func=cmd_live)

    args = parser.parse_args()
    config = load_config(args.config)
    setup_logger("bot", config["logging"]["level"], config["logging"]["file"])
    args.func(args, config)


if __name__ == "__main__":
    main()
