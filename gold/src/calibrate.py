#!/usr/bin/env python3
from __future__ import annotations
import json, math, io
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_percentage_error

ROOT = Path(__file__).resolve().parents[2]
MODEL_OUT = ROOT / 'gold' / 'model' / 'model.json'
UA = 'GoldEquilibriumPrice/1.0 (+https://github.com/kalmaghrabi2-hub/copper-equilibrium-price)'
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
STOOQ = 'https://stooq.com/q/d/l/?s=xauusd&i=d'
FEATURES = ['DFII10','DTWEXBGS','T10YIE','VIXCLS_LOG']

def get(url: str, timeout: int = 40) -> bytes:
    r = requests.get(url, headers={'User-Agent': UA}, timeout=timeout)
    r.raise_for_status()
    return r.content

def fred(series: str) -> pd.Series:
    raw = pd.read_csv(io.BytesIO(get(FRED.format(series))))
    raw.columns = ['date', series]
    raw['date'] = pd.to_datetime(raw['date'])
    raw[series] = pd.to_numeric(raw[series], errors='coerce')
    return raw.dropna().set_index('date')[series].sort_index()

def gold_price() -> pd.Series:
    raw = pd.read_csv(io.BytesIO(get(STOOQ)))
    raw.columns = [c.lower() for c in raw.columns]
    raw['date'] = pd.to_datetime(raw['date'])
    s = pd.to_numeric(raw['close'], errors='coerce')
    s.index = raw['date']
    s = s.dropna().sort_index()
    if s.empty or s.index.max().year < 2024:
        raise RuntimeError('Stooq XAUUSD history is missing/stale')
    return s.rename('gold')

def build_monthly() -> pd.DataFrame:
    daily = pd.concat([gold_price(), fred('DFII10'), fred('DTWEXBGS'), fred('T10YIE'), fred('VIXCLS')], axis=1).sort_index()
    daily[['DFII10','DTWEXBGS','T10YIE','VIXCLS']] = daily[['DFII10','DTWEXBGS','T10YIE','VIXCLS']].ffill(limit=7)
    m = daily.loc['2010-01-01':].resample('ME').mean()
    m['VIXCLS_LOG'] = np.log(m['VIXCLS'].clip(lower=1.0))
    m['target'] = np.log(m['gold'])
    return m.dropna(subset=['target'] + FEATURES)

def fit_standardized_ridge(train: pd.DataFrame, alpha: float):
    mu = train[FEATURES].mean()
    sd = train[FEATURES].std(ddof=0).replace(0, 1.0)
    X = (train[FEATURES] - mu) / sd
    model = Ridge(alpha=alpha, fit_intercept=True)
    model.fit(X.values, train['target'].values)
    return model, mu, sd

def predict(model, mu, sd, frame: pd.DataFrame) -> np.ndarray:
    X = (frame[FEATURES] - mu) / sd
    return np.exp(model.predict(X.values))

def choose_alpha(df: pd.DataFrame) -> float:
    train = df.loc[:'2016-12-31']
    valid = df.loc['2017-01-01':'2018-12-31']
    if len(train) < 60 or len(valid) < 12:
        return 10.0
    best = None
    for a in (0.1, 1.0, 10.0, 100.0):
        m, mu, sd = fit_standardized_ridge(train, a)
        pred = predict(m, mu, sd, valid)
        mape = mean_absolute_percentage_error(valid['gold'].values, pred)
        if best is None or mape < best[0]:
            best = (mape, a)
    return float(best[1])

def walk_forward(df: pd.DataFrame, alpha: float) -> pd.DataFrame:
    rows = []
    test = df.loc['2019-01-01':]
    for dt, row in test.iterrows():
        train = df.loc[:dt - pd.offsets.MonthEnd(1)]
        if len(train) < 72:
            continue
        m, mu, sd = fit_standardized_ridge(train, alpha)
        p = float(predict(m, mu, sd, row.to_frame().T)[0])
        rows.append((dt, float(row['gold']), p))
    return pd.DataFrame(rows, columns=['date','actual','pred']).set_index('date')

def main():
    df = build_monthly()
    alpha = choose_alpha(df)
    wf = walk_forward(df, alpha)
    mape = float(mean_absolute_percentage_error(wf['actual'], wf['pred'])) if len(wf) else math.nan
    r2 = float(r2_score(wf['actual'], wf['pred'])) if len(wf) > 1 else math.nan
    bias = float((wf['pred'] / wf['actual'] - 1.0).mean()) if len(wf) else math.nan
    gate = bool(len(wf) >= 48 and mape <= 0.18 and r2 >= 0.25 and abs(bias) <= 0.10)
    final_model, mu, sd = fit_standardized_ridge(df, alpha)
    latest_macro_pstar = float(predict(final_model, mu, sd, df.iloc[[-1]])[0])
    payload = {
        'model_version': 'gold-macro-ridge-v1',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'training_start': df.index.min().date().isoformat(),
        'training_end': df.index.max().date().isoformat(),
        'observations_monthly': int(len(df)),
        'walk_forward_start': wf.index.min().date().isoformat() if len(wf) else None,
        'walk_forward_end': wf.index.max().date().isoformat() if len(wf) else None,
        'walk_forward_observations': int(len(wf)),
        'alpha': alpha,
        'features': FEATURES,
        'feature_mean': {k: float(v) for k,v in mu.items()},
        'feature_std': {k: float(v) for k,v in sd.items()},
        'intercept': float(final_model.intercept_),
        'coefficients_standardized': {f: float(c) for f, c in zip(FEATURES, final_model.coef_)},
        'metrics': {'mape': mape, 'r2': r2, 'mean_bias': bias},
        'macro_validation_gate': 'PASS' if gate else 'FAIL',
        'macro_pstar_latest_usd_oz': round(latest_macro_pstar, 2),
        'notes': [
            'Target is monthly average XAUUSD close from Stooq.',
            'Macro features are public FRED series; VIX is log-transformed.',
            'Walk-forward forecasts are one month ahead using only prior data.',
            'Physical WGC overlay is governed separately and remains provisional until continuous historical WGC data is machine-readable in production.'
        ]
    }
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    MODEL_OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()
