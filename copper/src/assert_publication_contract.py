#!/usr/bin/env python3
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
d = json.loads((ROOT / 'docs/copper/data/latest.json').read_text(encoding='utf-8'))
c = d.get('calibration') or {}
m = d.get('model') or {}
g = d.get('governance') or {}
s = d.get('structural_model') or {}

# Structural-equilibrium publication remains provisional until the monthly
# fundamental gate passes, regardless of the weekly market-reference result.
assert d.get('model_status') == 'PROVISIONAL', d.get('model_status')
assert g.get('model_status') == 'PROVISIONAL', g.get('model_status')
assert g.get('monthly_fundamental_walk_forward') == 'BLOCKED', g.get('monthly_fundamental_walk_forward')
assert g.get('final_calibrated_daily_pstar') == 'BLOCKED', g.get('final_calibrated_daily_pstar')
assert g.get('market_months_continuous') == 80
assert g.get('exact_public_icsg_months') == 35
assert g.get('longest_consecutive_icsg_months') == 11
assert g.get('minimum_consecutive_required') == 36
assert g.get('no_imputation') is True
assert g.get('publication_lag_control') is True
assert m.get('equilibrium_claim') == 'WITHHELD_NOT_VALIDATED', m.get('equilibrium_claim')
assert s.get('weight_in_calibrated_pstar', 0) == 0.0
assert abs(float(s.get('p_star_usd_t')) - 10469.088447) < 1e-9
assert not m.get('guardrail_active', False)

print('publication contract OK:', d.get('model_status'), g.get('final_calibrated_daily_pstar'))
