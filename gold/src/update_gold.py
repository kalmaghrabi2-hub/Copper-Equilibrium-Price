#!/usr/bin/env python3
from __future__ import annotations
import csv, io, json, math, re
from datetime import datetime, timezone
from pathlib import Path
import requests

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs' / 'gold' / 'data' / 'latest.json'
HISTORY = ROOT / 'docs' / 'gold' / 'data' / 'history.jsonl'
MODEL_FILE = ROOT / 'gold' / 'model' / 'model.json'
UA = 'GoldEquilibriumPrice/1.0 (+https://github.com/kalmaghrabi2-hub/copper-equilibrium-price)'

def text(url: str, timeout=35) -> str:
    r = requests.get(url, headers={'User-Agent': UA, 'Accept': '*/*'}, timeout=timeout)
    r.raise_for_status()
    return r.text

def js(url: str):
    return json.loads(text(url))

def latest_fred(series: str) -> dict:
    url = f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={series}'
    rows = list(csv.DictReader(io.StringIO(text(url))))
    for row in reversed(rows):
        raw = (row.get(series) or '').strip()
        if raw not in ('', '.'):
            return {'series': series, 'date': row.get('observation_date') or row.get('DATE'), 'value': float(raw), 'source': url}
    raise RuntimeError(f'No valid FRED observation: {series}')

def spot() -> dict:
    errors=[]
    for provider,url,extract in [
        ('XAUS','https://xaus.com/api/v1/spot?compact=1',lambda j: j.get('spot_usd_oz') or (j.get('xau') or {}).get('price')),
        ('Gold API','https://api.gold-api.com/price/XAU',lambda j: j.get('price')),
    ]:
        try:
            j=js(url); p=extract(j)
            if p is None: raise ValueError('missing price')
            state=j.get('data_state') or {}
            return {'usd_oz':float(p),'provider':provider,'as_of':state.get('as_of') or j.get('updatedAt') or j.get('updated_at'),'freshness_status':state.get('status','fallback' if provider!='XAUS' else 'unknown'),'source':url}
        except Exception as e: errors.append(f'{provider}: {e}')
    raise RuntimeError(' | '.join(errors))

def wgc_latest() -> dict:
    now=datetime.now(timezone.utc); q=(now.month-1)//3+1; cq=q-1; cy=now.year
    if cq==0: cq,cy=4,cy-1
    last_error=''
    for _ in range(6):
        url=f'https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q{cq}-{cy}'
        try:
            html=text(url)
            plain=re.sub(r'<[^>]+>',' ',html); plain=re.sub(r'\s+',' ',plain)
            def vals(label):
                m=re.search(re.escape(label)+r"\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)",plain,re.I)
                if not m: raise ValueError(label)
                return [float(x.replace(',','')) for x in m.groups()]
            mine=vals('Mine Production'); recycled=vals('Recycled Gold'); hedging=vals('Net Producer Hedging')
            tech=vals('Technology'); bar=vals('Total Bar and Coin')
            try: etf=vals('ETFs & Similar Products')
            except Exception: etf=vals('ETFs & similar products')
            try: cb=vals('Central Banks & Other inst.')
            except Exception: cb=vals('Central banks & other inst.')
            price=vals('LBMA Gold Price (US$/oz)')
            supply=vals('Total Supply')
            pressure=[]
            for i in range(5):
                strategic=0.45*cb[i]+0.35*bar[i]+0.15*etf[i]+0.05*tech[i]
                denom=max(1.0,mine[i]+recycled[i]+hedging[i])
                pressure.append(strategic/denom)
            med=sorted(pressure)[2]
            cur=pressure[-1]
            physical_multiplier=math.exp(0.85*(cur-med))
            return {
                'quarter':f'{cy}-Q{cq}','source':url,
                'mine_production_t':mine[-1],'producer_hedging_t':hedging[-1],'recycled_gold_t':recycled[-1],'total_supply_t':supply[-1],
                'technology_t':tech[-1],'bar_coin_t':bar[-1],'etf_t':etf[-1],'central_banks_t':cb[-1],
                'quarter_avg_lbma_usd_oz':price[-1],
                'pressure_last5':pressure,'pressure_median5':med,'pressure_current':cur,'physical_multiplier':physical_multiplier,
                'physical_status':'PROVISIONAL_5Q_NORMALIZATION'
            }
        except Exception as e:
            last_error=f'{url}: {e}'
            cq-=1
            if cq==0: cq,cy=4,cy-1
    raise RuntimeError(last_error)

def macro_pstar(model: dict, macro: dict) -> float:
    feats={
        'DFII10':macro['DFII10']['value'],
        'DTWEXBGS':macro['DTWEXBGS']['value'],
        'T10YIE':macro['T10YIE']['value'],
        'VIXCLS_LOG':math.log(max(1.0,macro['VIXCLS']['value']))
    }
    z=[]
    for f in model['features']:
        z.append((feats[f]-model['feature_mean'][f])/model['feature_std'][f])
    logp=model['intercept']+sum(model['coefficients_standardized'][f]*zz for f,zz in zip(model['features'],z))
    return math.exp(logp)

def append_history(payload: dict):
    HISTORY.parent.mkdir(parents=True,exist_ok=True)
    compact={'generated_at_utc':payload['generated_at_utc'],'market':payload.get('market'),'model':payload.get('model'),'data_quality':payload['data_quality']}
    with HISTORY.open('a',encoding='utf-8') as f: f.write(json.dumps(compact,ensure_ascii=False)+'\n')

def main():
    now=datetime.now(timezone.utc); errors=[]
    payload={'as_of_date':now.date().isoformat(),'generated_at_utc':now.isoformat(),'model_version':'gold-equilibrium-v1'}
    try: payload['market']=mkt=spot()
    except Exception as e: errors.append(f'spot: {e}'); mkt=None
    macro={}
    for s in ('DFII10','DTWEXBGS','T10YIE','VIXCLS'):
        try: macro[s]=latest_fred(s)
        except Exception as e: errors.append(f'FRED {s}: {e}')
    payload['macro']=macro
    try: payload['fundamentals']=fund=wgc_latest()
    except Exception as e: errors.append(f'WGC: {e}'); fund=None
    try: model=json.loads(MODEL_FILE.read_text(encoding='utf-8'))
    except Exception as e: errors.append(f'model file: {e}'); model=None
    if mkt and fund and model and all(s in macro for s in ('DFII10','DTWEXBGS','T10YIE','VIXCLS')):
        macro_fair=macro_pstar(model,macro)
        raw_pstar=macro_fair*fund['physical_multiplier']
        lower,upper=0.55*mkt['usd_oz'],1.55*mkt['usd_oz']
        guardrail_applied=raw_pstar<lower or raw_pstar>upper
        pstar=max(lower,min(upper,raw_pstar))
        macro_gate=model.get('macro_validation_gate')=='PASS'
        physical_gate=fund.get('physical_status')=='VALID'
        status='VALID' if macro_gate and physical_gate and not guardrail_applied else 'PROVISIONAL'
        payload['model']={
            'macro_fair_value_usd_oz':round(macro_fair,2),'physical_multiplier':round(fund['physical_multiplier'],6),
            'raw_fundamental_p_star_usd_oz':round(raw_pstar,2),'fundamental_p_star_usd_oz':round(pstar,2),
            'guardrail_applied':guardrail_applied,'market_vs_pstar_pct':round((mkt['usd_oz']/pstar-1)*100,2),
            'status':status,'macro_gate':model.get('macro_validation_gate'),'physical_gate':fund.get('physical_status'),
            'walk_forward_metrics':model.get('metrics'),
            'governance':{'no_imputation':True,'publication_gate':'VALID_ONLY_IF_BOTH_GATES_PASS_AND_NO_GUARDRAIL'}
        }
        payload['model_status']=status
    else:
        payload['model']=None; payload['model_status']='UNAVAILABLE'
    payload['errors']=errors; payload['data_quality']='OK' if not errors else 'DEGRADED'
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    append_history(payload)
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__': main()
