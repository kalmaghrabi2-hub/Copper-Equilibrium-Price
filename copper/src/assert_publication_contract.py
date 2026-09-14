#!/usr/bin/env python3
import json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
d=json.loads((ROOT/'docs/copper/data/latest.json').read_text())
c=d.get('calibration') or {}
m=d.get('model') or {}
strict=c.get('strict_publication_gate')
if strict!='PASS':
    assert d.get('model_status')=='REFERENCE_ONLY', d.get('model_status')
    assert m.get('equilibrium_claim')=='WITHHELD_NOT_VALIDATED', m.get('equilibrium_claim')
assert (d.get('structural_model') or {}).get('weight_in_calibrated_pstar',0)==0.0
assert not m.get('guardrail_active',False)
print('publication contract OK:', strict, d.get('model_status'))
