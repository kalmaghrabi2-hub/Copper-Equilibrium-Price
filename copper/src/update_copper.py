#!/usr/bin/env python3
from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import date, datetime, time, timedelta, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WESTMETALL_URL = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"
OUTPUT = ROOT / "docs/copper/data/latest.json"
CAL = ROOT / "docs/copper/data/weekly_calibration.json"
INDEX = ROOT / "docs/index.html"
STRUCTURAL_PSTAR = 10469.088447
MARKET_CLOSE_CUTOFF_UTC = time(18, 0)

V15_GOVERNANCE = {
    "market_months_continuous": 80,
    "exact_public_icsg_months": 35,
    "longest_consecutive_icsg_months": 11,
    "minimum_consecutive_required": 36,
    "no_imputation": True,
    "publication_lag_control": True,
    "monthly_fundamental_walk_forward": "BLOCKED",
    "final_calibrated_daily_pstar": "BLOCKED",
}


class TableParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.in_cell = False
        self.in_row = False
        self.cell = []
        self.row = []
        self.rows = []

    def handle_starttag(self, tag, attrs):
        if tag == "tr":
            self.in_row = True
            self.row = []
        elif tag in ("td", "th") and self.in_row:
            self.in_cell = True
            self.cell = []

    def handle_data(self, data):
        if self.in_cell:
            self.cell.append(data)

    def handle_endtag(self, tag):
        if tag in ("td", "th") and self.in_cell:
            text = html.unescape(" ".join(self.cell)).strip()
            self.row.append(re.sub(r"\s+", " ", text))
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Copper-Equilibrium-Price/2.1",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as response:
        return response.read().decode("utf-8", errors="replace")


def num(value: str) -> float:
    return float(value.replace(",", "").strip())


def previous_weekday(day: date) -> date:
    day -= timedelta(days=1)
    while day.weekday() >= 5:
        day -= timedelta(days=1)
    return day


def expected_latest_completed_day(now_utc: datetime) -> date:
    today = now_utc.date()
    if today.weekday() >= 5:
        while today.weekday() >= 5:
            today -= timedelta(days=1)
        return today
    if now_utc.time() >= MARKET_CLOSE_CUTOFF_UTC:
        return today
    return previous_weekday(today)


def parse_latest(html_text: str) -> dict:
    parser = TableParser()
    parser.feed(html_text)
    month_map = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }
    date_re = re.compile(r"^(\d{1,2})\.\s+([A-Za-z]+)\s+(\d{4})$")
    for row in parser.rows:
        if len(row) < 4:
            continue
        match = date_re.match(row[0])
        if not match or match.group(2) not in month_map:
            continue
        dt = datetime(int(match.group(3)), month_map[match.group(2)], int(match.group(1)))
        cash = num(row[1])
        three_m = num(row[2])
        stock = int(round(num(row[3])))
        if cash <= 0 or three_m <= 0 or stock < 0:
            continue
        return {
            "as_of": dt.date().isoformat(),
            "lme_cash_usd_t": cash,
            "lme_3m_usd_t": three_m,
            "lme_stock_t": stock,
            "cash_3m_spread_usd_t": round(cash - three_m, 6),
            "curve_state": "backwardation" if cash > three_m else ("contango" if cash < three_m else "flat"),
            "source": "Westmetall public validation proxy",
            "source_url": WESTMETALL_URL,
        }
    raise RuntimeError("No valid copper market row found in Westmetall table")


def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def fmt_price(value: float, decimals: int = 2) -> str:
    return f"${value:,.{decimals}f}/t"


def fmt_pct(value) -> str:
    return "—" if value is None else f"{float(value):.2f}%"


def update_index(data: dict) -> None:
    if not INDEX.exists():
        raise RuntimeError("docs/index.html is missing")
    text = INDEX.read_text(encoding="utf-8")
    market = data["market"]
    model = data["model"]
    structural = data["structural_model"]
    metrics = ((data.get("calibration") or {}).get("metrics") or {})
    structural_gap = float(structural["market_vs_structural_pstar_pct"])
    status = data.get("data_status", "UNKNOWN")

    replacements = [
        (
            r'(<span class="muted">LME Cash — public validation proxy</span><strong class="copper">).*?(</strong><small>).*?(</small>)',
            rf'\g<1>{fmt_price(market["lme_cash_usd_t"])}\g<2>آخر مجموعة كاملة موثقة: {data["as_of"]} · {status}\g<3>',
        ),
        (
            r'(<span class="muted">(?:Calibrated market P\*|Structural P\*)</span><strong class="green">).*?(</strong><small>).*?(</small>)',
            rf'\g<1>{fmt_price(structural["p_star_usd_t"], 0)}\g<2>Structural P* · PROVISIONAL · monthly walk-forward BLOCKED\g<3>',
        ),
        (
            r'(<span class="muted">Market vs P\*</span><strong class="red">).*?(</strong><small>).*?(</small>)',
            rf'\g<1>{structural_gap:+.1f}%\g<2>{"السوق أعلى من Structural P*" if structural_gap >= 0 else "السوق أدنى من Structural P*"}\g<3>',
        ),
        (r'(<div class="row"><span>LME 3M</span><b>).*?(</b></div>)', rf'\g<1>{fmt_price(market["lme_3m_usd_t"], 0)}\g<2>'),
        (r'(<div class="row"><span>LME Stocks</span><b>).*?(</b></div>)', rf'\g<1>{int(market["lme_stock_t"]):,} t\g<2>'),
        (r'(<div class="row"><span>OOS accuracy \(100 − MAPE\)</span><b>).*?(</b></div>)', rf'\g<1>{fmt_pct(metrics.get("accuracy_pct"))}\g<2>'),
        (r'(<div class="row"><span>Model MAPE</span><b>).*?(</b></div>)', rf'\g<1>{fmt_pct(metrics.get("mape_pct"))}\g<2>'),
        (r'(<div class="row"><span>Naive MAPE</span><b>).*?(</b></div>)', rf'\g<1>{fmt_pct(metrics.get("naive_mape_pct"))}\g<2>'),
        (r'(<div class="row"><span>Skill vs naive MSE</span><b[^>]*>).*?(</b></div>)', rf'\g<1>{fmt_pct(metrics.get("skill_vs_naive_mse_pct"))}\g<2>'),
        (r'(<div class="row"><span>Direction accuracy</span><b>).*?(</b></div>)', rf'\g<1>{fmt_pct(metrics.get("direction_accuracy_pct"))}\g<2>'),
        (r'(<div class="row"><span>Benchmark gate</span><b[^>]*>).*?(</b></div>)', rf'\g<1>{(data.get("calibration") or {}).get("benchmark_gate", "PENDING")}\g<2>'),
    ]

    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
        if count != 1:
            raise RuntimeError(f"Dashboard pattern did not match exactly once: {pattern[:70]}")

    INDEX.write_text(text, encoding="utf-8")


def main() -> None:
    previous = load_json(OUTPUT)
    now_utc = datetime.now(timezone.utc).replace(microsecond=0)
    stale_reason = None

    try:
        market = parse_latest(fetch_text(WESTMETALL_URL))
        expected_day = expected_latest_completed_day(now_utc)
        observed_day = date.fromisoformat(market["as_of"])
        if observed_day < expected_day:
            data_status = "STALE_LAST_VERIFIED"
            stale_reason = (
                f"Configured public validation source latest complete row is {observed_day.isoformat()}, "
                f"while the latest expected completed weekday is {expected_day.isoformat()}; "
                "missing required full Cash/3M/Stocks set was not fabricated."
            )
        else:
            data_status = "FRESH_PUBLIC_PROXY"
    except Exception as exc:
        if previous is None or not previous.get("market"):
            raise
        market = previous["market"]
        data_status = "STALE_LAST_VERIFIED"
        stale_reason = str(exc)[:240]

    calibration = load_json(CAL)
    live = (calibration or {}).get("live") or {}
    calibrated = float(live.get("fair_value_usd_t") or STRUCTURAL_PSTAR)
    weekly_gate = (calibration or {}).get("walk_forward_gate") or "PENDING"
    benchmark_gate = (calibration or {}).get("benchmark_gate") or "PENDING"
    metrics = (calibration or {}).get("metrics") or {}

    # Weekly market-reference layer remains reference-only unless all its hard gates pass.
    valid_market_layer = weekly_gate == "PASS" and benchmark_gate == "PASS"
    weekly_status = "VALID" if valid_market_layer else "PROVISIONAL"
    calibrated_gap = market["lme_cash_usd_t"] / calibrated - 1.0
    structural_gap = market["lme_cash_usd_t"] / STRUCTURAL_PSTAR - 1.0

    data = {
        "as_of": market["as_of"],
        "generated_at_utc": now_utc.isoformat(),
        "engine_version": "copper-benchmark-aware-2.1",
        "data_status": data_status,
        "market": market,
        "calibration": calibration,
        "model": {
            "calibrated_p_star_usd_t": round(calibrated, 2),
            "calibrated_p_star_usd_lb": round(calibrated / 2204.62262185, 6),
            "market_vs_pstar_pct": round(calibrated_gap * 100.0, 6),
            "status": "PROVISIONAL",
            "confidence": "LOW",
            "publication_role": "REFERENCE_ONLY",
            "accuracy": {
                "oos_accuracy_pct": metrics.get("accuracy_pct"),
                "mape_pct": metrics.get("mape_pct"),
                "naive_mape_pct": metrics.get("naive_mape_pct"),
                "skill_vs_naive_mse_pct": metrics.get("skill_vs_naive_mse_pct"),
                "direction_accuracy_pct": metrics.get("direction_accuracy_pct"),
                "definition": "100 - final out-of-sample MAPE; descriptive, not a probability",
            },
            "governance": {
                "weekly_walk_forward": weekly_gate,
                "benchmark_gate": benchmark_gate,
                "publication_gate": "REFERENCE_ONLY" if not valid_market_layer else "VALID_MARKET_REFERENCE_ONLY",
                "equilibrium_claim": "WITHHELD_NOT_VALIDATED",
                "no_imputation": True,
            },
        },
        "structural_model": {
            "p_star_usd_t": STRUCTURAL_PSTAR,
            "p_star_usd_lb": round(STRUCTURAL_PSTAR / 2204.62262185, 6),
            "market_vs_structural_pstar_pct": round(structural_gap * 100.0, 6),
            "residual_structural_gap_mt": 2.711236079,
            "optimistic_usd_t": 8599.16355,
            "stress_lower_bound_usd_t": 24500.0,
            "status": "PROVISIONAL_DIAGNOSTIC_ONLY",
            "weight_in_calibrated_pstar": 0.0,
        },
        "governance": {
            "model_status": "PROVISIONAL",
            "structural_fundamental_status": "PROVISIONAL",
            "failed_or_unvalidated_layers_have_zero_price_weight": True,
            **V15_GOVERNANCE,
        },
        "model_status": "PROVISIONAL",
    }
    if stale_reason:
        data["stale_reason"] = stale_reason

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_index(data)
    print(json.dumps({
        "ok": True,
        "as_of": data.get("as_of"),
        "data_status": data_status,
        "model_status": "PROVISIONAL",
        "market_vs_structural_pstar_pct": data["structural_model"]["market_vs_structural_pstar_pct"],
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
