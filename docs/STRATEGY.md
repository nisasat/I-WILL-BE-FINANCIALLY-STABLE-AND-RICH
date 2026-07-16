# ORB + VWAP Futures Day Trading Strategy — Design, Validation & Deployment

> **EDUCATIONAL USE ONLY. NOT FINANCIAL ADVICE.** Hypothetical or past
> performance is not indicative of future results. Trading futures involves
> substantial risk of loss and is not suitable for all investors. Nothing here
> is personalized investment advice.

Target instrument: **/MES** (Micro E-mini S&P 500). Everything transfers to
/ES by multiplying dollar figures by 10 and re-checking costs.

Repo artifacts:

| File | Purpose |
|---|---|
| `pinescript/orb_vwap_mes.pine` | Complete Pine Script v6 strategy for TradingView |
| `research/backtest_skeleton.py` | Standalone pandas/numpy research backtester |
| `src/` | backtrader/ib_insync scaffold for eventual live wiring |

---

## Step 1 — Candidate Edges

### Edge A: Filtered Opening Range Breakout (ORB)
The 9:30–10:00 ET window concentrates overnight order-flow resolution:
institutions execute decisions made off the overnight session, economic data
(8:30/10:00 releases), and Europe's afternoon. When the day's range expands
*beyond* that initial auction with directional conviction, a meaningful
fraction of those days become trend days, and trend days pay for many small
failed-breakout losses. The edge is **positive skew**: low win rate, large
winners. Crucially, it degrades gracefully — a filtered ORB that stops working
bleeds slowly rather than blowing up.

### Edge B: VWAP Mean Reversion
Institutional execution algos benchmark to VWAP. On balanced (non-trend) days,
extensions of ~1.5–2 standard deviations from session VWAP tend to revert as
passive institutional flow leans against the move. Exploitable, but it has
**negative skew**: high win rate, occasional catastrophic loss when a
"stretched" market is actually beginning a trend day. Stops get run at the
worst moments, and distinguishing balance days from trend days *in advance* is
the entire (hard) problem.

### Edge C: Trend-Day Pullback Continuation
On days that establish early directional conviction (open drives), pullbacks
to VWAP or the 20-EMA tend to get bought/sold by late institutional flow that
missed the initial move. Solid concept, but it requires a reliable trend-day
classifier, which adds parameters and overfitting surface.

### Selection
**Edge A**, with a VWAP-side filter borrowed from Edge C's logic (only take
breakouts on the VWAP side of the market, i.e. in the direction the average
participant is already positioned). Reasons: fewest parameters, positive skew,
mechanically unambiguous, robust literature (ORB variants are among the few
day-trading approaches with published evidence of persistence), and failure
mode is slow bleed rather than tail-risk blowup.

---

## Step 2 — Full Specification

| Rule | Specification |
|---|---|
| Instrument | /MES (CME Micro E-mini S&P 500), front month, roll ~8 days before expiry |
| Timeframe | 5-minute bars, RTH focus |
| Opening range (OR) | High/low of 9:30–10:00 ET (six 5-min bars) |
| Long entry | First 5-min **close** > OR high, AND close > session VWAP (RTH-anchored), during entry window |
| Short entry | First 5-min **close** < OR low, AND close < session VWAP, during entry window |
| Entry window | 10:00–13:30 ET only. No new entries after 13:30 |
| Fill assumption | Next bar open after signal close (market order) |
| Initial stop | 1.5 × ATR(14, 5-min) from fill price |
| Profit target | 2.0 R (2 × initial stop distance), limit order |
| Breakeven | After a 5-min close ≥ +1.0 R in favor, stop moves to entry price |
| Session exit | Flatten everything at 15:55 ET, no exceptions, no overnight holds |
| Volatility filter | Trade only if OR width is 0.15–0.70 × daily ATR(14). Below: dead day, chop. Above: range already spent / event shock |
| News filter | No trading on FOMC decision days, CPI, NFP (maintained blackout-date list; Pine cannot read a calendar) |
| Position sizing | contracts = floor(0.5% of equity ÷ (stop distance × $5/pt)), min 1 else skip, capped at 10 |
| Max trades/day | 2 (one attempt per direction) |
| Circuit breaker | Daily loss ≥ 1.5% of day-start equity → flatten, no new trades until next session |

Parameter count that actually matters: OR window, stop multiple, target R,
OR-width band. That's deliberately small. Every additional filter you bolt on
after seeing a backtest is curve-fitting.

Expected character: roughly 0.6–1.2 trades/day, ~150–300 trades/year,
win rate 35–45%, average winner ≈ 1.6–1.9 R after breakeven exits,
average hold 30 min–3 h.

---

## Step 3 — Implementation

- **Pine Script v6**: `pinescript/orb_vwap_mes.pine`. Load on an MES 5-min
  chart. Costs are modeled in the `strategy()` declaration (per-side
  commission + 1 tick slippage) — set them to your broker's real numbers and
  re-test at 2 ticks before believing anything.
- **Python**: `research/backtest_skeleton.py`. Same fill model (next-bar-open
  entries, stop-before-target intrabar assumption, adverse slippage) so the
  two implementations can cross-validate each other. Walk-forward and Monte
  Carlo stubs included.

---

## Step 4 — Backtesting & Validation Plan

### Data & period
Minimum **2018 → present**, 5-min bars, continuous back-adjusted contract.
That covers: Volmageddon (Feb 2018), Q4-2018 bear, 2019 grind, COVID crash and
V-recovery (2020), 2021 low-vol melt-up, 2022 rate-hike bear, 2023–24
AI-driven bull, 2025. If the strategy only works in 2–3 of those regimes, you
must know *which ones* and *why* before risking money. TradingView's intraday
history is too shallow for this — buy 5-min history (Databento, Polygon,
IQFeed) and use the Python harness; treat TradingView as a prototype/execution
layer only.

### Walk-forward protocol
1. Freeze the rule structure. Optimizable set: stop multiple {1.25, 1.5, 2.0},
   target R {1.5, 2.0, 2.5}. Nothing else.
2. Train 2 years → test the next 6 months (untouched). Roll forward 6 months.
   Repeat across the whole history.
3. Concatenate **only** the out-of-sample segments into one equity curve.
   That curve is your honest estimate.
4. One shot. If it fails, the strategy fails. Going back to add filters until
   the OOS curve looks good silently converts your out-of-sample data into
   in-sample data.
5. Keep the most recent ~12 months as a final holdout you touch exactly once.

### Metrics & realistic target ranges (after costs)

| Metric | Viable range | Red flag |
|---|---|---|
| Profit factor | 1.15 – 1.40 | > 1.8 (almost certainly overfit or costs missing) |
| Win rate | 35 – 45% (breakout style) | > 60% for this style |
| Expectancy | ≥ $8–15 per MES contract per trade (≥ ~0.15 R) | < 1 tick after costs |
| Max drawdown | < 15% of account; expect 10–25 R peak-to-trough | any DD you couldn't psychologically survive |
| Sharpe (daily, annualized) | 0.7 – 1.3 | > 2.5 |
| Trade count | ≥ 300 OOS trades before judging | conclusions from < 100 trades |
| Avg duration | 30 min – 3 h | — |

### Cost model
- Commission: ~$1.00–1.50/side/contract all-in for MES (broker + exchange +
  NFA). ES: ~$2–3/side.
- Slippage: 1 tick per side baseline (market entries and stop exits; limit
  target fills get none). **Re-run everything at 2 ticks** — MES is $1.25/tick,
  so 2 trades/day at 2 ticks each way is real money. If the edge dies between
  1 and 2 ticks of slippage, there is no edge.

### Robustness checks
- **Parameter sensitivity**: perturb each parameter ±20%. Performance should
  degrade smoothly. A sharp peak at exactly 1.5×ATR is noise you memorized.
- **Monte Carlo**: bootstrap trade order 5,000×; plan capital around the
  95th-percentile max drawdown, not the historical one.
- **Regime slicing**: report results separately for VIX <15, 15–25, >25 and
  by year. Know where the P&L comes from.
- **Cross-validation**: Pine and Python results on the same period should
  broadly agree; large divergence means a fill-model bug.

---

## Step 5 — Execution / Deployment

### Semi-automated (recommended starting point)
TradingView alert on the strategy ("Order fills and alert() function calls",
message `{{strategy.order.alert_message}}`) → you manually confirm and place
the order. Slower, but you learn how the system behaves live before trusting
it with autonomy.

### Automated paths
| Path | Notes |
|---|---|
| TradingView webhook → TradersPost → Tradovate | Easiest no-code bridge; Tradovate has good micro pricing and a REST/WebSocket API |
| TradingView webhook → custom relay (small Flask/FastAPI service) → Tradovate/IBKR API | Most control; the JSON alert payloads in the Pine file are built for this |
| NinjaTrader | Port the strategy to NinjaScript; tight broker integration, good sim engine |
| IBKR via `ib_insync` | What `src/` in this repo scaffolds; solid API, futures commissions fine, data feed adequate |

### Brokers (US futures, day trading)
- **Tradovate/NinjaTrader**: low micro commissions, modern API, popular for
  exactly this use case.
- **AMP / Optimus** (Rithmic/CQG routing): very low cost, robust order routing.
- **IBKR**: fine all-rounder, best if you already have the account; API is the
  most mature.
- Avoid anything without native server-side bracket/OCO orders — your stop
  must live at the broker/exchange, not in your script.

### Forward-testing protocol (non-negotiable)
1. **Paper/sim**: minimum **3 months AND 60+ trades**, whichever is longer,
   on the full automated pipeline (alerts → webhook → sim fills). You're
   testing the plumbing as much as the edge: missed alerts, duplicate orders,
   rollover handling, session-boundary bugs.
2. Compare sim fills to the backtest's assumed fills trade by trade. If live
   slippage exceeds the model, fix the model and re-validate.
3. **Live with 1 MES** for another 2–3 months before any size increase.
4. Scale only on new equity highs; cut size in half after a 10% drawdown.

### Latency / infrastructure
A 5-minute-bar strategy is not latency sensitive — seconds are fine, so a
$5–10/month VPS (or any always-on machine) for the webhook relay is plenty.
What matters instead: TradingView alert delivery reliability, webhook retries,
idempotency (never act twice on a duplicate alert), and a kill switch that
flattens via the broker directly if the pipeline desyncs. If you ever move to
1-min scalping, that calculus changes (Chicago-proximate VPS, direct API) —
this strategy deliberately avoids needing it.

---

## Step 6 — Realism, Risks & Honest Assessment

**Most retail futures day traders lose money.** Commonly cited figures put
consistent long-term profitability in the low single-digit percentages of
participants. You are trading against firms with microstructure expertise,
co-located infrastructure, and full-time researchers. The only reasons a
simple retail system can survive at all: no latency competition at the
5-minute horizon, positive-skew payoff structure, and — above all —
discipline about risk that most participants lack.

**How AI-generated (and human-generated) strategies fool you:**
- *Overfitting*: enough parameters will fit any historical noise. This design
  keeps ~4 meaningful knobs on purpose. If you find yourself adding a filter
  because the backtest "needed it," stop.
- *Understated costs*: 1 tick of slippage on MES is $1.25. Two round trips a
  day at 2 ticks total each ≈ $1,200/year/contract before commissions. Many
  published "edges" are smaller than that.
- *Regime dependence*: ORB earns its money on trend days. A prolonged low-vol
  chop regime (2017-style) will bleed for months. You must know your regime
  exposure *before* it happens or you'll abandon the system at the bottom of
  its drawdown — the single most common way traders lose with a
  net-profitable system.
- *Psychology*: a 40%-win-rate system produces 6–8 consecutive losses
  routinely (probability of an 8-loss streak somewhere in 250 trades is high).
  If you can't sit through that without overriding the rules, the system's
  stats are irrelevant.
- *Silent look-ahead / fill fantasy*: backtests that fill limit orders that
  were never truly touched, use same-bar close fills on close-based signals,
  or leak daily data intraday. Both implementations here model next-bar-open
  fills and stop-before-target for that reason.

**Capital**: with 0.5% risk per trade and typical MES stop distances
($25–60/contract), you need roughly **$10,000+** to size even 1–2 contracts
correctly; $25,000 is comfortable. Trade only money whose total loss would
not change your life. Day-trading margins are a leverage convenience, not a
suggestion of appropriate size.

**Nothing works forever.** An edge is a hypothesis under continuous test.
Track live expectancy vs. backtest expectancy monthly; if live performance
falls outside the Monte Carlo 95% envelope, stop and re-validate rather than
hoping.

> **Disclaimer**: This document and all code in this repository are for
> educational purposes only. They are not investment advice, not a
> solicitation, and not a recommendation to trade any instrument. Hypothetical
> or simulated performance results have inherent limitations and do not
> represent actual trading. Past performance is not indicative of future
> results. Futures trading involves substantial risk of loss. Consult a
> licensed financial professional before making investment decisions.
