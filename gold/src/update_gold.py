#!/usr/bin/env python3
from __future__ import annotations
import html,json,math,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/gold/data/latest.json';CAL=ROOT/'docs/gold/data/weekly_calibration.json'
UA='Mozilla/5.0 GoldEquilibriumPrice/1.3';MACRO_SERIES=['DX-Y.NYB','^TNX','^VIX','TIP']
def get_text(url,timeout=45):
 r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
 with urllib.request.urlopen(r,timeout=timeout) as x:return x.read().decode('utf-8',errors='replace')
def get_json(u):return json.loads(get_text(u))
def yahoo_quote(s):
 q=urllib.parse.quote(s,safe='');now=int(datetime.now(timezone.utc).timestamp());start=now-21*86400;u=f'https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1={start}&period2={now}&interval=1d&events=history'
 j=get_json(u);res=((j.get('chart') or {}).get('result') or [None])[0]
 if not res:raise RuntimeError('Yahoo empty '+s)
 ts=res.get('timestamp') or [];cl=(((res.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
 for t,v in reversed(list(zip(ts,cl))):
  if v is not None and math.isfinite(float(v)):return {'series':s,'date':datetime.fromtimestamp(t,tz=timezone.utc).date().isoformat(),'value':float(v),'source':u}
 raise RuntimeError('Yahoo no valid close '+s)
def fetch_spot():
 try:
  j=get_json('https://xaus.com/api/v1/spot?compact=1');ds=j.get('data_state') or {};v=j.get('spot_usd_oz') or (j.get('xau') or {}).get('price')
  if v is None:raise RuntimeError('XAUS price missing')
  return {'usd_oz':float(v),'as_of':ds.get('as_of') or j.get('updated_at'),'freshness_status':ds.get('status','unknown'),'provider':'XAUS','source':'https://xaus.com/api/v1/spot'}
 except Exception:
  try:
   q=yahoo_quote('GC=F');return {'usd_oz':q['value'],'as_of':q['date'],'freshness_status':'futures_fallback','provider':'Yahoo GC=F','source':q['source']}
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
 t=html.unescape(h);t=re.sub(r'<[^>]+>',' ',t);t=t.replace('\u00a0',' ');t=re.sub(r'\s+',' ',t)
 def val(*labels):
  for label in labels:
   p=re.escape(label)+r"\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)\s*\|?\s*([\-\d,.]+)";m=re.search(p,t,re.I)
   if m:return float(m.group(5).replace(',',''))
  raise RuntimeError('missing WGC '+labels[0])
 d={'mine_production_t':val('Mine Production'),'producer_hedging_t':val('Net Producer Hedging'),'recycled_gold_t':val('Recycled Gold'),'total_supply_t':val('Total Supply'),'jewellery_fabrication_t':val('Jewellery Fabrication'),'technology_t':val('Technology'),'investment_t':val('Investment'),'bar_coin_t':val('Total Bar and Coin','Bar and Coin'),'etf_t':val('ETFs & Similar Products','Gold ETFs','ETFs'),'central_banks_t':val('Central Banks & Other inst.','Central Banks'),'gold_demand_ex_otc_t':val('Gold Demand'),'otc_other_t':val('OTC and Other'),'total_demand_t':val('Total Demand'),'quarter_avg_lbma_usd_oz':val('LBMA Gold Price (US$/oz)','LBMA (PM) Gold Price (US$/oz)'),'source':u};m=re.search(r'Gold Demand Trends:\s*Q([1-4])\s*(\d{4})',t,re.I)
 if m:d['quarter']=f'{m.group(2)}-Q{m.group(1)}'
 return d
def fetch_wgc(now):
 errs=[]
 for u in urls(now):
  try:
   h=get_text(u)
   if 'Total Supply' not in html.unescape(h):raise RuntimeError('table absent')
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
 now=datetime.now(timezone.utc);err=[];p={'as_of_date':now.date().isoformat(),'generated_at_utc':now.isoformat(),'model_version':'gold-weekly-hybrid-v1.3'}
 try:spot=fetch_spot();p['market']=spot
 except Exception as e:err.append('spot: '+str(e));spot=None
 macro={}
 for s in MACRO_SERIES:
  try:macro[s]=yahoo_quote(s)
  except Exception as e:err.append(f'Yahoo {s}: {e}')
 p['macro']=macro
 try:w=fetch_wgc(now);p['fundamentals']=w
 except Exception as e:err.append('WGC: '+str(e));w=None
 cal=load_cal();p['calibration']=cal;mp=macro_value(macro,cal)
 if spot and w and mp:
  ph=overlay(w);raw=mp*ph['multiplier'];lo,hi=.55*spot['usd_oz'],1.55*spot['usd_oz'];ps=min(max(raw,lo),hi);gate=(cal or {}).get('walk_forward_gate');p['model']={'macro_fair_value_usd_oz':round(mp,2),'physical_overlay':{k:(round(v,6) if isinstance(v,float) else v) for k,v in ph.items()},'fundamental_p_star_usd_oz':round(ps,2),'raw_combined_p_star_usd_oz':round(raw,2),'market_vs_pstar_pct':round((spot['usd_oz']/ps-1)*100,2),'guardrail_active':ps!=raw,'status':'PROVISIONAL','confidence':'LOW' if gate!='PASS' else 'MEDIUM','governance':{'weekly_walk_forward':gate or 'PENDING','fundamentals_historical_calibration':'PENDING','no_imputation':True,'publication_gate':'PROVISIONAL_ONLY'}};p['model_status']='PROVISIONAL'
 else:p['model']=None;p['model_status']='UNAVAILABLE'
 p['errors']=err;p['data_quality']='OK' if not err else 'DEGRADED';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n');print(json.dumps(p,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
