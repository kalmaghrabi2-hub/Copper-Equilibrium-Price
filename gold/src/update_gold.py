#!/usr/bin/env python3
from __future__ import annotations
import html,json,math,re,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/gold/data/latest.json'
CAL=ROOT/'docs/gold/data/weekly_calibration.json'
FCAL=ROOT/'docs/gold/data/fundamentals_calibration.json'
UA='Mozilla/5.0 GoldEquilibriumPrice/3.0';MACRO_SERIES=['DX-Y.NYB','^TNX','^VIX','TIP']

def get_text(url,timeout=45):
 r=urllib.request.Request(url,headers={'User-Agent':UA,'Accept':'*/*'})
 with urllib.request.urlopen(r,timeout=timeout) as x:return x.read().decode('utf-8',errors='replace')
def get_json(u):return json.loads(get_text(u))
def yahoo_quote(s):
 q=urllib.parse.quote(s,safe='');now=int(datetime.now(timezone.utc).timestamp());start=now-21*86400;u=f'https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1={start}&period2={now}&interval=1d&events=history';j=get_json(u);res=((j.get('chart') or {}).get('result') or [None])[0]
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
def load_json(path):
 try:return json.loads(path.read_text(encoding='utf-8'))
 except:return None
def fair_value(m,cal,gold_anchor):
 if not cal:return None
 s=cal.get('series') or [];b=cal.get('beta') or [];mu=cal.get('means') or [];sd=cal.get('sds') or []
 if len(b)!=len(s)+1:return None
 vals=[]
 for k in s:
  if k=='LAG_GOLD_LOG':vals.append(math.log(gold_anchor))
  elif k in m:vals.append(m[k]['value'])
  else:return None
 x=[1.0]+[(v-a)/z for v,a,z in zip(vals,mu,sd)];return math.exp(sum(a*z for a,z in zip(x,b)))
def physical_features(w):
 supply=max(w['total_supply_t'],1.0);strategic=w['bar_coin_t']+w['etf_t']+w['central_banks_t']
 return [strategic/supply,w['recycled_gold_t']/supply,(w.get('producer_hedging_t') or 0.0)/supply]
def overlay(w,fcal):
 x=physical_features(w);strategic=x[0];recycle=x[1]
 if fcal:
  b=fcal.get('beta') or [];mu=fcal.get('means') or [];sd=fcal.get('sds') or []
  if len(b)==len(x)+1 and len(mu)==len(x) and len(sd)==len(x):
   z=[1.0]+[(v-a)/s for v,a,s in zip(x,mu,sd)];ret=sum(a*v for a,v in zip(b,z));raw=math.exp(ret);mult=min(max(raw,.88),1.12);gate=fcal.get('walk_forward_gate') or 'PENDING'
   return {'strategic_demand_share':strategic,'recycling_share':recycle,'producer_hedging_share':x[2],'predicted_next_quarter_return_pct':100*(raw-1),'raw_multiplier':raw,'multiplier':mult,'guardrail_active':mult!=raw,'status':'CALIBRATED' if gate=='PASS' else 'CALIBRATED_GATE_FAIL','walk_forward_gate':gate}
 # Explicit fallback only when the calibration artifact is unavailable.
 raw=math.exp(.35*(strategic-.50)-.20*(recycle-.27));mult=min(max(raw,.88),1.12)
 return {'strategic_demand_share':strategic,'recycling_share':recycle,'producer_hedging_share':x[2],'predicted_next_quarter_return_pct':100*(raw-1),'raw_multiplier':raw,'multiplier':mult,'guardrail_active':mult!=raw,'status':'FALLBACK_HEURISTIC','walk_forward_gate':'PENDING'}
def main():
 now=datetime.now(timezone.utc);err=[];p={'as_of_date':now.date().isoformat(),'generated_at_utc':now.isoformat(),'model_version':'gold-weekly-arx-wgc-calibrated-v3.0'}
 try:spot=fetch_spot();p['market']=spot
 except Exception as e:err.append('spot: '+str(e));spot=None
 macro={}
 for s in MACRO_SERIES:
  try:macro[s]=yahoo_quote(s)
  except Exception as e:err.append(f'Yahoo {s}: {e}')
 p['macro']=macro
 try:w=fetch_wgc(now);p['fundamentals']=w
 except Exception as e:err.append('WGC: '+str(e));w=None
 cal=load_json(CAL);fcal=load_json(FCAL);p['calibration']=cal;p['fundamentals_calibration']=fcal;mp=fair_value(macro,cal,spot['usd_oz']) if spot else None
 if spot and w and mp:
  ph=overlay(w,fcal);raw=mp*ph['multiplier'];lo,hi=.55*spot['usd_oz'],1.55*spot['usd_oz'];ps=min(max(raw,lo),hi);wg=(cal or {}).get('walk_forward_gate') or 'PENDING';fg=(fcal or {}).get('walk_forward_gate') or 'PENDING';fully_valid=wg=='PASS' and fg=='PASS' and not err;status='VALID' if fully_valid else 'PROVISIONAL';confidence='HIGH' if fully_valid else ('MEDIUM' if wg=='PASS' else 'LOW')
  p['model']={'weekly_fair_value_usd_oz':round(mp,2),'macro_fair_value_usd_oz':round(mp,2),'physical_overlay':{k:(round(v,6) if isinstance(v,float) else v) for k,v in ph.items()},'fundamental_p_star_usd_oz':round(ps,2),'raw_combined_p_star_usd_oz':round(raw,2),'market_vs_pstar_pct':round((spot['usd_oz']/ps-1)*100,2),'guardrail_active':ps!=raw or bool(ph.get('guardrail_active')),'status':status,'confidence':confidence,'governance':{'weekly_walk_forward':wg,'fundamentals_historical_calibration':fg,'no_imputation':True,'publication_gate':'VALID' if fully_valid else 'PROVISIONAL_ONLY'}};p['model_status']=status
 else:p['model']=None;p['model_status']='UNAVAILABLE'
 p['errors']=err;p['data_quality']='OK' if not err else 'DEGRADED';OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(p,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');print(json.dumps(p,ensure_ascii=False,indent=2))
if __name__=='__main__':main()
