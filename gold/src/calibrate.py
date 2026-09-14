#!/usr/bin/env python3
from __future__ import annotations
import io, json, math
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
import pandas as pd
import requests
from sklearn.linear_model import Ridge
from sklearn.metrics import r2_score, mean_absolute_percentage_error

ROOT = Path(__file__).resolve().parents[2]
MODEL_OUT = ROOT / 'gold' / 'model' / 'model.json'
UA = 'GoldEquilibriumPrice/2.0 (+https://github.com/kalmaghrabi2-hub/copper-equilibrium-price)'
FRED = 'https://fred.stlouisfed.org/graph/fredgraph.csv?id={}'
LEGACY_GOLD = 'https://raw.githubusercontent.com/tohaitrieu/market-history/master/data/commodities/GOLD/GOLD-D1.csv'
XAUS_HISTORY = 'https://xaus.com/api/v1/history?range=5y'
FEATURES = ['REAL_YIELD_EASING','USD_WEAKENING','BREAKEVEN_RISE','VIX_RISE','GOLD_MOMENTUM_L1']

def get(url: str, timeout: int = 60) -> bytes:
    r = requests.get(url, headers={'User-Agent': UA}, timeout=timeout)
    r.raise_for_status()
    return r.content

def fred(series: str) -> pd.Series:
    raw = pd.read_csv(io.BytesIO(get(FRED.format(series))))
    if raw.shape[1] != 2:
        raise RuntimeError(f'Unexpected FRED schema for {series}: {list(raw.columns)}')
    raw.columns = ['date', series]
    raw['date'] = pd.to_datetime(raw['date'], errors='coerce')
    raw[series] = pd.to_numeric(raw[series], errors='coerce')
    return raw.dropna().set_index('date')[series].sort_index()

def gold_price() -> pd.Series:
    raw = pd.read_csv(io.BytesIO(get(LEGACY_GOLD)))
    if not {'Time','Close'}.issubset(raw.columns):
        raise RuntimeError(f'Unexpected legacy gold schema: {list(raw.columns)}')
    dates = pd.to_datetime(raw['Time'], errors='coerce')
    close = pd.to_numeric(raw['Close'], errors='coerce')
    legacy = pd.Series(close.values, index=dates, name='gold').dropna().sort_index()
    legacy = legacy[~legacy.index.duplicated(keep='last')]

    live_json = requests.get(XAUS_HISTORY, headers={'User-Agent': UA}, timeout=60)
    live_json.raise_for_status()
    data = live_json.json()
    points = data.get('points') or []
    if not points:
        raise RuntimeError('XAUS history returned no points')
    live = pd.DataFrame(points)
    if not {'d','c'}.issubset(live.columns):
        raise RuntimeError(f'Unexpected XAUS history schema: {list(live.columns)}')
    live['date'] = pd.to_datetime(live['d'], errors='coerce')
    live['gold'] = pd.to_numeric(live['c'], errors='coerce')
    live_s = live.dropna(subset=['date','gold']).set_index('date')['gold'].sort_index()

    combined = pd.concat([legacy, live_s]).sort_index()
    combined = combined[~combined.index.duplicated(keep='last')]
    now = pd.Timestamp(datetime.now(timezone.utc).date())
    if combined.empty or combined.index.min().year > 2010:
        raise RuntimeError('Gold history does not reach 2010')
    if (now - combined.index.max().tz_localize(None)).days > 10:
        raise RuntimeError(f'Gold history stale: last date {combined.index.max().date()}')
    return combined.rename('gold')

def build_monthly() -> pd.DataFrame:
    daily = pd.concat([gold_price(), fred('DFII10'), fred('DTWEXBGS'), fred('T10YIE'), fred('VIXCLS')], axis=1).sort_index()
    macro_cols = ['DFII10','DTWEXBGS','T10YIE','VIXCLS']
    daily[macro_cols] = daily[macro_cols].ffill(limit=7)
    m = daily.loc['2010-01-01':].resample('ME').mean()
    current_month_start = pd.Timestamp(datetime.now(timezone.utc).date()).replace(day=1)
    m = m[m.index < current_month_start]
    m['PREV_GOLD'] = m['gold'].shift(1)
    m['TARGET_RETURN'] = np.log(m['gold'] / m['PREV_GOLD'])
    m['REAL_YIELD_EASING'] = -m['DFII10'].diff()
    m['USD_WEAKENING'] = -np.log(m['DTWEXBGS']).diff()
    m['BREAKEVEN_RISE'] = m['T10YIE'].diff()
    m['VIX_RISE'] = np.log(m['VIXCLS'].clip(lower=1.0)).diff()
    m['GOLD_MOMENTUM_L1'] = m['TARGET_RETURN'].shift(1)
    return m.dropna(subset=['gold','PREV_GOLD','TARGET_RETURN'] + FEATURES)

def fit_standardized_ridge(train: pd.DataFrame, alpha: float):
    mu = train[FEATURES].mean()
    sd = train[FEATURES].std(ddof=0).replace(0, 1.0)
    X = (train[FEATURES] - mu) / sd
    model = Ridge(alpha=alpha, fit_intercept=True)
    model.fit(X.values, train['TARGET_RETURN'].values)
    return model, mu, sd

def predict_return(model, mu, sd, frame: pd.DataFrame) -> np.ndarray:
    X = (frame[FEATURES] - mu) / sd
    return model.predict(X.values)

def choose_alpha(df: pd.DataFrame) -> float:
    train = df.loc[:'2016-12-31']
    valid = df.loc['2017-01-01':'2018-12-31']
    if len(train) < 60 or len(valid) < 12:
        return 10.0
    best = None
    for a in (0.1, 1.0, 10.0, 100.0):
        model, mu, sd = fit_standardized_ridge(train, a)
        pred_ret = predict_return(model, mu, sd, valid)
        pred_price = valid['PREV_GOLD'].values * np.exp(pred_ret)
        mape = mean_absolute_percentage_error(valid['gold'].values, pred_price)
        if best is None or mape < best[0]:
            best = (mape, a)
    return float(best[1])

def walk_forward(df: pd.DataFrame, alpha: float) -> pd.DataFrame:
    rows = []
    for dt, row in df.loc['2019-01-01':].iterrows():
        train = df.loc[:dt - pd.offsets.MonthEnd(1)]
        if len(train) < 72:
            continue
        model, mu, sd = fit_standardized_ridge(train, alpha)
        pred_ret = float(predict_return(model, mu, sd, row.to_frame().T)[0])
        pred_price = float(row['PREV_GOLD'] * math.exp(pred_ret))
        rows.append((dt, float(row['gold']), float(row['PREV_GOLD']), float(row['TARGET_RETURN']), pred_ret, pred_price))
    return pd.DataFrame(rows, columns=['date','actual','naive','actual_return','pred_return','pred']).set_index('date')

def main():
    df = build_monthly()
    alpha = choose_alpha(df)
    wf = walk_forward(df, alpha)
    mape = float(mean_absolute_percentage_error(wf['actual'], wf['pred'])) if len(wf) else math.nan
    naive_mape = float(mean_absolute_percentage_error(wf['actual'], wf['naive'])) if len(wf) else math.nan
    return_r2 = float(r2_score(wf['actual_return'], wf['pred_return'])) if len(wf) > 1 else math.nan
    price_r2 = float(r2_score(wf['actual'], wf['pred'])) if len(wf) > 1 else math.nan
    bias = float((wf['pred'] / wf['actual'] - 1.0).mean()) if len(wf) else math.nan
    direction = float((np.sign(wf['actual_return']) == np.sign(wf['pred_return'])).mean()) if len(wf) else math.nan
    improvement = float((naive_mape - mape) / naive_mape) if naive_mape and not math.isnan(naive_mape) else math.nan
    gate = bool(len(wf) >= 60 and mape <= 0.08 and abs(bias) <= 0.03 and direction >= 0.48 and improvement >= 0.0)

    final_model, mu, sd = fit_standardized_ridge(df, alpha)
    last = df.iloc[-1]
    payload = {
        'model_version': 'gold-macro-return-ridge-v2',
        'model_type': 'monthly_return_bridge',
        'generated_at_utc': datetime.now(timezone.utc).isoformat(),
        'target_sources': [LEGACY_GOLD, XAUS_HISTORY],
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
        'reference': {
            'month': df.index[-1].date().isoformat(),
            'gold_usd_oz': float(last['gold']),
            'DFII10': float(last['DFII10']),
            'DTWEXBGS': float(last['DTWEXBGS']),
            'T10YIE': float(last['T10YIE']),
            'VIXCLS': float(last['VIXCLS']),
            'gold_momentum_l1': float(last['TARGET_RETURN'])
        },
        'metrics': {
            'mape': mape,
            'naive_mape': naive_mape,
            'improvement_vs_naive_pct': improvement * 100.0,
            'return_r2': return_r2,
            'price_r2': price_r2,
            'directional_accuracy': direction,
            'mean_bias': bias
        },
        'macro_validation_gate': 'PASS' if gate else 'FAIL',
        'notes': [
            'Model predicts monthly gold return from changes in real yield, broad USD, breakeven inflation, VIX and lagged gold return.',
            'Training uses only completed months; the current partial month is excluded.',
            'Walk-forward refits on prior observations only. Current-month macro variables are contemporaneous fair-value inputs, not future information.',
            'The validation gate also compares against a naive previous-month-price baseline and will not pass if the model does not improve on it.',
            'Physical WGC overlay remains a separate governance gate.'
        ]
    }
    MODEL_OUT.parent.mkdir(parents=True, exist_ok=True)
    MODEL_OUT.write_text(json.dumps(payload, indent=2) + '\n', encoding='utf-8')
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()
