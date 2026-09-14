#!/usr/bin/env python3
"""Weekly gold fair-value calibration.

Target: weekly XAU/USD close from Stooq.
Predictors: weekly-average public FRED macro series, lagged one full week.
No forward/back filling is used. Only weeks with complete target and predictors enter the sample.
"""
from __future__ import annotations
import csv,io,json,math,statistics,urllib.request
from datetime import datetime,timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/'docs/gold/data/weekly_calibration.json'
GOLD='https://stooq.com/q/d/l/?s=xauusd&d1=20100101&i=w'
SER=['DFII10','DTWEXBGS','T10YIE','VIXCLS']

def get(u,timeout=90):
 r=urllib.request.Request(u,headers={'User-Agent':'GoldEquilibriumPrice/0.4'})
 with urllib.request.urlopen(r,timeout=timeout) as x:return x.read().decode('utf-8',errors='replace')
def monday(date):
 d=datetime.strptime(date[:10],'%Y-%m-%d').date();return (d.toordinal()-d.weekday())
def read_gold():
 out={}
 for r in csv.DictReader(io.StringIO(get(GOLD))):
  try:out[monday(r['Date'])]=float(r['Close'])
  except:pass
 return out
def read_fred(s):
 # FRED graph aggregation keeps transport size small and uses weekly average for daily inputs.
 u=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2009-12-28&fq=Weekly&fam=Average'
 out={}
 for r in csv.DictReader(io.StringIO(get(u))):
  v=(r.get(s) or '').strip()
  if v not in ('','.'):
   try:out[monday(r['DATE'])]=float(v)
   except:pass
 return out,u
def solve(A,b):
 n=len(b);M=[A[i][:]+[b[i]] for i in range(n)]
 for c in range(n):
  p=max(range(c,n),key=lambda r:abs(M[r][c]));M[c],M[p]=M[p],M[c];z=M[c][c]
  if abs(z)<1e-12:raise RuntimeError('singular matrix')
  M[c]=[v/z for v in M[c]]
  for r in range(n):
   if r==c:continue
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
 X=[[1.0]+[(v-m)/s for v,m,s in zip(r[2],mu,sd)] for r in rows]
 return X,mu,sd
def metrics(y,p):
 mean=statistics.fmean(y);den=sum((v-mean)**2 for v in y)
 return {'r2':1-sum((a-b)**2 for a,b in zip(y,p))/den,'mape_pct':100*statistics.fmean(abs((a-b)/a) for a,b in zip(y,p)),'rmse_usd_oz':math.sqrt(statistics.fmean((a-b)**2 for a,b in zip(y,p)))}
def main():
 g=read_gold();f={};urls={}
 for s in SER:f[s],urls[s]=read_fred(s)
 weeks=sorted(set(g).intersection(*[set(f[s]) for s in SER]));raw=[(w,g[w],[f[s][w] for s in SER]) for w in weeks]
 # Features in week t predict gold close in week t+1. Enforce exactly one calendar week gap.
 rows=[]
 for i in range(1,len(raw)):
  pw,_,px=raw[i-1];w,p,_=raw[i]
  if w-pw==7:rows.append((w,p,px))
 if len(rows)<260:raise RuntimeError(f'insufficient complete weekly history: {len(rows)}')
 min_train=156;pred=[];act=[];dates=[]
 for i in range(min_train,len(rows)):
  tr=rows[:i];X,mu,sd=design(tr);be=fit(X,[math.log(r[1]) for r in tr]);x=[1.0]+[(v-m)/s for v,m,s in zip(rows[i][2],mu,sd)];pred.append(math.exp(sum(a*b for a,b in zip(x,be))));act.append(rows[i][1]);dates.append(datetime.fromordinal(rows[i][0]).date().isoformat())
 X,mu,sd=design(rows);be=fit(X,[math.log(r[1]) for r in rows]);m=metrics(act,pred)
 M={'n_weeks_total':len(rows),'walk_forward_n':len(pred),'walk_forward_start':dates[0],'walk_forward_end':dates[-1],'r2':round(m['r2'],4),'mape_pct':round(m['mape_pct'],3),'rmse_usd_oz':round(m['rmse_usd_oz'],2)}
 # At least 5 years of weekly OOS testing.
 passed=len(pred)>=260 and M['r2']>=0.60 and M['mape_pct']<=12.0
 out={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'model':'weekly-macro-ridge-v1','frequency':'weekly','target_source':GOLD,'macro_sources':urls,'series':SER,'beta':be,'means':mu,'sds':sd,'ridge_lambda':4.0,'metrics':M,'walk_forward_gate':'PASS' if passed else 'FAIL','publication_status':'CALIBRATED' if passed else 'PROVISIONAL','rules':{'min_training_weeks':156,'min_oos_weeks':260,'max_mape_pct':12.0,'min_r2':0.60,'lookahead':'none; predictors lagged one full week','missing_data':'complete-case only; no imputation'}}
 OUT.parent.mkdir(parents=True,exist_ok=True);OUT.write_text(json.dumps(out,indent=2),encoding='utf-8');print(json.dumps(out,indent=2))
if __name__=='__main__':main()
