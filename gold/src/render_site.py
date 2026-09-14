#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'docs'/'gold'/'data'/'latest.json'
OUT=ROOT/'docs'/'gold'/'index.md'

def n(v,d=2):
    return '—' if v is None else f'{float(v):,.{d}f}'

def main():
    d=json.loads(DATA.read_text(encoding='utf-8'))
    m=d.get('market') or {}; x=d.get('model') or {}; f=d.get('fundamentals') or {}; macro=d.get('macro') or {}
    gap=x.get('market_vs_pstar_pct'); gap_text='—' if gap is None else f'{gap:+.2f}%'
    metrics=x.get('walk_forward_metrics') or {}
    lines=[
'---','title: Gold Equilibrium Price','---','',
'# Gold Equilibrium Price','',
'> **'+str(d.get('model_status','UNAVAILABLE'))+' · GOVERNANCE GATE ACTIVE**','',
'السعر المتعادل للذهب مقابل سعر السوق. النموذج يفصل بين **طبقة نقدية يومية** و**طبقة أساسيات عرض/طلب ربع سنوية**، ولا يملأ البيانات الحرجة المفقودة اصطناعيًا.','',
'| المؤشر | القيمة |','|---|---:|',
f"| XAU/USD Spot | **${n(m.get('usd_oz'))}/oz** |",
f"| Equilibrium P* | **${n(x.get('fundamental_p_star_usd_oz'))}/oz** |",
f"| Market vs P* | **{gap_text}** |",
f"| Macro fair value | ${n(x.get('macro_fair_value_usd_oz'))}/oz |",
f"| Physical multiplier | {n(x.get('physical_multiplier'),4)} |",'',
'## الاختبار والحوكمة','',
'| البند | الحالة |','|---|---:|',
f"| Macro walk-forward gate | **{x.get('macro_gate','—')}** |",
f"| Physical-history gate | **{x.get('physical_gate','—')}** |",
f"| Walk-forward MAPE | {n((metrics.get('mape') or 0)*100 if metrics.get('mape') is not None else None)}% |",
f"| Walk-forward R² | {n(metrics.get('r2'),3)} |",
f"| Mean bias | {n((metrics.get('mean_bias') or 0)*100 if metrics.get('mean_bias') is not None else None)}% |",
'| No-imputation | **ACTIVE** |','',
'## آخر أساسيات World Gold Council','',
'| المؤشر | القيمة |','|---|---:|',
f"| Period | {f.get('quarter','—')} |",
f"| Mine production | {n(f.get('mine_production_t'))} t |",
f"| Recycled gold | {n(f.get('recycled_gold_t'))} t |",
f"| Bar & coin | {n(f.get('bar_coin_t'))} t |",
f"| ETFs | {n(f.get('etf_t'))} t |",
f"| Central banks | {n(f.get('central_banks_t'))} t |",'',
'## العوامل النقدية','',
'| المؤشر | القيمة |','|---|---:|',
f"| 10Y real yield (DFII10) | {n((macro.get('DFII10') or {}).get('value'))}% |",
f"| Broad USD (DTWEXBGS) | {n((macro.get('DTWEXBGS') or {}).get('value'))} |",
f"| 10Y breakeven (T10YIE) | {n((macro.get('T10YIE') or {}).get('value'))}% |",
f"| VIX | {n((macro.get('VIXCLS') or {}).get('value'))} |",'',
'## منهجية السعر المتعادل','',
'إجمالي الطلب وإجمالي العرض في سوق الذهب يتساويان محاسبيًا تقريبًا، لذلك لا يستخدم النموذج نسبة `Total Demand / Total Supply` كإشارة. السعر المتعادل يجمع بين fair value نقدي مُعاير تاريخيًا وبين ضغط مكونات الطلب الاستراتيجي (البنوك المركزية، السبائك والعملات، ETF والتكنولوجيا) مقابل العرض الأولي والمعاد تدويره.','',
'حالة **VALID** لا تُمنح إلا عند نجاح بوابتين مستقلتين: اختبار Walk‑Forward للنموذج النقدي، واكتمال/اعتماد السلسلة التاريخية الفيزيائية. وإلا تبقى النتيجة **PROVISIONAL**.','',
'## المصادر','',
'- World Gold Council — Gold Demand Trends / Historical demand & supply','- FRED — DFII10, DTWEXBGS, T10YIE, VIXCLS','- Stooq — XAUUSD historical calibration series','- XAUS / Gold API — indicative current market layer','',
f"آخر تحديث آلي: `{d.get('generated_at_utc','—')}`",'',
'> للاستخدام التحليلي وليس توصية استثمارية.'
    ]
    OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__': main()
