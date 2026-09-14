#!/usr/bin/env python3
"""Historical calibration of the gold physical/fundamentals overlay.

Purpose
-------
Estimate the next-quarter gold-price return associated with *already published*
World Gold Council quarterly fundamentals.  For each usable WGC quarter q, the
features are from q and the target is the average COMEX gold price in q+1 versus
q.  This enforces a one-quarter publication lag and avoids look-ahead.

The public output stores model coefficients/metrics and source coverage only; it
does not republish the WGC historical table.
"""
from __future__ import annotations

import html
import json
import math
import re
import statistics
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / "docs/gold/data/fundamentals_calibration.json"
UA = "Mozilla/5.0 GoldEquilibriumPrice/3.0"
START_YEAR = 2017
RIDGE = 1.5
MIN_TRAIN = 12
MIN_OOS = 12


def get_text(url: str, timeout: int = 45) -> str:
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": UA,
            "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
        },
    )
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")


class LinkParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.links = []
        self._href = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() == "a":
            self._href = dict(attrs).get("href")
            self._parts = []

    def handle_data(self, data):
        if self._href is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        if tag.lower() == "a" and self._href is not None:
            self.links.append((" ".join(self._parts).strip(), self._href))
            self._href = None
            self._parts = []


class TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables = []
        self._table = None
        self._row = None
        self._cell = None
        self._parts = []

    def handle_starttag(self, tag, attrs):
        t = tag.lower()
        if t == "table":
            self._table = []
        elif t == "tr" and self._table is not None:
            self._row = []
        elif t in ("td", "th") and self._row is not None:
            self._cell = t
            self._parts = []

    def handle_data(self, data):
        if self._cell is not None:
            self._parts.append(data)

    def handle_endtag(self, tag):
        t = tag.lower()
        if t in ("td", "th") and self._cell is not None:
            text = " ".join(self._parts)
            text = html.unescape(text).replace("\u00a0", " ")
            text = re.sub(r"\s+", " ", text).strip()
            self._row.append(text)
            self._cell = None
            self._parts = []
        elif t == "tr" and self._row is not None:
            if self._row:
                self._table.append(self._row)
            self._row = None
        elif t == "table" and self._table is not None:
            if self._table:
                self.tables.append(self._table)
            self._table = None


def norm(s: str) -> str:
    s = html.unescape(s or "").lower()
    s = s.replace("’", "'").replace("‘", "'").replace("&", "and")
    return re.sub(r"[^a-z0-9'+.-]+", " ", s).strip()


def number(s: str):
    if not s:
        return None
    x = html.unescape(s).replace("−", "-").replace("–", "-")
    m = re.search(r"(?<![\d])(-?\d[\d,]*(?:\.\d+)?)", x)
    if not m:
        return None
    try:
        return float(m.group(1).replace(",", ""))
    except ValueError:
        return None


def quarter_markers(year: int, q: int):
    yy = str(year)[-2:]
    return {
        norm(f"Q{q}'{yy}"),
        norm(f"Q{q}’{yy}"),
        norm(f"Q{q} {year}"),
        norm(f"Q{q}{year}"),
    }


def target_col(table, year: int, q: int):
    marks = quarter_markers(year, q)
    for row in table[:6]:
        for j, cell in enumerate(row):
            c = norm(cell)
            if c in marks or any(m in c for m in marks if len(m) >= 5):
                return j
    return None


def row_value(tables, year: int, q: int, labels):
    labels = [norm(x) for x in labels]
    for table in tables:
        j = target_col(table, year, q)
        if j is None:
            continue
        for row in table:
            if not row:
                continue
            lab = norm(row[0])
            if any(x == lab or x in lab for x in labels):
                if j < len(row):
                    v = number(row[j])
                    if v is not None:
                        return v
    return None


def text_fallback(text: str, patterns):
    flat = html.unescape(re.sub(r"<[^>]+>", " ", text)).replace("\u00a0", " ")
    flat = re.sub(r"\s+", " ", flat)
    for p in patterns:
        m = re.search(p, flat, flags=re.I)
        if m:
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                pass
    return None


def report_url(year: int, q: int) -> str:
    return f"https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q{q}-{year}"


def section_links(base: str, main_html: str):
    p = LinkParser(); p.feed(main_html)
    out = {}
    for text, href in p.links:
        t = norm(text)
        if not href:
            continue
        u = urllib.parse.urljoin(base, href)
        if "gold.org/goldhub/research/gold-demand-trends" not in u:
            continue
        if t == "supply" or t.endswith(" supply"):
            out.setdefault("supply", u)
        elif t == "investment" or t.endswith(" investment"):
            out.setdefault("investment", u)
        elif "central bank" in t:
            out.setdefault("central", u)
    # Modern pages often expose semantic child paths; these are safe fallbacks.
    out.setdefault("supply", base.rstrip("/") + "/supply")
    out.setdefault("investment", base.rstrip("/") + "/investment")
    out.setdefault("central", base.rstrip("/") + "/central-banks")
    return out


def parse_tables(doc: str):
    p = TableParser(); p.feed(doc); return p.tables


def scrape_quarter(year: int, q: int):
    base = report_url(year, q)
    main = get_text(base)
    links = section_links(base, main)
    docs = {"main": main}
    for key in ("supply", "investment", "central"):
        candidates = [links[key]]
        if key == "central":
            candidates += [base.rstrip("/") + "/central-banks-and-other-institutions"]
        last = None
        for u in candidates:
            try:
                docs[key] = get_text(u)
                links[key] = u
                last = None
                break
            except Exception as e:
                last = e
        if key not in docs and last:
            raise last
        time.sleep(0.05)

    st = parse_tables(docs["supply"])
    it = parse_tables(docs["investment"])
    ct = parse_tables(docs["central"])

    total_supply = row_value(st, year, q, ["Total supply"])
    recycled = row_value(st, year, q, ["Recycled gold", "Recycling"])
    hedging = row_value(st, year, q, ["Net producer hedging", "Producer hedging"])
    barcoin = row_value(it, year, q, ["Total bar & coin demand", "Total bar and coin demand", "Bar and coin"])
    etf = row_value(it, year, q, ["ETFs & similar products", "ETFs and similar products", "Gold-backed ETFs", "ETFs"])
    cb = row_value(ct, year, q, ["Central banks & others", "Central banks and other institutions", "Central banks"])

    # Narrative fallbacks are intentionally narrow and used only when the exact
    # quarterly table cannot be parsed. No interpolation or synthetic value is used.
    if total_supply is None:
        total_supply = text_fallback(docs["main"], [rf"supply[^.]*?(?:to|at)\s*([\d,]+(?:\.\d+)?)\s*t"])
    if recycled is None:
        recycled = text_fallback(docs["supply"], [r"recycl(?:ed|ing)[^.]*?(?:to|at|of)\s*([\d,]+(?:\.\d+)?)\s*(?:t|tonnes)"])
    if barcoin is None:
        barcoin = text_fallback(docs["main"], [r"bar\s+and\s+coin[^.]*?(?:to|at|of)\s*([\d,]+(?:\.\d+)?)\s*t"])
    if etf is None:
        etf = text_fallback(docs["main"], [r"ETF(?:s)?[^.]*?(?:inflows|outflows|grew|fell|of)\s*(?:by|of|to)?\s*(-?[\d,]+(?:\.\d+)?)\s*t"])
    if cb is None:
        cb = text_fallback(docs["main"], [r"central banks?[^.]*?(?:added|purchased|bought|buying|purchases)[^.]*?([\d,]+(?:\.\d+)?)\s*t"])

    values = {
        "total_supply_t": total_supply,
        "recycled_gold_t": recycled,
        "producer_hedging_t": hedging,
        "bar_coin_t": barcoin,
        "etf_t": etf,
        "central_banks_t": cb,
    }
    required = ("total_supply_t", "recycled_gold_t", "bar_coin_t", "etf_t", "central_banks_t")
    if any(values[k] is None for k in required):
        missing = [k for k in required if values[k] is None]
        raise RuntimeError(f"missing {missing}")
    return values, {"report": base, **links}


def yahoo_weekly(symbol="GC=F"):
    q = urllib.parse.quote(symbol, safe="")
    now = int(datetime.now(timezone.utc).timestamp()) + 86400
    start = int(datetime(2016, 1, 1, tzinfo=timezone.utc).timestamp())
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1={start}&period2={now}&interval=1wk&events=history&includeAdjustedClose=true"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=60) as r:
        j = json.loads(r.read().decode())
    res = ((j.get("chart") or {}).get("result") or [None])[0]
    if not res:
        raise RuntimeError("Yahoo gold history unavailable")
    ts = res.get("timestamp") or []
    close = (((res.get("indicators") or {}).get("quote") or [{}])[0].get("close") or [])
    out = []
    for t, v in zip(ts, close):
        if v is None:
            continue
        v = float(v)
        if not math.isfinite(v) or v <= 0:
            continue
        d = datetime.fromtimestamp(t, tz=timezone.utc)
        qtr = (d.month - 1) // 3 + 1
        out.append((d.year, qtr, v))
    return out, url


def quarterly_gold(weeks):
    box = {}
    for y, q, v in weeks:
        box.setdefault((y, q), []).append(v)
    return {k: statistics.fmean(v) for k, v in box.items() if len(v) >= 8}


def next_q(y, q):
    return (y + 1, 1) if q == 4 else (y, q + 1)


def solve(A, b):
    n = len(b); M = [A[i][:] + [b[i]] for i in range(n)]
    for c in range(n):
        p = max(range(c, n), key=lambda r: abs(M[r][c])); M[c], M[p] = M[p], M[c]
        z = M[c][c]
        if abs(z) < 1e-12:
            raise RuntimeError("singular matrix")
        M[c] = [v / z for v in M[c]]
        for r in range(n):
            if r == c:
                continue
            z = M[r][c]
            M[r] = [M[r][j] - z * M[c][j] for j in range(n + 1)]
    return [M[i][-1] for i in range(n)]


def design(rows):
    cols = list(zip(*[r["x"] for r in rows]))
    mu = [statistics.fmean(c) for c in cols]
    sd = [statistics.pstdev(c) or 1.0 for c in cols]
    X = [[1.0] + [(v - m) / s for v, m, s in zip(r["x"], mu, sd)] for r in rows]
    return X, mu, sd


def fit(X, y, lam=RIDGE):
    p = len(X[0]); A = [[0.0] * p for _ in range(p)]; b = [0.0] * p
    for x, t in zip(X, y):
        for i in range(p):
            b[i] += x[i] * t
            for j in range(p):
                A[i][j] += x[i] * x[j]
    for i in range(1, p):
        A[i][i] += lam
    return solve(A, b)


def features(w):
    supply = max(w["total_supply_t"], 1.0)
    strategic = w["bar_coin_t"] + w["etf_t"] + w["central_banks_t"]
    return [
        strategic / supply,
        w["recycled_gold_t"] / supply,
        (w["producer_hedging_t"] or 0.0) / supply,
    ]


def predict(x, beta, mu, sd):
    z = [1.0] + [(v - m) / s for v, m, s in zip(x, mu, sd)]
    return sum(a * b for a, b in zip(z, beta))


def main():
    now = datetime.now(timezone.utc)
    latest_completed_q = (now.month - 1) // 3
    latest_year = now.year
    if latest_completed_q == 0:
        latest_completed_q = 4; latest_year -= 1

    weeks, gold_url = yahoo_weekly()
    gq = quarterly_gold(weeks)
    observations = []
    coverage = []
    failures = []

    # Q1-Q3 are deliberately preferred. In many full-year reports the section
    # tables switch to annual columns, making a Q4 value ambiguous. We reject
    # ambiguity rather than infer a quarter from an annual table.
    for year in range(START_YEAR, latest_year + 1):
        for q in (1, 2, 3):
            if (year, q) > (latest_year, latest_completed_q):
                continue
            try:
                w, sources = scrape_quarter(year, q)
                nq = next_q(year, q)
                if (year, q) not in gq or nq not in gq:
                    raise RuntimeError("quarterly gold average unavailable")
                observations.append({
                    "period": f"{year}-Q{q}",
                    "x": features(w),
                    "gold_anchor": gq[(year, q)],
                    "gold_next": gq[nq],
                    "target_return": math.log(gq[nq] / gq[(year, q)]),
                })
                coverage.append(f"{year}-Q{q}")
            except Exception as e:
                failures.append({"period": f"{year}-Q{q}", "reason": str(e)[:180]})

    if len(observations) < MIN_TRAIN + MIN_OOS:
        raise RuntimeError(f"insufficient exact WGC observations: {len(observations)}")

    pred_price = []; actual = []; naive = []; directions = []; periods = []
    for i in range(MIN_TRAIN, len(observations)):
        tr = observations[:i]
        X, mu, sd = design(tr)
        beta = fit(X, [r["target_return"] for r in tr])
        r = observations[i]
        pr = predict(r["x"], beta, mu, sd)
        pp = r["gold_anchor"] * math.exp(pr)
        pred_price.append(pp); actual.append(r["gold_next"]); naive.append(r["gold_anchor"])
        actual_ret = math.log(r["gold_next"] / r["gold_anchor"])
        directions.append(1 if (pr >= 0) == (actual_ret >= 0) else 0)
        periods.append(r["period"])

    X, mu, sd = design(observations)
    beta = fit(X, [r["target_return"] for r in observations])
    mape = 100 * statistics.fmean(abs((a - p) / a) for a, p in zip(actual, pred_price))
    naive_mape = 100 * statistics.fmean(abs((a - p) / a) for a, p in zip(actual, naive))
    rmse = math.sqrt(statistics.fmean((a - p) ** 2 for a, p in zip(actual, pred_price)))
    mse = statistics.fmean((a - p) ** 2 for a, p in zip(actual, pred_price))
    naive_mse = statistics.fmean((a - p) ** 2 for a, p in zip(actual, naive))
    skill = 100 * (1 - mse / naive_mse) if naive_mse else 0.0
    direction = 100 * statistics.fmean(directions)
    mean_a = statistics.fmean(actual)
    denom = sum((a - mean_a) ** 2 for a in actual)
    r2 = 1 - sum((a - p) ** 2 for a, p in zip(actual, pred_price)) / denom if denom else 0.0

    passed = (
        len(actual) >= MIN_OOS
        and mape <= 12.0
        and direction >= 45.0
        and skill >= -10.0
    )

    out = {
        "generated_at_utc": now.isoformat(),
        "model": "wgc-quarterly-physical-overlay-ridge-v1",
        "frequency": "quarterly",
        "feature_period": "quarter q fundamentals",
        "target": "average COMEX GC=F price in q+1 versus q",
        "features": ["strategic_demand_share", "recycling_share", "producer_hedging_share"],
        "beta": beta,
        "means": mu,
        "sds": sd,
        "ridge_lambda": RIDGE,
        "metrics": {
            "wgc_quarters_exact": len(observations),
            "walk_forward_n": len(actual),
            "walk_forward_start_feature_period": periods[0],
            "walk_forward_end_feature_period": periods[-1],
            "price_r2": round(r2, 4),
            "price_mape_pct": round(mape, 3),
            "naive_mape_pct": round(naive_mape, 3),
            "rmse_usd_oz": round(rmse, 2),
            "skill_vs_naive_mse_pct": round(skill, 2),
            "direction_accuracy_pct": round(direction, 2),
        },
        "walk_forward_gate": "PASS" if passed else "FAIL",
        "publication_status": "CALIBRATED" if passed else "PROVISIONAL",
        "coverage": {
            "first": coverage[0] if coverage else None,
            "last": coverage[-1] if coverage else None,
            "period_count": len(coverage),
            "q4_policy": "excluded when quarterly table is ambiguous in full-year reports",
            "failed_period_count": len(failures),
            "failed_periods": failures,
        },
        "sources": {
            "fundamentals": "World Gold Council public Gold Demand Trends quarterly report section tables",
            "gold_price": gold_url,
        },
        "rules": {
            "publication_lag": "features from q predict q+1; no same-quarter WGC look-ahead",
            "missing_data": "exact observations only; no interpolation or imputation",
            "min_training_quarters": MIN_TRAIN,
            "min_oos_quarters": MIN_OOS,
            "max_price_mape_pct": 12.0,
            "min_direction_accuracy_pct": 45.0,
            "min_skill_vs_naive_mse_pct": -10.0,
            "copyright": "historical WGC row-level data are not republished; only model coefficients, metrics and coverage metadata are stored",
        },
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(out, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
