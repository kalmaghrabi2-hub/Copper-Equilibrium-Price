#!/usr/bin/env python3
"""Calibrate the gold macro fair-value layer and run expanding walk-forward tests.

Data policy:
- Gold monthly price: datasets/gold-prices (World Bank Pink Sheet for modern era).
- Macro: FRED public CSV exports.
- Evaluation starts in 2015 after a minimum 60-month training window.
- Predictors are lagged one month in walk-forward tests to avoid look-ahead.
- No interpolation of missing critical observations.
"""
from __future__ import annotations
import csv, io, json, math, statistics, urllib.request
from collections import defaultdict
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT / 'docs' / 'gold' / 'data' / 'calibration.json'
GOLD_URL = 'https://raw.githubusercontent.com/datasets/gold-prices/main/data/monthly-processed.csv'
FRED_URL = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
SERIES = ['DFII10','DTWEXBGS','T10YIE','VIXCLS','CPIAUCSL','M2SL']
UA = 'GoldEquilibriumPrice/0.2'

def get(url):
    req=urllib.request.Request(url,headers={'User-Agent':UA})
    with urllib.request.urlopen(req,timeout=30) as r:return r.read().decode('utf-8')

def ym(s): return s[:7]

def read_gold():
    d={}
    for r in csv.DictReader(io.StringIO(get(GOLD_URL))):
        if r['Date']>='2010-01-01': d[ym(r['Date'])]=float(r['Price'])
    return d

def read_fred(series):
    buckets=defaultdict(list)
    rows=list(csv.DictReader(io.StringIO(get(FRED_URL.format(series)))))
    for r in rows:
        raw=(r.get(series) or '').strip()
        if raw in ('','.'): continue
        try: buckets[ym(r['DATE'])].append(float(raw))
        except Exception: pass
    return {m:statistics.fmean(v) for m,v in buckets.items() if v}

def solve(A,b):
    n=len(b); M=[list(map(float,A[i]))+[float(b[i])] for i in range(n)]
    for col in range(n):
        pivot=max(range(col,n),key=lambda r:abs(M[r][col]))
        if abs(M[pivot][col])<1e-12: raise ValueError('singular')
        M[col],M[pivot]=M[pivot],M[col]
        z=M[col][col]; M[col]=[v/z for v in M[col]]
        for r in range(n):
            if r==col: continue
            z=M[r][col]
            if z: M[r]=[M[r][c]-z*M[col][c] for c in range(n+1)]
    return [M[i][-1] for i in range(n)]

def ridge_fit(X,y,lam=2.0):
    p=len(X[0]); xtx=[[0.0]*p for _ in range(p)]; xty=[0.0]*p
    for row,target in zip(X,y):
        for i in range(p):
            xty[i]+=row[i]*target
            for j in range(p): xtx[i][j]+=row[i]*row[j]
    for i in range(1,p): xtx[i][i]+=lam
    return solve(xtx,xty)

def dot(a,b): return sum(x*y for x,y in zip(a,b))

def r2(y,p):
    mu=statistics.fmean(y); den=sum((v-mu)**2 for v in y)
    return 1-sum((a-b)**2 for a,b in zip(y,p))/den if den else 0.0

def mape(y,p): return 100*statistics.fmean(abs((a-b)/a) for a,b in zip(y,p) if a)

def rmse(y,p): return math.sqrt(statistics.fmean((a-b)**2 for a,b in zip(y,p)))

def build_rows():
    gold=read_gold(); macro={s:read_fred(s) for s in SERIES}
    months=sorted(set(gold).intersection(*[set(v) for v in macro.values()]))
    raw=[]
    for m in months:
        vals=[macro[s][m] for s in SERIES]
        if any(not math.isfinite(v) for v in vals): continue
        raw.append((m,gold[m],vals))
    # Standardise using only training sample at each fit; raw rows are retained.
    return raw

def design(train_rows, predict_rows):
    cols=list(zip(*[r[2] for r in train_rows]))
    means=[statistics.fmean(c) for c in cols]
    sds=[statistics.pstdev(c) or 1.0 for c in cols]
    def x(vals):
        z=[(v-m)/s for v,m,s in zip(vals,means,sds)]
        # log transforms are represented by standardised monthly levels; intercept first.
        return [1.0]+z
    return [x(r[2]) for r in train_rows],[x(r[2]) for r in predict_rows],means,sds

def main():
    rows=build_rows()
    # one-month lag: features from t-1 predict gold price at t
    lagged=[]
    idx={m:i for i,(m,_,_) in enumerate(rows)}
    for i in range(1,len(rows)):
        pm,_,px=rows[i-1]; m,price,_=rows[i]
        y0,mo0=map(int,pm.split('-')); y1,mo1=map(int,m.split('-'))
        if (y1*12+mo1)-(y0*12+mo0)==1: lagged.append((m,price,px))
    preds=[]; actual=[]; dates=[]
    min_train=60
    for i in range(min_train,len(lagged)):
        train=lagged[:i]; test=[lagged[i]]
        X,XT,_,_=design(train,test)
        y=[math.log(r[1]) for r in train]
        beta=ridge_fit(X,y,lam=2.0)
        pred=math.exp(dot(XT[0],beta))
        dates.append(test[0][0]); actual.append(test[0][1]); preds.append(pred)
    # Final fit uses all lagged history; latest available macro values are used by live engine.
    X,_,means,sds=design(lagged,[])
    beta=ridge_fit(X,[math.log(r[1]) for r in lagged],lam=2.0)
    metrics={
        'n_months_total':len(lagged),'walk_forward_n':len(preds),
        'walk_forward_start':dates[0] if dates else None,'walk_forward_end':dates[-1] if dates else None,
        'r2':round(r2(actual,preds),4) if preds else None,
        'mape_pct':round(mape(actual,preds),3) if preds else None,
        'rmse_usd_oz':round(rmse(actual,preds),2) if preds else None,
    }
    # Governance thresholds: explanatory R2 >= .60 and MAPE <= 15% with >=84 OOS months.
    passed=bool(preds and len(preds)>=84 and metrics['r2']>=0.60 and metrics['mape_pct']<=15.0)
    out={
      'generated_at_utc':datetime.utcnow().isoformat()+'Z','model':'macro-ridge-v1',
      'price_source':GOLD_URL,'macro_sources':{s:FRED_URL.format(s) for s in SERIES},
      'series':SERIES,'beta':beta,'means':means,'sds':sds,'ridge_lambda':2.0,
      'metrics':metrics,'walk_forward_gate':'PASS' if passed else 'FAIL',
      'publication_status':'CALIBRATED' if passed else 'PROVISIONAL',
      'rules':{'min_training_months':60,'min_oos_months':84,'max_mape_pct':15.0,'min_r2':0.60,'lookahead':'none; predictors lagged one month'},
    }
    OUT.parent.mkdir(parents=True,exist_ok=True)
    OUT.write_text(json.dumps(out,indent=2),encoding='utf-8')
    print(json.dumps(out,indent=2))

if __name__=='__main__': main()
