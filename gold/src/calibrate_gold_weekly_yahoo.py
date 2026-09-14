#!/usr/bin/env python3
"""Weekly gold walk-forward calibration using Yahoo chart API (no API key).
Target: COMEX gold futures GC=F weekly close.
Predictors: Dollar Index DX-Y.NYB, 10Y yield ^TNX, VIX ^VIX, TIPS ETF TIP.
All predictor values are lagged one full week. No missing-value interpolation.
"""
from __future__ import annotations
import json,math,statistics,urllib.parse,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/gold/data/weekly_calibration.json'
TARGET='GC=F';SER=['DX-Y.NYB','^TNX','^VIX','TIP']
START=1262304000

def chart(symbol):
 q=urllib.parse.quote(symbol,safe='');now=int(datetime.now(timezone.utc).timestamp())
 u=f'https://query1.finance.yahoo.com/v8/finance/chart/{q}?period1={START}&period2={now}&interval=1wk&events=history&includeAdjustedClose=true'
 r=urllib.request.Request(u,headers={'User-Agent':'Mozilla/5.0 GoldEquilibriumPrice/1.2','Accept':'application/json'})
 with urllib.request.urlopen(r,timeout=60) as x:j=json.loads(x.read().decode())
 res=((j.get('chart') or {}).get('result') or [None])[0]
 if not res:raise RuntimeError(f'Yahoo empty result {symbol}: {(j.get("chart") or {}).get("error")}')
 ts=res.get('timestamp') or [];cl=(((res.get('indicators') or {}).get('quote') or [{}])[0].get('close') or [])
 out={}
 for t,v in zip(ts,cl):
  if v is not None and math.isfinite(float(v)):out[int(t)//604800]=float(v)
 return out,u

def solve(A,b):
 n=len(b);M=[A[i][:]+[b[i]] for i in range(n)]
 for c in range(n):
  p=max(range(c,n),key=lambda r:abs(M[r][c]));M[c],M[p]=M[p],M[c];z=M[c][c]
  if abs(z)<1e-12:raise RuntimeError('singular matrix')
  M[c]=[v/z for v in M[c]]
  for r in range(n):
   if r!=c:
    z=M[r][c];M[r]=[M[r][j]-z*M[c][j] for j in range(n+1)]
 return [M[i][-1] for i in range(n)]
def fit(X,y,lam=4.0):
 p=len(X[0]);A=[[0.0]*p for _ in range(p)];b=[0.0]*p
 for x,t in zip(X,y):
  for i in range(p):
   b[i]+=x[i]*t
   for j in range(p):A[i][j]+=x[i]*x[j]
 for i in range(1,p):A[i][i]+=lam
 return solve(A,b)
def design(rows):
 cols=list(zip(*[r[2] for r in rows]));mu=[statistics.fmean(c) for c in cols];sd=[statistics.pstdev(c) or 1 for c in cols]
 return [[1.0]+[(v-m)/s for v,m,s in zip(r[2],mu,sd)] for r in rows],mu,sd

def main():
 g,gu=chart(TARGET);f={};urls={}
 for s in SER:f[s],urls[s]=chart(s)
 weeks=sorted(set(g).intersection(*[set(f[s]) for s in SER]));raw=[(w,g[w],[f[s][w] for s in SER]) for w in weeks];rows=[]
 for i in range(1,len(raw)):
  pw,_,px=raw[i-1];w,p,_=raw[i]
  if w-pw==1:rows.append((w,p,px))
 if len(rows)<260:raise RuntimeError(f'insufficient weekly history {len(rows)}; counts target={len(g)} predictors='+str({s:len(f[s]) for s in SER})+f'; overlap={len(weeks)}')
 min_train=156;pred=[];act=[];dates=[]
 for i in range(min_train,len(rows)):
  tr=rows[:i];X,mu,sd=design(tr);be=fit(X,[math.log(r[1]) for r in tr]);x=[1.0]+[(v-m)/s for v,m,s in zip(rows[i][2],mu,sd)];pred.append(math.exp(sum(a*b for a,b in zip(x,be))));act.append(rows[i][1]);dates.append(datetime.fromtimestamp(rows[i][0]*604800,tz=timezone.utc).date().isoformat())
 X,mu,sd=design(rows);be=fit(X,[math.log(r[1]) for r in rows]);mean=statistics.fmean(act);r2=1-sum((a-b)**2 for a,b in zip(act,pred))/sum((a-mean)**2 for a in act);mape=100*statistics.fmean(abs((a-b)/a) for a,b in zip(act,pred));rmse=math.sqrt(statistics.fmean((a-b)**2 for a,b in zip(act,pred)));M={'n_weeks_total':len(rows),'walk_forward_n':len(pred),'walk_forward_start':dates[0],'walk_forward_end':dates[-1],'r2':round(r2,4),'mape_pct':round(mape,3),'rmse_usd_oz':round(rmse,2)};passed=len(pred)>=260 and r2>=.60 and mape<=12
 out={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'model':'weekly-yahoo-macro-ridge-v1','frequency':'weekly','target':'GC=F','target_source':gu,'series':SER,'predictor_sources':urls,'beta':be,'means':mu,'sds':sd,'ridge_lambda':4.0,'metrics':M,'walk_forward_gate':'PASS' if passed else 'FAIL','publication_status':'CALIBRATED' if passed else 'PROVISIONAL','rules':{'min_training_weeks':156,'min_oos_weeks':260,'max_mape_pct':12.0,'min_r2':0.60,'lookahead':'none; predictors lagged one full week','missing_data':'complete-case only; no imputation'}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
