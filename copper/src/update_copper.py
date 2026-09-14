from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

WESTMETALL_URL = "https://www.westmetall.com/en/markdaten.php?action=table&field=LME_Cu_cash"
OUTPUT = Path("docs/copper/data/latest.json")
INDEX = Path("docs/index.html")
STRUCTURAL_PSTAR = 10469.088447


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
            text = re.sub(r"\s+", " ", text)
            self.row.append(text)
            self.in_cell = False
        elif tag == "tr" and self.in_row:
            if self.row:
                self.rows.append(self.row)
            self.in_row = False


def fetch_text(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 Copper-Equilibrium-Price/1.0",
            "Accept": "text/html,application/xhtml+xml",
        },
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", errors="replace")


def num(s: str) -> float:
    return float(s.replace(",", "").strip())


def parse_latest(html_text: str) -> dict:
    p = TableParser()
    p.feed(html_text)
    month_map = {
        "January": 1, "February": 2, "March": 3, "April": 4,
        "May": 5, "June": 6, "July": 7, "August": 8,
        "September": 9, "October": 10, "November": 11, "December": 12,
    }
    date_re = re.compile(r"^(\d{1,2})\.\s+([A-Za-z]+)\s+(\d{4})$")
    for row in p.rows:
        if len(row) < 4:
            continue
        m = date_re.match(row[0])
        if not m or m.group(2) not in month_map:
            continue
        dt = datetime(int(m.group(3)), month_map[m.group(2)], int(m.group(1)))
        cash = num(row[1])
        three_m = num(row[2])
        stock = int(round(num(row[3])))
        if cash <= 0 or three_m <= 0 or stock < 0:
            continue
        gap = cash / STRUCTURAL_PSTAR - 1.0
        spread = cash - three_m
        return {
            "as_of": dt.date().isoformat(),
            "market": {
                "lme_cash_usd_t": cash,
                "lme_3m_usd_t": three_m,
                "lme_stock_t": stock,
                "cash_3m_spread_usd_t": round(spread, 6),
                "curve_state": "backwardation" if spread > 0 else ("contango" if spread < 0 else "flat"),
                "source": "Westmetall public validation proxy",
                "source_url": WESTMETALL_URL,
            },
            "structural_model": {
                "p_star_usd_t": STRUCTURAL_PSTAR,
                "p_star_usd_lb": round(STRUCTURAL_PSTAR / 2204.62262185, 6),
                "market_vs_pstar_pct": round(gap * 100.0, 6),
                "residual_structural_gap_mt": 2.711236079,
                "optimistic_usd_t": 8599.16355,
                "stress_lower_bound_usd_t": 24500.0,
            },
            "governance": {
                "model_status": "PROVISIONAL",
                "confidence": "LOW",
                "final_daily_pstar_published": False,
                "walk_forward": "BLOCKED",
                "market_months": 80,
                "exact_public_icsg_months": 35,
                "longest_consecutive_icsg_months": 11,
                "minimum_consecutive_required": 36,
                "no_imputation": True,
                "publication_lag_control": True,
                "reason": "Final calibrated daily P* remains blocked until >=36 consecutive complete monthly fundamentals pass look-ahead-safe walk-forward validation.",
            },
        }
    raise RuntimeError("No valid copper market row found in Westmetall table")


def load_previous() -> dict | None:
    if not OUTPUT.exists():
        return None
    try:
        return json.loads(OUTPUT.read_text(encoding="utf-8"))
    except Exception:
        return None


def fmt_price(v: float, decimals: int = 2) -> str:
    return f"${v:,.{decimals}f}/t"


def update_index(data: dict) -> None:
    if not INDEX.exists():
        raise RuntimeError("docs/index.html is missing")
    text = INDEX.read_text(encoding="utf-8")
    m = data["market"]
    s = data["structural_model"]
    gap = float(s["market_vs_pstar_pct"])
    status = data.get("data_status", "UNKNOWN")

    replacements = [
        (
            r'(<span class="muted">LME Cash — public validation proxy</span><strong class="copper">).*?(</strong><small>).*?(</small>)',
            rf'\g<1>{fmt_price(m["lme_cash_usd_t"])}\g<2>آخر جلسة موثقة داخل المحرك: {data["as_of"]} · {status}\g<3>',
        ),
        (
            r'(<span class="muted">Market vs P\*</span><strong class="red">).*?(</strong><small>).*?(</small>)',
            rf'\g<1>{gap:+.1f}%\g<2>{"السوق أعلى من التوازن الهيكلي" if gap >= 0 else "السوق أدنى من التوازن الهيكلي"}\g<3>',
        ),
        (
            r'(<div class="row"><span>LME 3M</span><b>).*?(</b></div>)',
            rf'\g<1>{fmt_price(m["lme_3m_usd_t"], 0)}\g<2>',
        ),
        (
            r'(<div class="row"><span>LME Stocks</span><b>).*?(</b></div>)',
            rf'\g<1>{int(m["lme_stock_t"]):,} t\g<2>',
        ),
    ]

    for pattern, replacement in replacements:
        text, count = re.subn(pattern, replacement, text, count=1, flags=re.S)
        if count != 1:
            raise RuntimeError(f"Dashboard pattern did not match exactly once: {pattern[:50]}")

    INDEX.write_text(text, encoding="utf-8")


def main() -> None:
    previous = load_previous()
    try:
        data = parse_latest(fetch_text(WESTMETALL_URL))
        data["data_status"] = "FRESH_PUBLIC_PROXY"
    except Exception as exc:
        if previous is None:
            raise
        data = previous
        data["data_status"] = "STALE_LAST_VERIFIED"
        data["stale_reason"] = str(exc)[:240]

    data["engine_version"] = "copper-daily-1.1"
    data["generated_at_utc"] = datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    update_index(data)
    print(json.dumps({"ok": True, "as_of": data.get("as_of"), "status": data.get("data_status")}, ensure_ascii=False))


if __name__ == "__main__":
    main()
