#!/usr/bin/env python3
"""Apply weekly reference governance without overriding structural-equilibrium governance."""
from __future__ import annotations
import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
LATEST = ROOT / 'docs/copper/data/latest.json'
CAL = ROOT / 'docs/copper/data/weekly_calibration.json'
INDEX = ROOT / 'docs/index.html'
TONNES_PER_LB = 2204.62262185


def pct(v):
    return '—' if v is None else f'{float(v):.2f}%'


def main():
    d = json.loads(LATEST.read_text(encoding='utf-8'))
    c = json.loads(CAL.read_text(encoding='utf-8'))
    m = c.get('metrics') or {}
    live = c.get('live') or {}

    weekly_passed = c.get('strict_publication_gate') == 'PASS'
    candidate = float(live.get('fair_value_usd_t') or d['model']['calibrated_p_star_usd_t'])
    anchor_lb = live.get('anchor_usd_lb')
    anchor = float(anchor_lb) * TONNES_PER_LB if anchor_lb is not None else candidate
    active = candidate if weekly_passed else anchor
    market = float(d['market']['lme_cash_usd_t'])
    model = d['model']

    fit = m.get('accuracy_pct') if weekly_passed else m.get('naive_accuracy_pct')
    mape = m.get('mape_pct') if weekly_passed else m.get('naive_mape_pct')
    rmse = m.get('rmse_usd_lb') if weekly_passed else m.get('naive_rmse_usd_lb')

    # Weekly layer remains a near-term market reference only. It never upgrades
    # the structural equilibrium claim or the top-level governance state.
    model['calibrated_p_star_usd_t'] = round(active, 2)
    model['calibrated_p_star_usd_lb'] = round(active / TONNES_PER_LB, 6)
    model['market_vs_pstar_pct'] = round((market / active - 1) * 100, 6)
    model['status'] = 'PROVISIONAL'
    model['confidence'] = 'LOW'
    model['publication_role'] = 'REFERENCE_ONLY'
    model['publication_source'] = 'STRICT_VALIDATED_MARKET_REFERENCE' if weekly_passed else 'REFERENCE_PRICE_PERSISTENCE'
    model['equilibrium_claim'] = 'WITHHELD_NOT_VALIDATED'
    model['accuracy'] = {
        'oos_fit_score_100_minus_mape_pct': fit,
        'mape_pct': mape,
        'rmse_usd_lb': rmse,
        'candidate_fit_score_pct': m.get('accuracy_pct'),
        'naive_fit_score_pct': m.get('naive_accuracy_pct'),
        'definition': '100 - MAPE on effective published market reference; descriptive fit score, not probability or proof of structural equilibrium.'
    }

    d['model_status'] = 'PROVISIONAL'
    gov = d.setdefault('governance', {})
    gov['model_status'] = 'PROVISIONAL'
    gov['monthly_fundamental_walk_forward'] = 'BLOCKED'
    gov['final_calibrated_daily_pstar'] = 'BLOCKED'
    LATEST.write_text(json.dumps(d, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    # Only update the weekly accuracy row. Structural P* and market-vs-Structural-P*
    # cards are owned by update_copper.py and must not be overwritten here.
    text = INDEX.read_text(encoding='utf-8')
    text = re.sub(
        r'(<div class="row"><span>OOS accuracy \(100 − MAPE\)</span><b>).*?(</b></div>)',
        rf'\g<1>{pct(fit)}\g<2>', text, count=1, flags=re.S
    )
    INDEX.write_text(text, encoding='utf-8')
    print(json.dumps({
        'weekly_strict_gate': c.get('strict_publication_gate'),
        'weekly_publication_source': model['publication_source'],
        'weekly_reference_usd_t': round(active, 2),
        'top_level_model_status': d['model_status'],
        'final_calibrated_daily_pstar': gov['final_calibrated_daily_pstar']
    }, ensure_ascii=False))


if __name__ == '__main__':
    main()
