#!/usr/bin/env python3
"""Gold equilibrium price pipeline — provisional public-data implementation.

The model deliberately separates:
1) daily market layer (XAU/USD),
2) daily macro layer (FRED),
3) quarterly physical/sectoral fundamentals (World Gold Council),
4) governance gates.

No missing critical value is fabricated. If a feed fails, status is downgraded.
"""
from __future__ import annotations

import csv
import io
import json
import math
import re
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

OUT = Path(__file__).resolve().parents[2] / "docs" / "gold" / "data" / "latest.json"
UA = "GoldEquilibriumPrice/0.1 (+https://github.com/kalmaghrabi2-hub/copper-equilibrium-price)"

def get_text(url: str, timeout: int = 25) -> str:
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept": "*/*"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read().decode("utf-8", errors="replace")

def get_json(url: str) -> dict:
    return json.loads(get_text(url))

def latest_fred(series: str) -> dict:
    url = f"https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}"
    rows = list(csv.DictReader(io.StringIO(get_text(url))))
    for row in reversed(rows):
        raw = (row.get(series) or "").strip()
        if raw not in ("", "."):
            return {"series": series, "date": row["DATE"], "value": float(raw), "source": url}
    raise RuntimeError(f"No valid FRED observation for {series}")

def fetch_spot() -> dict:
    try:
        j = get_json("https://xaus.com/api/v1/spot?compact=1")
        value = j.get("spot_usd_oz") or (j.get("xau") or {}).get("price")
        ds = j.get("data_state") or {}
        if value is None:
            raise RuntimeError("XAUS response missing price")
        return {"usd_oz": float(value), "as_of": ds.get("as_of") or j.get("updated_at"), "freshness_status": ds.get("status", "unknown"), "age_seconds": ds.get("age_seconds"), "provider": "XAUS", "source": "https://xaus.com/api/v1/spot"}
    except Exception as first_error:
        j = get_json("https://api.gold-api.com/price/XAU")
        value = j.get("price")
        if value is None:
            raise RuntimeError(f"Both spot feeds failed; primary error={first_error}")
        return {"usd_oz": float(value), "as_of": j.get("updatedAt") or j.get("updated_at"), "freshness_status": "fallback", "age_seconds": None, "provider": "Gold API", "source": "https://api.gold-api.com/price/XAU"}

def candidate_wgc_urls(now: datetime) -> list[str]:
    q = ((now.month - 1) // 3) + 1
    y = now.year
    completed_q = q - 1
    if completed_q == 0:
        completed_q, y = 4, y - 1
    candidates = []
    cq, cy = completed_q, y
    for _ in range(6):
        candidates.append(f"https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q{cq}-{cy}")
        cq -= 1
        if cq == 0:
            cq, cy = 4, cy - 1
    return candidates

def parse_wgc_table(html: str, url: str) -> dict:
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text)
    def last_value(label: str) -> float:
        pat = re.escape(label) + r"\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)"
        m = re.search(pat, text, flags=re.I)
        if not m:
            raise RuntimeError(f"Could not parse WGC row: {label}")
        return float(m.group(5).replace(",", ""))
    data = {
        "mine_production_t": last_value("Mine Production"),
        "producer_hedging_t": last_value("Net Producer Hedging"),
        "recycled_gold_t": last_value("Recycled Gold"),
        "total_supply_t": last_value("Total Supply"),
        "jewellery_fabrication_t": last_value("Jewellery Fabrication"),
        "technology_t": last_value("Technology"),
        "investment_t": last_value("Investment"),
        "bar_coin_t": last_value("Total Bar and Coin"),
        "etf_t": last_value("ETFs & Similar Products"),
        "central_banks_t": last_value("Central Banks & Other inst."),
        "gold_demand_ex_otc_t": last_value("Gold Demand"),
        "otc_other_t": last_value("OTC and Other"),
        "total_demand_t": last_value("Total Demand"),
        "quarter_avg_lbma_usd_oz": last_value("LBMA Gold Price (US$/oz)"),
        "source": url,
    }
    qmatch = re.search(r"Gold Demand Trends:\s*Q([1-4])\s*(\d{4})", text, re.I)
    if qmatch:
        data["quarter"] = f"{qmatch.group(2)}-Q{qmatch.group(1)}"
    return data

def fetch_wgc(now: datetime) -> dict:
    errors = []
    for url in candidate_wgc_urls(now):
        try:
            html = get_text(url)
            if "Gold supply and demand" not in html and "Total Supply" not in html:
                raise RuntimeError("quarterly table marker missing")
            return parse_wgc_table(html, url)
        except Exception as e:
            errors.append(f"{url}: {e}")
    raise RuntimeError("WGC quarterly fundamentals unavailable: " + " | ".join(errors))

def build_model(spot: dict, macro: dict, wgc: dict) -> dict:
    supply = max(1.0, wgc["mine_production_t"] + wgc["recycled_gold_t"] + wgc["producer_hedging_t"])
    strategic_demand = 0.35*max(0.0,wgc["central_banks_t"]) + 0.30*max(0.0,wgc["bar_coin_t"]) + 0.20*max(-150.0,wgc["etf_t"]) + 0.15*max(0.0,wgc["technology_t"])
    demand_pressure = max(0.25, strategic_demand / 260.0)
    supply_pressure = max(0.50, supply / 1250.0)
    real_yield = macro["DFII10"]["value"]
    dollar = macro["DTWEXBGS"]["value"]
    breakeven = macro["T10YIE"]["value"]
    vix = macro["VIXCLS"]["value"]
    monetary_multiplier = math.exp(-0.10*(real_yield-2.0) -0.004*(dollar-120.0) +0.05*(breakeven-2.3) +0.006*(vix-20.0))
    eps_d, eps_s = -0.45, 0.20
    physical_multiplier = (demand_pressure / supply_pressure) ** (1.0/(eps_s-eps_d))
    anchor = wgc["quarter_avg_lbma_usd_oz"]
    p_star = anchor * physical_multiplier * monetary_multiplier
    lower, upper = 0.45*spot["usd_oz"], 1.75*spot["usd_oz"]
    gated_p_star = min(max(p_star, lower), upper)
    return {
        "fundamental_p_star_usd_oz": round(gated_p_star,2),
        "raw_phase0_p_star_usd_oz": round(p_star,2),
        "market_vs_pstar_pct": round((spot["usd_oz"]/gated_p_star-1.0)*100.0,2),
        "demand_pressure_index": round(demand_pressure*100.0,3),
        "supply_pressure_index": round(supply_pressure*100.0,3),
        "physical_multiplier": round(physical_multiplier,6),
        "monetary_multiplier": round(monetary_multiplier,6),
        "elasticities": {"demand": eps_d, "supply": eps_s},
        "status": "PROVISIONAL",
        "confidence": "LOW_UNTIL_BACKTEST",
        "governance": {"historical_calibration":"PENDING","walk_forward":"PENDING","no_imputation":True,"publication_gate":"PROVISIONAL_ONLY"},
    }

def main() -> None:
    now = datetime.now(timezone.utc)
    errors = []
    payload = {"as_of_date": now.date().isoformat(), "generated_at_utc": now.isoformat(), "model_version": "gold-phase0-v0.1"}
    try:
        spot = fetch_spot(); payload["market"] = spot
    except Exception as e:
        errors.append(f"spot: {e}"); spot = None
    macro = {}
    for series in ("DFII10","DTWEXBGS","T10YIE","VIXCLS"):
        try: macro[series] = latest_fred(series)
        except Exception as e: errors.append(f"FRED {series}: {e}")
    payload["macro"] = macro
    try:
        wgc = fetch_wgc(now); payload["fundamentals"] = wgc
    except Exception as e:
        errors.append(f"WGC: {e}"); wgc = None
    if spot and wgc and all(k in macro for k in ("DFII10","DTWEXBGS","T10YIE","VIXCLS")):
        payload["model"] = build_model(spot,macro,wgc); payload["model_status"] = "PROVISIONAL"
    else:
        payload["model"] = None; payload["model_status"] = "UNAVAILABLE"
    payload["errors"] = errors
    payload["data_quality"] = "OK" if not errors else "DEGRADED"
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    print(json.dumps(payload, ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
