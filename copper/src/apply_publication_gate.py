#!/usr/bin/env python3
"""Apply the final publication gate after model calibration/update.

If the candidate weekly model does not beat persistence on the untouched final
OOS window, the published P* falls back to the last observed weekly copper
anchor. Candidate diagnostics remain in weekly_calibration.json.
"""
from __future__ import annotations
import json,re
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
LATEST=ROOT/'docs/copper/data/latest.json'
CAL=ROOT/'docs/copper/data/weekly_calibration.json'
INDEX=ROOT/'docs/index.html'
TONNES_PER_LB=2204.62262185

def pct(v): return '—' if v is None else f'{float(v):.2f}%'
def main():
    d=json.loads(LATEST.read_text(encoding='utf-8'))
    c=json.loads(CAL.read_text(encoding='utf-8'))
    m=c.get('metrics') or {}; live=c.get('live') or {}
    passed=c.get('walk_forward_gate')=='PASS' and c.get('benchmark_gate')=='PASS'
    candidate=float(live.get('fair_value_usd_t') or d['model']['calibrated_p_star_usd_t'])
    anchor_lb=live.get('anchor_usd_lb')
    fallback=float(anchor_lb)*TONNES_PER_LB if anchor_lb is not None else candidate
    active=candidate if passed else fallback
    market=float(d['market']['lme_cash_usd_t'])
    acc=m.get('accuracy_pct') if passed else m.get('naive_accuracy_pct')
    mape=m.get('mape_pct') if passed else m.get('naive_mape_pct')
    rmse=m.get('rmse_usd_lb') if passed else m.get('naive_rmse_usd_lb')
    model=d['model']; model['calibrated_p_star_usd_t']=round(active,2); model['calibrated_p_star_usd_lb']=round(active/TONNES_PER_LB,6)
    model['market_vs_pstar_pct']=round((market/active-1)*100,6)
    model['publication_source']='BENCHMARK_MODEL' if passed else 'PERSISTENCE_FALLBACK'
    model['accuracy']={**(model.get('accuracy') or {}),'oos_accuracy_pct':acc,'mape_pct':mape,'rmse_usd_lb':rmse,'candidate_model_accuracy_pct':m.get('accuracy_pct'),'candidate_model_mape_pct':m.get('mape_pct'),'naive_accuracy_pct':m.get('naive_accuracy_pct'),'naive_mape_pct':m.get('naive_mape_pct'),'definition':'100 - MAPE on the effective published layer over the final OOS window; descriptive, not a probability'}
    LATEST.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text=INDEX.read_text(encoding='utf-8'); gap=model['market_vs_pstar_pct']
    repl=[
      (r'(<span class="muted">Calibrated market P\*</span><strong class="green">).*?(</strong><small>).*?(</small>)',rf'\g<1>${active:,.0f}/t\g<2>{model["publication_source"]} · effective OOS accuracy {pct(acc)}\g<3>'),
      (r'(<span class="muted">Market vs P\*</span><strong class="red">).*?(</strong><small>).*?(</small>)',rf'\g<1>{gap:+.1f}%\g<2>{"السوق أعلى من السعر المتعادل" if gap>=0 else "السوق أدنى من السعر المتعادل"}\g<3>'),
      (r'(<div class="row"><span>OOS accuracy \(100 − MAPE\)</span><b>).*?(</b></div>)',rf'\g<1>{pct(acc)}\g<2>'),
      (r'(<div class="row"><span>Model MAPE</span><b>).*?(</b></div>)',rf'\g<1>{pct(m.get("mape_pct"))}\g<2>'),
      (r'(<div class="row"><span>Naive MAPE</span><b>).*?(</b></div>)',rf'\g<1>{pct(m.get("naive_mape_pct"))}\g<2>')]
    for p,r in repl: text=re.sub(p,r,text,count=1,flags=re.S)
    INDEX.write_text(text,encoding='utf-8')
    print(json.dumps({'publication_source':model['publication_source'],'pstar_usd_t':round(active,2),'effective_accuracy_pct':acc},ensure_ascii=False))
if __name__=='__main__': main()
