#!/usr/bin/env python3
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
DATA=ROOT/'docs'/'gold'/'data'/'latest.json'
OUT=ROOT/'docs'/'gold'/'index.md'

def n(v,d=2):
    return '—' if v is None else f'{float(v):,.{d}f}'

def pct(v,d=2):
    return '—' if v is None else f'{float(v)*100:.{d}f}%'

def main():
    d=json.loads(DATA.read_text(encoding='utf-8'))
    m=d.get('market') or {}; x=d.get('model') or {}; f=d.get('fundamentals') or {}; macro=d.get('macro') or {}
    gap=x.get('market_vs_pstar_pct'); gap_text='—' if gap is None else f'{gap:+.2f}%'
    metrics=x.get('walk_forward_metrics') or {}
    lines=[
'---','title: Gold Equilibrium Price','---','',
'# Gold Equilibrium Price','',
'> **'+str(d.get('model_status','UNAVAILABLE'))+' · GOVERNANCE GATE ACTIVE**','',
'السعر المتعادل للذهب مقابل سعر السوق. النموذج يفصل بين **طبقة نقدية مُعايرة تاريخيًا** و**طبقة أساسيات عرض/طلب ربع سنوية**، ولا يملأ البيانات الحرجة المفقودة اصطناعيًا.','',
'| المؤشر | القيمة |','|---|---:|',
f"| XAU/USD Spot | **${n(m.get('usd_oz'))}/oz** |",
f"| Equilibrium P* | **${n(x.get('fundamental_p_star_usd_oz'))}/oz** |",
f"| Market vs P* | **{gap_text}** |",
f"| Macro fair value | ${n(x.get('macro_fair_value_usd_oz'))}/oz |",
f"| Macro predicted return | {n(x.get('macro_predicted_return_pct'),3)}% |",
f"| Physical multiplier | {n(x.get('physical_multiplier'),4)} |",
f"| Outlier flag | **{'YES' if x.get('outlier_flag') else 'NO'}** |",'',
'## الاختبار والحوكمة','',
'| البند | الحالة |','|---|---:|',
f"| Macro walk-forward gate | **{x.get('macro_gate','—')}** |",
f"| Physical-history gate | **{x.get('physical_gate','—')}** |",
f"| Walk-forward MAPE | {pct(metrics.get('mape'))} |",
f"| Naive baseline MAPE | {pct(metrics.get('naive_mape'))} |",
f"| Improvement vs naive | {n(metrics.get('improvement_vs_naive_pct'))}% |",
f"| Return R² | {n(metrics.get('return_r2'),3)} |",
f"| Price R² | {n(metrics.get('price_r2'),3)} |",
f"| Directional accuracy | {pct(metrics.get('directional_accuracy'))} |",
f"| Mean bias | {pct(metrics.get('mean_bias'))} |",
'| No-imputation | **ACTIVE** |','| Market-price clipping | **DISABLED** |','',
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
'النموذج النقدي لا يفسر مستوى السعر مباشرة؛ بل يقدّر **التغير الشهري العادل** انطلاقًا من تغير العائد الحقيقي، قوة الدولار، توقعات التضخم، التقلب وزخم الذهب، ثم يختبر نفسه زمنيًا مقابل baseline بسيط هو سعر الشهر السابق. بعد ذلك تُطبق طبقة ضغط العرض/الطلب من World Gold Council.','',
'إجمالي الطلب وإجمالي العرض في سوق الذهب يتساويان محاسبيًا تقريبًا، لذلك لا نستخدم `Total Demand / Total Supply` كإشارة سعرية. كما لا يتم قص P* ليقترب من سعر السوق؛ إذا خرجت النتيجة بعيدًا تُرفع علامة Outlier بدل تعديلها قسرًا.','',
'حالة **VALID** لا تُمنح إلا عند نجاح بوابتين مستقلتين: اختبار Walk‑Forward للنموذج النقدي، واعتماد السلسلة التاريخية الفيزيائية. وإلا تبقى النتيجة **PROVISIONAL**.','',
'## المصادر','',
'- World Gold Council — Gold Demand Trends / Historical demand & supply','- FRED — DFII10, DTWEXBGS, T10YIE, VIXCLS','- Public-domain GOLD history repository + XAUS recent history — historical calibration','- XAUS / Gold API — indicative current market layer','',
f"آخر تحديث آلي: `{d.get('generated_at_utc','—')}`",'',
'> للاستخدام التحليلي وليس توصية استثمارية.'
    ]
    OUT.write_text('\n'.join(lines)+'\n',encoding='utf-8')

if __name__=='__main__': main()
