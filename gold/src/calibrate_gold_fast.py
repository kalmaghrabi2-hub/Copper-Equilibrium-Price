#!/usr/bin/env python3
import csv,io,json,math,statistics,urllib.request
from collections import defaultdict
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2];OUT=ROOT/'docs/gold/data/calibration.json'
GOLD='https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly-processed.csv'
SER=['DFII10','DTWEXBGS','T10YIE','VIXCLS','M2SL']

def get(u):
 r=urllib.request.Request(u,headers={'User-Agent':'GoldEquilibriumPrice/0.3'})
 with urllib.request.urlopen(r,timeout=75) as x:return x.read().decode()
def month(s):return s[:7]
def series(s):
 u=f'https://fred.stlouisfed.org/graph/fredgraph.csv?id={s}&cosd=2009-12-01';b=defaultdict(list)
 for r in csv.DictReader(io.StringIO(get(u))):
  v=(r.get(s) or '').strip()
  if v not in ('','.'):
   try:b[month(r['DATE'])].append(float(v))
   except:pass
 return {m:statistics.fmean(v) for m,v in b.items()}
def solve(A,b):
 n=len(b);M=[A[i][:]+[b[i]] for i in range(n)]
 for c in range(n):
  p=max(range(c,n),key=lambda r:abs(M[r][c]));M[c],M[p]=M[p],M[c];z=M[c][c]
  if abs(z)<1e-12:raise RuntimeError('singular')
  M[c]=[v/z for v in M[c]]
  for r in range(n):
   if r!=c:
    z=M[r][c];M[r]=[M[r][j]-z*M[c][j] for j in range(n+1)]
 return [M[i][-1] for i in range(n)]
def fit(X,y,lam=2):
 p=len(X[0]);A=[[0.0]*p for _ in range(p)];b=[0.0]*p
 for x,t in zip(X,y):
  for i in range(p):
   b[i]+=x[i]*t
   for j in range(p):A[i][j]+=x[i]*x[j]
 for i in range(1,p):A[i][i]+=lam
 return solve(A,b)
def design(rows):
 cols=list(zip(*[r[2] for r in rows]));mu=[statistics.fmean(c) for c in cols];sd=[statistics.pstdev(c) or 1 for c in cols]
 X=[[1.0]+[(v-m)/s for v,m,s in zip(r[2],mu,sd)] for r in rows];return X,mu,sd
def main():
 g={month(r['Date']):float(r['Price']) for r in csv.DictReader(io.StringIO(get(GOLD))) if r['Date']>='2010-01-01'}
 f={s:series(s) for s in SER};months=sorted(set(g).intersection(*[set(f[s]) for s in SER]));raw=[(m,g[m],[f[s][m] for s in SER]) for m in months]
 rows=[]
 for i in range(1,len(raw)):
  pm,_,px=raw[i-1];m,p,_=raw[i];y0,mo0=map(int,pm.split('-'));y1,mo1=map(int,m.split('-'))
  if y1*12+mo1-y0*12-mo0==1:rows.append((m,p,px))
 if len(rows)<72:raise RuntimeError(f'complete months={len(rows)}')
 pred=[];act=[];dates=[]
 for i in range(60,len(rows)):
  tr=rows[:i];X,mu,sd=design(tr);be=fit(X,[math.log(r[1]) for r in tr]);x=[1]+[(v-m)/s for v,m,s in zip(rows[i][2],mu,sd)];pred.append(math.exp(sum(a*b for a,b in zip(x,be))));act.append(rows[i][1]);dates.append(rows[i][0])
 X,mu,sd=design(rows);be=fit(X,[math.log(r[1]) for r in rows]);mean=statistics.fmean(act);r2=1-sum((a-b)**2 for a,b in zip(act,pred))/sum((a-mean)**2 for a in act);mape=100*statistics.fmean(abs((a-b)/a) for a,b in zip(act,pred));rmse=math.sqrt(statistics.fmean((a-b)**2 for a,b in zip(act,pred)));ok=len(pred)>=84 and r2>=.60 and mape<=15
 out={'generated_at_utc':datetime.now(timezone.utc).isoformat(),'model':'macro-ridge-v1','series':SER,'beta':be,'means':mu,'sds':sd,'ridge_lambda':2.0,'metrics':{'n_months_total':len(rows),'walk_forward_n':len(pred),'walk_forward_start':dates[0],'walk_forward_end':dates[-1],'r2':round(r2,4),'mape_pct':round(mape,3),'rmse_usd_oz':round(rmse,2)},'walk_forward_gate':'PASS' if ok else 'FAIL','publication_status':'CALIBRATED' if ok else 'PROVISIONAL'}
 OUT.write_text(json.dumps(out,indent=2));print(json.dumps(out,indent=2))
if __name__=='__main__':main()
