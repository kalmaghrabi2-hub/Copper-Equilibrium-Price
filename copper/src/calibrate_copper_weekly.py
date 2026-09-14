#!/usr/bin/env python3
"""Benchmark-aware weekly copper fair-value calibration.

Forecast target: next observed weekly COMEX copper close (HG=F).
Model family: ridge ARX on the prior week's copper level and macro factors.
Governance: model hyperparameters and persistence-blend weight are selected on
an explicit validation window; the most recent 260 weeks remain untouched for
final out-of-sample evaluation. No imputation and no look-ahead.
"""
from __future__ import annotations

import json
import math
import statistics
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/copper/data/weekly_calibration.json"
TARGET = "HG=F"
MACRO = ["GC=F", "CL=F", "DX-Y.NYB", "^TNX", "^VIX"]
SERIES = ["LAG_COPPER_LOG"] + MACRO
START = 946684800
MIN_TRAIN = 156
VALIDATION_WEEKS = 156
FINAL_OOS_WEEKS = 260
RIDGE_CANDIDATES = [0.5, 2.0, 10.0, 50.0]
BLEND_WEIGHTS = [0.0, 0.25, 0.50, 0.75, 1.0]
MIN_R2 = 0.60
MAX_MAPE = 12.0
UA = "Mozilla/5.0 CopperEquilibriumPrice/2.0"


def chart(symbol: str):
    q = urllib.parse.quote(symbol, safe="")
    now = int(datetime.now(timezone.utc).timestamp())
    url = (
        f"https://query1.finance.yahoo.com/v8/finance/chart/{q}"
        f"?period1={START}&period2={now}&interval=1wk&events=history"
        "&includeAdjustedClose=true"
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    result = ((payload.get("chart") or {}).get("result") or [None])[0]
    if not result:
        raise RuntimeError(f"Yahoo returned no data for {symbol}")
    ts = result.get("timestamp") or []
    closes = (((result.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    out = {}
    for t, value in zip(ts, closes):
        if value is None:
            continue
        value = float(value)
        if value > 0 and math.isfinite(value):
            out[int(t) // 604800] = value
    return out, url


def solve(a, b):
    n = len(b)
    aug = [a[i][:] + [b[i]] for i in range(n)]
    for col in range(n):
        pivot = max(range(col, n), key=lambda row: abs(aug[row][col]))
        aug[col], aug[pivot] = aug[pivot], aug[col]
        z = aug[col][col]
        if abs(z) < 1e-12:
            raise RuntimeError("singular matrix")
        aug[col] = [v / z for v in aug[col]]
        for row in range(n):
            if row == col:
                continue
            factor = aug[row][col]
            aug[row] = [aug[row][j] - factor * aug[col][j] for j in range(n + 1)]
    return [aug[i][-1] for i in range(n)]


def design(rows):
    cols = list(zip(*[r[2] for r in rows]))
    means = [statistics.fmean(c) for c in cols]
    sds = [statistics.pstdev(c) or 1.0 for c in cols]
    x = [[1.0] + [(v - m) / s for v, m, s in zip(r[2], means, sds)] for r in rows]
    return x, means, sds


def fit(x_rows, y, lam):
    p = len(x_rows[0])
    a = [[0.0] * p for _ in range(p)]
    b = [0.0] * p
    for x, target in zip(x_rows, y):
        for i in range(p):
            b[i] += x[i] * target
            for j in range(p):
                a[i][j] += x[i] * x[j]
    for i in range(1, p):
        a[i][i] += lam
    return solve(a, b)


def predict_one(train, row, lam):
    x, means, sds = design(train)
    beta = fit(x, [math.log(r[1]) for r in train], lam)
    live_x = [1.0] + [(v - m) / s for v, m, s in zip(row[2], means, sds)]
    return math.exp(sum(a * b for a, b in zip(live_x, beta)))


def blended(raw, naive, weight):
    return naive + weight * (raw - naive)


def metric_block(pred, actual, naive):
    mse = statistics.fmean((a - p) ** 2 for a, p in zip(actual, pred))
    nmse = statistics.fmean((a - p) ** 2 for a, p in zip(actual, naive))
    mape = 100.0 * statistics.fmean(abs((a - p) / a) for a, p in zip(actual, pred))
    naive_mape = 100.0 * statistics.fmean(abs((a - p) / a) for a, p in zip(actual, naive))
    mean_actual = statistics.fmean(actual)
    denom = sum((a - mean_actual) ** 2 for a in actual)
    r2 = 1.0 - sum((a - p) ** 2 for a, p in zip(actual, pred)) / denom if denom else 0.0
    direction_hits = 0
    direction_n = 0
    for a, p, n in zip(actual, pred, naive):
        am = a - n
        pm = p - n
        if am != 0:
            direction_n += 1
            direction_hits += int((am > 0) == (pm > 0))
    direction = 100.0 * direction_hits / direction_n if direction_n else None
    return {
        "n": len(actual),
        "r2": round(r2, 4),
        "mape_pct": round(mape, 3),
        "accuracy_pct": round(max(0.0, min(100.0, 100.0 - mape)), 3),
        "rmse_usd_lb": round(math.sqrt(mse), 3),
        "naive_mape_pct": round(naive_mape, 3),
        "naive_accuracy_pct": round(max(0.0, min(100.0, 100.0 - naive_mape)), 3),
        "naive_rmse_usd_lb": round(math.sqrt(nmse), 3),
        "skill_vs_naive_mse_pct": round(100.0 * (1.0 - mse / nmse) if nmse > 0 else 0.0, 3),
        "direction_accuracy_pct": None if direction is None else round(direction, 2),
    }


def main():
    copper, copper_url = chart(TARGET)
    factors, urls = {}, {}
    for symbol in MACRO:
        factors[symbol], urls[symbol] = chart(symbol)

    common = sorted(set(copper).intersection(*[set(factors[s]) for s in MACRO]))
    raw = [(w, copper[w], [factors[s][w] for s in MACRO]) for w in common]
    rows = []
    for i in range(1, len(raw)):
        prev_week, prev_copper, prev_macro = raw[i - 1]
        week, current_copper, _ = raw[i]
        if week - prev_week == 1:
            rows.append((week, current_copper, [math.log(prev_copper)] + prev_macro))

    required = MIN_TRAIN + VALIDATION_WEEKS + FINAL_OOS_WEEKS
    if len(rows) < required:
        raise RuntimeError(f"insufficient complete weekly history: {len(rows)} < {required}")

    test_start = len(rows) - FINAL_OOS_WEEKS
    val_start = test_start - VALIDATION_WEEKS
    if val_start < MIN_TRAIN:
        raise RuntimeError("validation window overlaps minimum training window")

    cache = {}
    for lam in RIDGE_CANDIDATES:
        raw_pred = {}
        for i in range(val_start, len(rows)):
            raw_pred[i] = predict_one(rows[:i], rows[i], lam)
        cache[lam] = raw_pred

    candidates = []
    for lam in RIDGE_CANDIDATES:
        for weight in BLEND_WEIGHTS:
            pred, actual, naive = [], [], []
            for i in range(val_start, test_start):
                anchor = math.exp(rows[i][2][0])
                pred.append(blended(cache[lam][i], anchor, weight))
                actual.append(rows[i][1])
                naive.append(anchor)
            m = metric_block(pred, actual, naive)
            candidates.append({"ridge_lambda": lam, "blend_weight": weight, "validation": m})

    candidates.sort(key=lambda c: (c["validation"]["rmse_usd_lb"], c["validation"]["mape_pct"], c["blend_weight"]))
    selected = candidates[0]
    lam = selected["ridge_lambda"]
    weight = selected["blend_weight"]

    pred, actual, naive, dates = [], [], [], []
    for i in range(test_start, len(rows)):
        anchor = math.exp(rows[i][2][0])
        pred.append(blended(cache[lam][i], anchor, weight))
        actual.append(rows[i][1])
        naive.append(anchor)
        dates.append(datetime.fromtimestamp(rows[i][0] * 604800, tz=timezone.utc).date().isoformat())
    metrics = metric_block(pred, actual, naive)
    metrics.update({
        "n_weeks_total": len(rows),
        "walk_forward_n": len(pred),
        "walk_forward_start": dates[0],
        "walk_forward_end": dates[-1],
    })

    x_all, means, sds = design(rows)
    beta = fit(x_all, [math.log(r[1]) for r in rows], lam)
    last_week, last_copper, last_macro = raw[-1]
    live_values = [math.log(last_copper)] + last_macro
    live_x = [1.0] + [(v - m) / s for v, m, s in zip(live_values, means, sds)]
    raw_live = math.exp(sum(a * b for a, b in zip(live_x, beta)))
    live_value = blended(raw_live, last_copper, weight)

    basic_gate = metrics["r2"] >= MIN_R2 and metrics["mape_pct"] <= MAX_MAPE
    benchmark_gate = (
        weight > 0.0
        and metrics["skill_vs_naive_mse_pct"] > 0.0
        and metrics["mape_pct"] < metrics["naive_mape_pct"]
    )
    publication_ok = basic_gate and benchmark_gate

    output = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "model": "copper-weekly-benchmark-aware-ridge-v2",
        "frequency": "weekly",
        "forecast_horizon_weeks": 1,
        "target": TARGET,
        "target_source": copper_url,
        "series": SERIES,
        "predictor_sources": {"LAG_COPPER_LOG": copper_url, **urls},
        "beta": beta,
        "means": means,
        "sds": sds,
        "ridge_lambda": lam,
        "blend_weight_vs_persistence": weight,
        "selection": {
            "protocol": "validation-only hyperparameter and persistence-blend selection; final 260 weeks untouched",
            "validation_weeks": VALIDATION_WEEKS,
            "final_oos_weeks": FINAL_OOS_WEEKS,
            "ridge_candidates": RIDGE_CANDIDATES,
            "blend_weights": BLEND_WEIGHTS,
            "selected_validation_metrics": selected["validation"],
        },
        "metrics": metrics,
        "walk_forward_gate": "PASS" if basic_gate else "FAIL",
        "benchmark_gate": "PASS" if benchmark_gate else "FAIL",
        "publication_status": "CALIBRATED" if publication_ok else "PROVISIONAL",
        "live": {
            "as_of_week": datetime.fromtimestamp(last_week * 604800, tz=timezone.utc).date().isoformat(),
            "anchor_usd_lb": round(last_copper, 6),
            "raw_model_fair_value_usd_lb": round(raw_live, 6),
            "raw_model_fair_value_usd_t": round(raw_live * 2204.62262185, 2),
            "fair_value_usd_lb": round(live_value, 6),
            "fair_value_usd_t": round(live_value * 2204.62262185, 2),
            "predicted_return_pct": round((live_value / last_copper - 1.0) * 100.0, 3),
        },
        "rules": {
            "min_training_weeks": MIN_TRAIN,
            "validation_weeks": VALIDATION_WEEKS,
            "final_oos_weeks": FINAL_OOS_WEEKS,
            "max_mape_pct": MAX_MAPE,
            "min_r2": MIN_R2,
            "must_beat_naive_mape": True,
            "must_have_positive_skill_vs_naive_mse": True,
            "naive_benchmark": "persistence: next weekly close equals previous observed weekly close",
            "accuracy_definition": "100 - final out-of-sample MAPE; descriptive only, not a probability",
            "lookahead": "none; predictors and target anchor are from information available before the forecast week",
            "missing_data": "complete-case only; no imputation",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(output, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(output, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
