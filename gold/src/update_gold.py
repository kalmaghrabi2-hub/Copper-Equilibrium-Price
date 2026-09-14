#!/usr/bin/env python3
"""Daily gold equilibrium engine.

Layers:
1. live/indicative XAUUSD market quote,
2. calibrated macro fair value from historical monthly data,
3. latest WGC physical/sectoral demand-supply overlay,
4. governance and freshness gates.

Critical missing data is never imputed. The combined P* remains PROVISIONAL until
both macro walk-forward validation and a historical fundamentals calibration pass.
"""
from __future__ import annotations
import csv, io, json, math, re, urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs'/'gold'/'data'/'latest.json'
CAL=ROOT/'docs'/'gold'/'data'/'calibration.json'
UA='GoldEquilibriumPrice/0.2 (+https://github.com/kalmaghrabi2-hub/copper-equilibrium-price)'
FRED='https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
MACRO_SERIES=['DFII10','DTWEXBGS','T10YIE','VIXCLS','CPIAUCSL','M2SL']

def get_text(url,timeout=30):
    req=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
    with urllib.request.urlopen(req,timeout=timeout) as r:return r.read().decode('utf-8',errors='replace')

def get_json(url):return json.loads(get_text(url))

def latest_fred(series):
    rows=list(csv.DictReader(io.StringIO(get_text(FRED.format(series)))))
    for r in reversed(rows):
        raw=(r.get(series) or '').strip()
        if raw not in ('','.'):
            return {'series':series,'date':r['DATE'],'value':float(raw),'source':FRED.format(series)}
    raise RuntimeError(f'no valid FRED observation: {series}')

def fetch_spot():
    try:
        j=get_json('https://xaus.com/api/v1/spot?compact=1')
        ds=j.get('data_state') or {}; v=j.get('spot_usd_oz') or (j.get('xau') or {}).get('price')
        if v is None: raise RuntimeError('XAUS price missing')
        return {'usd_oz':float(v),'as_of':ds.get('as_of') or j.get('updated_at'),'freshness_status':ds.get('status','unknown'),'age_seconds':ds.get('age_seconds'),'provider':'XAUS','source':'https://xaus.com/api/v1/spot'}
    except Exception as primary:
        j=get_json('https://api.gold-api.com/price/XAU'); v=j.get('price')
        if v is None: raise RuntimeError(f'gold spot feeds failed; XAUS={primary}')
        return {'usd_oz':float(v),'as_of':j.get('updatedAt') or j.get('updated_at'),'freshness_status':'fallback','age_seconds':None,'provider':'Gold API','source':'https://api.gold-api.com/price/XAU'}

def candidate_wgc_urls(now):
    q=(now.month-1)//3+1; y=now.year; q-=1
    if q==0:q,y=4,y-1
    out=[]
    for _ in range(8):
        out.append(f'https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q{q}-{y}')
        q-=1
        if q==0:q,y=4,y-1
    return out

def parse_wgc_table(html,url):
    text=re.sub(r'<[^>]+>',' ',html); text=re.sub(r'\s+',' ',text)
    def val(label):
        p=re.escape(label)+r"\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)"
        m=re.search(p,text,re.I)
        if not m: raise RuntimeError('missing WGC row '+label)
        return float(m.group(5).replace(',',''))
    d={'mine_production_t':val('Mine Production'),'producer_hedging_t':val('Net Producer Hedging'),'recycled_gold_t':val('Recycled Gold'),'total_supply_t':val('Total Supply'),'jewellery_fabrication_t':val('Jewellery Fabrication'),'technology_t':val('Technology'),'investment_t':val('Investment'),'bar_coin_t':val('Total Bar and Coin'),'etf_t':val('ETFs & Similar Products'),'central_banks_t':val('Central Banks & Other inst.'),'gold_demand_ex_otc_t':val('Gold Demand'),'otc_other_t':val('OTC and Other'),'total_demand_t':val('Total Demand'),'quarter_avg_lbma_usd_oz':val('LBMA Gold Price (US$/oz)'),'source':url}
    m=re.search(r'Gold Demand Trends:\s*Q([1-4])\s*(\d{4})',text,re.I)
    if m:d['quarter']=f'{m.group(2)}-Q{m.group(1)}'
    return d

def fetch_wgc(now):
    errs=[]
    for u in candidate_wgc_urls(now):
        try:
            h=get_text(u)
            if 'Total Supply' not in h: raise RuntimeError('table marker absent')
            return parse_wgc_table(h,u)
        except Exception as e: errs.append(str(e))
    raise RuntimeError('WGC latest table unavailable: '+' | '.join(errs))

def load_calibration():
    if not CAL.exists(): return None
    try:return json.loads(CAL.read_text(encoding='utf-8'))
    except Exception:return None

def calibrated_macro_value(macro,cal):
    if not cal:return None
    series=cal.get('series') or []; beta=cal.get('beta') or []; means=cal.get('means') or []; sds=cal.get('sds') or []
    if len(beta)!=len(series)+1:return None
    vals=[]
    for s in series:
        if s not in macro:return None
        vals.append(macro[s]['value'])
    x=[1.0]+[(v-m)/sd for v,m,sd in zip(vals,means,sds)]
    return math.exp(sum(a*b for a,b in zip(x,beta)))

def physical_overlay(w):
    # Visible strategic demand share: bar/coin + ETF + central bank + OTC relative to total supply.
    # Neutral share 0.50 is an explicit phase-1 reference, not a fitted historical coefficient.
    strategic=w['bar_coin_t']+w['etf_t']+w['central_banks_t']+w['otc_other_t']
    share=strategic/max(w['total_supply_t'],1.0)
    recycling_share=w['recycled_gold_t']/max(w['total_supply_t'],1.0)
    # Strong strategic demand lifts fair value; unusually high recycling is a countervailing supply response.
    raw=math.exp(0.35*(share-0.50)-0.20*(recycling_share-0.27))
    mult=min(max(raw,0.88),1.12)
    return {'strategic_demand_share':share,'recycling_share':recycling_share,'multiplier':mult,'status':'UNCALIBRATED_OVERLAY'}

def main():
    now=datetime.now(timezone.utc); errors=[]
    payload={'as_of_date':now.date().isoformat(),'generated_at_utc':now.isoformat(),'model_version':'gold-hybrid-v1.0'}
    try: spot=fetch_spot(); payload['market']=spot
    except Exception as e: errors.append('spot: '+str(e)); spot=None
    macro={}
    for s in MACRO_SERIES:
        try:macro[s]=latest_fred(s)
        except Exception as e:errors.append(f'FRED {s}: {e}')
    payload['macro']=macro
    try:wgc=fetch_wgc(now); payload['fundamentals']=wgc
    except Exception as e:errors.append('WGC: '+str(e)); wgc=None
    cal=load_calibration(); payload['calibration']=cal
    macro_p=calibrated_macro_value(macro,cal)
    if spot and wgc and macro_p:
        ph=physical_overlay(wgc); pstar=macro_p*ph['multiplier']
        # Publication guardrail; hitting it is itself disclosed.
        lo,hi=0.55*spot['usd_oz'],1.55*spot['usd_oz']; gated=min(max(pstar,lo),hi); guardrail=(gated!=pstar)
        macro_gate=(cal or {}).get('walk_forward_gate')
        model_status='PROVISIONAL'  # fundamentals overlay has not yet passed historical calibration
        payload['model']={'macro_fair_value_usd_oz':round(macro_p,2),'physical_overlay':{k:(round(v,6) if isinstance(v,float) else v) for k,v in ph.items()},'fundamental_p_star_usd_oz':round(gated,2),'raw_combined_p_star_usd_oz':round(pstar,2),'market_vs_pstar_pct':round((spot['usd_oz']/gated-1)*100,2),'guardrail_active':guardrail,'status':model_status,'confidence':'MEDIUM' if macro_gate=='PASS' else 'LOW','governance':{'macro_walk_forward':macro_gate or 'PENDING','fundamentals_historical_calibration':'PENDING','no_imputation':True,'publication_gate':'PROVISIONAL_ONLY'}}
        payload['model_status']=model_status
    else:
        payload['model']=None; payload['model_status']='UNAVAILABLE'
    payload['errors']=errors; payload['data_quality']='OK' if not errors else 'DEGRADED'
    OUT.parent.mkdir(parents=True,exist_ok=True); OUT.write_text(json.dumps(payload,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(json.dumps(payload,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
