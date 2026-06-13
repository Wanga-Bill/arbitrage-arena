# OpenClaw Historical Performance, Penalty, & Sizing Matrix

This document defines the mathematical evaluation, back-testing validation loop, and risk adjustment parameters for the World Cup live arbitrage node. 

## 1. Core Evaluation Mathematical Framework

Every finalized live tracking recommendation must be logged and evaluated using the **Brier Score** ($BS$) metric to determine true probabilistic calibration accuracy:

$$BS = \frac{1}{N} \sum_{t=1}^{N} (f_t - o_t)^2$$

Where:
* $f_t$ is the exact decimal probability calculated by our internal dominance engine.
* $o_t$ is the actual binary outcome (1 if the event occurred, 0 if it failed).

---

## 2. Adaptive Penalty & Reward System (The Weight Shift)

The agent maintains an active bias variable called `METRIC_CONFIDENCE_WEIGHT` (Default: `1.0`) for every algorithmic trigger. After every match closure, recalculate performance and apply the following modifier boundaries:

### 🟢 Reward Triggers (Confidence Amplification)
* **Criteria**: Recommendation hits successfully AND calculated model probability $f_t \ge 0.85$.
* **Action**: Increase `METRIC_CONFIDENCE_WEIGHT` by `+0.05` (Cap at `1.25`).
* **SaaS Output**: Automatically flag matching upcoming setups in the Free Channel as "🔥 Verified Whale Lock - Hot Streak".

### 🔴 Penalty Triggers (Throttling & Calibration Breaks)
* **Criteria**: Prediction fails completely ($o_t = 0$) while model confidence was high ($f_t \ge 0.90$).
* **Action**: Deduct `-0.15` from `METRIC_CONFIDENCE_WEIGHT` instantly.
* **Guardrail**: If any sub-metric weight drops below `0.70`, the agent must **force-throttle** that trigger type, muting alerts to prevent premium subscriber churn until calibration stabilizes.

---

## 3. High-Revenue Sizing Optimization (Kelly Criterion)

To drive the high-stake premium narrative for lead generation, the agent translates calculated live probability into optimal asset placement sizes using a fractional Kelly Criterion allocation formula:

$$f^* = \frac{p(b + 1) - 1}{b}$$

Where:
* $f^*$ is the calculated optimal bet fractional stake allocation.
* $p$ is the calibrated internal live probability adjusted by our metric weight.
* $b$ is the current live decimal odds multiplier offered by our partner sportsbooks minus 1.

### Sizing Tier Outputs to Telegram
The agent will pass the computed $f^*$ value to structure the exact text styling of the dispatched alert payload:
* **Whale Vault ($f^* \ge 0.08$)**: Label as "🚨 [MAX STAKE / HIGH ASSET ALLOCATION] 🚨"
* **High-Yield Retail ($0.03 \le f^* < 0.08$)**: Label as "📈 [AGGRESSIVE VARIANCE OPPORTUNITY] 📈"
