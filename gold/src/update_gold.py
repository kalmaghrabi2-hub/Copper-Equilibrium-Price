#!/usr/bin/env python3
from __future__ import annotations
import csv,io,json,math,re,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/gold/data/latest.json';CAL=ROOT/'docs/gold/data/weekly_calibration.json'
UA='GoldEquilibriumPrice/1.0';FRED='https://fred.stlouisfed.org/graph/fredgraph.csv?id={}&cosd=2026-01-01';MACRO_SERIES=['DFII10','DTWEXBGS','T10YIE','VIXCLS']
def get_text(url,timeout=45):
 r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
 with urllib.request.urlopen(r,timeout=timeout) as x:return x.read().decode('utf-8',errors='replace')
def get_json(u):return json.loads(get_text(u))
def latest_fred(s):
 rows=list(csv.DictReader(io.StringIO(get_text(FRED.format(s)))))
 for r in reversed(rows):
  v=(r.get(s) or '').strip()
  if v not in ('','.') :return {'series':s,'date':r['DATE'],'value':float(v),'source':FRED.format(s)}
 raise RuntimeError('no FRED observation '+s)
def fetch_spot():
 try:
  j=get_json('https://xaus.com/api/v1/spot?compact=1');ds=j.get('data_state') or {};v=j.get('spot_usd_oz') or (j.get('xau') or {}).get('price')
  if v is None:raise RuntimeError('XAUS price missing')
  return {'usd_oz':float(v),'as_of':ds.get('as_of') or j.get('updated_at'),'freshness_status':ds.get('status','unknown'),'provider':'XAUS','source':'https://xaus.com/api/v1/spot'}
 except Exception as e:
  j=get_json('https://api.gold-api.com/price/XAU');v=j.get('price')
  if v is None:raise RuntimeError('spot feeds failed '+str(e))
  return {'usd_oz':float(v),'as_of':j.get('updatedAt') or j.get('updated_at'),'freshness_status':'fallback','provider':'Gold API','source':'https://api.gold-api.com/price/XAU'}
def urls(now):
 q=(now.month-1)//3+1;y=now.year;q-=1
 if q==0:q,y=4,y-1
 o=[]
 for _ in range(8):
  o.append(f'https://www.gold.org/goldhub/research/gold-demand-trends/gold-demand-trends-q{q}-{y}');q-=1
  if q==0:q,y=4,y-1
 return o
def parse_wgc(h,u):
 t=re.sub(r'<[^>]+>',' ',h);t=re.sub(r'\s+',' ',t)
 def val(label):
  p=re.escape(label)+r"\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)";m=re.search(p,t,re.I)
  if not m:raise RuntimeError('missing WGC '+label)
  return float(m.group(5).replace(',',''))
 d={'mine_production_t':val('Mine Production'),'producer_hedging_t':val('Net Producer Hedging'),'recycled_gold_t':val('Recycled Gold'),'total_supply_t':val('Total Supply'),'jewellery_fabrication_t':val('Jewellery Fabrication'),'technology_t':val('Technology'),'investment_t':val('Investment'),'bar_coin_t':val('Total Bar and Coin'),'etf_t':val('ETFs & Similar Products'),'central_banks_t':val('Central Banks & Other inst.'),'gold_demand_ex_otc_t':val('Gold Demand'),'otc_other_t':val('OTC and Other'),'total_demand_t':val('Total Demand'),'quarter_avg_lbma_usd_oz':val('LBMA Gold Price (US$/oz)'),'source':u};m=re.search(r'Gold Demand Trends:\s*Q([1-4])\s*(\d{4})',t,re.I)
 if m:d['quarter']=f'{m.group(2)}-Q{m.group(1)}'
 return d
def fetch_wgc(now):
 errs=[]
 for u in urls(now):
  try:
   h=get_text(u)
   if 'Total Supply' not in h:raise RuntimeError('table absent')
   return parse_wgc(h,u)
  except Exception as e:errs.append(str(e))
 raise RuntimeError('WGC unavailable: '+' | '.join(errs))
def load_cal():
 try:return json.loads(CAL.read_text())
 except:return None
def macro_value(m,cal):
 if not cal:return None
 s=cal.get('series') or [];b=cal.get('beta') or [];mu=cal.get('means') or [];sd=cal.get('sds') or []
 if len(b)!=len(s)+1:return None
 vals=[]
 for k in s:
  if k not in m:return None
  vals.append(m[k]['value'])
 x=[1.0]+[(v-a)/z for v,a,z in zip(vals,mu,sd)];return math.exp(sum(a*z for a,z in zip(x,b)))
def overlay(w):
 strategic=w['bar_coin_t']+w['etf_t']+w['central_banks_t']+w['otc_other_t'];share=strategic/max(w['total_supply_t'],1);recycle=w['recycled_gold_t']/max(w['total_supply_t'],1);raw=math.exp(.35*(share-.50)-.20*(recycle-.27));mult=min(max(raw,.88),1.12);return {'strategic_demand_share':share,'recycling_share':recycle,'multiplier':mult,'status':'UNCALIBRATED_OVERLAY'}
def main():
 now=datetime.now(timezone.utc);err=[];p={'as_of_date':now.date().isoformat(),'generated_at_utc':now.isoformat(),'model_version':'gold-weekly-hybrid-v1.0'}
 try:spot=fetch_spot();p['market']=spot
 except Exception as e:err.append('spot: '+str(e));spot=None
 macro={}
 for s in MACRO_SERIES:
  try:macro[s]=latest_fred(s)
  except Exception as e:err.append(f'FRED {s}: {e}')
 p['macro']=macro
 try:w=fetch_wgc(now);p['fundamentals']=w
 except Exception as e:err.append('WGC: '+str(e));w=None
 cal=load_cal();p['calibration']=cal;mp=macro_value(macro,cal)
 if spot and w and mp:
  ph=overlay(w);raw=mp*ph['multiplier'];lo,hi=.55*spot['usd_oz'],1.55*spot['usd_oz'];ps=min(max(raw,lo),hi);gate=(cal or {}).get('walk_forward_gate');p['model']={'macro_fair_value_usd_oz':round(mp,2),'physical_overlay':{k:(round(v,6) if isinstance(v,float) else v) for k,v in ph.items()},'fundamental_p_star_usd_oz':round(ps,2),'raw_combined_p_star_usd_oz':round(raw,2),'market_vs_pstar_pct':round((spot['usd_oz']/ps-1)*100,2),'guardrail_active':ps!=raw,'status':'PROVISIONAL','confidence':'MEDIUM' if gate=='PASS' else 'LOW','governance':{'weekly_macro_walk_forward':gate or 'PENDING','fundamentals_historical_calibration':'PENDING','no_imputation':True,'publication_gate':'PROVISIONAL_ONLY'}};p['model_status']='PROVISIONAL'
 else:p['model']=None;p['model_status']='UNAVAILABLE'
 p['errors']=err;p['data_quality']='OK' if not err else 'DEGRADED';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n');print(json.dumps(p,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
