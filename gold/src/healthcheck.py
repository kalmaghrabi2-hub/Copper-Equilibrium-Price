#!/usr/bin/env python3
from __future__ import annotations
import json, sys
from datetime import datetime, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'docs'/'gold'/'data'/'latest.json'

def parse_dt(v):
    if not v: return None
    return datetime.fromisoformat(str(v).replace('Z','+00:00')).astimezone(timezone.utc)

def main():
    errors=[]
    try:
        d=json.loads(DATA.read_text(encoding='utf-8'))
    except Exception as e:
        print(f'HEALTHCHECK FAIL: latest.json unreadable: {e}')
        return 1
    now=datetime.now(timezone.utc)
    generated=parse_dt(d.get('generated_at_utc'))
    if not generated or (now-generated).total_seconds()>48*3600:
        errors.append('generated_at is missing or older than 48h')
    if d.get('data_quality')!='OK': errors.append(f"data_quality={d.get('data_quality')}")
    market=d.get('market') or {}
    if not isinstance(market.get('usd_oz'),(int,float)) or market.get('usd_oz',0)<=0:
        errors.append('market spot missing/non-positive')
    if market.get('freshness_status') not in ('fresh','fallback','unknown'):
        errors.append(f"market freshness={market.get('freshness_status')}")
    macro=d.get('macro') or {}
    max_days={'DFII10':10,'T10YIE':10,'VIXCLS':10,'DTWEXBGS':15}
    for key,days in max_days.items():
        item=macro.get(key) or {}
        if not isinstance(item.get('value'),(int,float)):
            errors.append(f'{key} value missing')
            continue
        try:
            dt=datetime.fromisoformat(item['date']).replace(tzinfo=timezone.utc)
            if (now-dt).days>days: errors.append(f'{key} stale: {item["date"]}')
        except Exception:
            errors.append(f'{key} date invalid')
    fund=d.get('fundamentals') or {}
    if not fund.get('quarter'): errors.append('WGC quarter missing')
    for key in ('mine_production_t','recycled_gold_t','bar_coin_t','central_banks_t','physical_multiplier'):
        if not isinstance(fund.get(key),(int,float)): errors.append(f'WGC {key} missing')
    model=d.get('model') or {}
    if d.get('model_status')=='UNAVAILABLE' or not model:
        errors.append('equilibrium model unavailable')
    elif not isinstance(model.get('fundamental_p_star_usd_oz'),(int,float)) or model.get('fundamental_p_star_usd_oz',0)<=0:
        errors.append('P* missing/non-positive')
    if d.get('errors'): errors.extend('pipeline: '+str(e) for e in d['errors'])
    if errors:
        print('HEALTHCHECK FAIL')
        for e in errors: print('- '+e)
        return 1
    print('HEALTHCHECK PASS')
    print(f"status={d.get('model_status')} spot={market.get('usd_oz')} pstar={model.get('fundamental_p_star_usd_oz')}")
    return 0

if __name__=='__main__': sys.exit(main())
