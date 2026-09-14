#!/usr/bin/env python3
"""Apply strict publication governance to copper outputs."""
from __future__ import annotations
import json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]; LATEST=ROOT/'docs/copper/data/latest.json'; CAL=ROOT/'docs/copper/data/weekly_calibration.json'; INDEX=ROOT/'docs/index.html'; TONNES_PER_LB=2204.62262185
def pct(v): return '—' if v is None else f'{float(v):.2f}%'
def main():
 d=json.loads(LATEST.read_text(encoding='utf-8')); c=json.loads(CAL.read_text(encoding='utf-8')); m=c.get('metrics') or {}; live=c.get('live') or {}
 passed=c.get('strict_publication_gate')=='PASS'; candidate=float(live.get('fair_value_usd_t') or d['model']['calibrated_p_star_usd_t']); anchor=float(live.get('anchor_usd_lb'))*TONNES_PER_LB; active=candidate if passed else anchor
 market=float(d['market']['lme_cash_usd_t']); model=d['model']; fit=m.get('accuracy_pct') if passed else m.get('naive_accuracy_pct'); mape=m.get('mape_pct') if passed else m.get('naive_mape_pct'); rmse=m.get('rmse_usd_lb') if passed else m.get('naive_rmse_usd_lb')
 model['calibrated_p_star_usd_t']=round(active,2); model['calibrated_p_star_usd_lb']=round(active/TONNES_PER_LB,6); model['market_vs_pstar_pct']=round((market/active-1)*100,6); model['publication_source']='STRICT_VALIDATED_MODEL' if passed else 'REFERENCE_PRICE_PERSISTENCE'; model['equilibrium_claim']='VALIDATED_MARKET_REFERENCE' if passed else 'WITHHELD_NOT_VALIDATED'; model['accuracy']={'oos_fit_score_100_minus_mape_pct':fit,'mape_pct':mape,'rmse_usd_lb':rmse,'candidate_fit_score_pct':m.get('accuracy_pct'),'naive_fit_score_pct':m.get('naive_accuracy_pct'),'definition':'100 - MAPE on effective published reference; descriptive fit score, not probability or proof of equilibrium.'}
 d['model_status']='VALID' if passed else 'REFERENCE_ONLY'; LATEST.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 text=INDEX.read_text(encoding='utf-8'); gap=model['market_vs_pstar_pct']; label='STRICT VALIDATED' if passed else 'REFERENCE ONLY · EQUILIBRIUM CLAIM WITHHELD'
 repl=[(r'(<span class="muted">Calibrated market P\*</span><strong class="green">).*?(</strong><small>).*?(</small>)',rf'\g<1>${active:,.0f}/t\g<2>{label} · OOS fit score {pct(fit)}\g<3>'),(r'(<span class="muted">Market vs P\*</span><strong class="red">).*?(</strong><small>).*?(</small>)',rf'\g<1>{gap:+.1f}%\g<2>{"market above reference" if gap>=0 else "market below reference"}\g<3>'),(r'(<div class="row"><span>OOS accuracy \(100 − MAPE\)</span><b>).*?(</b></div>)',rf'\g<1>{pct(fit)}\g<2>')]
 for p,r in repl:text=re.sub(p,r,text,count=1,flags=re.S)
 INDEX.write_text(text,encoding='utf-8'); print(json.dumps({'strict_gate':c.get('strict_publication_gate'),'publication_source':model['publication_source'],'reference_usd_t':round(active,2),'fit_score_pct':fit},ensure_ascii=False))
if __name__=='__main__':main()
