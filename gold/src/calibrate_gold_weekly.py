#!/usr/bin/env python3
"""Weekly gold fair-value calibration using reproducible Stooq market proxies.

Target: XAU/USD weekly close.
Predictors: US Dollar Index futures (DX.F), US 10Y yield (10USY.B),
US 2Y yield (2USY.B), and VIX (^VIX). Predictors are lagged one full week.
Only complete weeks enter the sample; no interpolation or backfill.
"""
from __future__ import annotations
import csv,io,json,math,statistics,urllib.request
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/gold/data/weekly_calibration.json'
TARGET='xauusd';SER=['dx.f','10usy.b','2usy.b','^vix']
def url(s):return f'https://stooq.com/q/d/l/?s={s}&d1=20100101&i=w'
def get(u,timeout=60):
 r=urllib.request.Request(u,headers={'User-Agent':'GoldEquilibriumPrice/1.0'})
 with urllib.request.urlopen(r,timeout=timeout) as x:return x.read().decode('utf-8',errors='replace')
def monday(d):
 x=datetime.strptime(d[:10],'%Y-%m-%d').date();return x.toordinal()-x.weekday()
def read(s):
 out={}
 for r in csv.DictReader(io.StringIO(get(url(s)))):
  try:out[monday(r['Date'])]=float(r['Close'])
  except:pass
 return out
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
 g=read(TARGET);f={s:read(s) for s in SER};weeks=sorted(set(g).intersection(*[set(f[s]) for s in SER]));raw=[(w,g[w],[f[s][w] for s in SER]) for w in weeks];rows=[]
 for i in range(1,len(raw)):
  pw,_,px=raw[i-1];w,p,_=raw[i]
  if w-pw==7:rows.append((w,p,px))
 if len(rows)<260:raise RuntimeError(f'insufficient complete weekly history: {len(rows)}')
 pred=[];act=[];dates=[];min_train=156
 for i in range(min_train,len(rows)):
  tr=rows[:i];X,mu,sd=design(tr);be=fit(X,[math.log(r[1]) for r in tr]);x=[1.0]+[(v-m)/s for v,m,s in zip(rows[i][2],mu,sd)];pred.append(math.exp(sum(a*b for a,b in zip(x,be))));act.append(rows[i][1]);dates.append(datetime.fromordinal(rows[i][0]).date().isoformat())
 X,mu,sd=design(rows);be=fit(X,[math.log(r[1]) for r in rows]);mean=statistics.fmean(act);r2=1-sum((a-b)**2 for a,b in zip(act,pred))/sum((a-mean)**2 for a in act);mape=100*statistics.fmean(abs((a-b)/a) for a,b in zip(act,pred));rmse=math.sqrt(statistics.fmean((a-b)**2 for a,b in zip(act,pred)));M={'n_weeks_total':len(rows),'walk_forward_n':len(pred),'walk_forward_start':dates[0],'walk_forward_end':dates[-1],'r2':round(r2,4),'mape_pct':round(mape,3),'rmse_usd_oz':round(rmse,2)};passed=len(pred)>=260 and r2>=.60 and mape<=12
 out={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'model':'weekly-market-macro-ridge-v2','frequency':'weekly','target_source':url(TARGET),'predictor_sources':{s:url(s) for s in SER},'series':SER,'beta':be,'means':mu,'sds':sd,'ridge_lambda':4.0,'metrics':M,'walk_forward_gate':'PASS' if passed else 'FAIL','publication_status':'CALIBRATED' if passed else 'PROVISIONAL','rules':{'min_training_weeks':156,'min_oos_weeks':260,'max_mape_pct':12.0,'min_r2':0.60,'lookahead':'none; predictors lagged one full week','missing_data':'complete-case only; no imputation'}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
