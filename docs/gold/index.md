---
title: Gold Equilibrium Price
---

# Gold Equilibrium Price

> **PROVISIONAL · GOVERNANCE GATE ACTIVE**

السعر المتعادل للذهب مقابل سعر السوق. النموذج يفصل بين **طبقة نقدية يومية** و**طبقة أساسيات عرض/طلب ربع سنوية**، ولا يملأ البيانات الحرجة المفقودة اصطناعيًا.

| المؤشر | القيمة |
|---|---:|
| XAU/USD Spot | **$4,310.40/oz** |
| Equilibrium P* | **$2,370.72/oz** |
| Market vs P* | **+81.82%** |
| Macro fair value | $2,050.22/oz |
| Physical multiplier | 1.0000 |

## الاختبار والحوكمة

| البند | الحالة |
|---|---:|
| Macro walk-forward gate | **FAIL** |
| Physical-history gate | **PROVISIONAL_5Q_NORMALIZATION** |
| Walk-forward MAPE | 23.64% |
| Walk-forward R² | -0.291 |
| Mean bias | -23.64% |
| No-imputation | **ACTIVE** |

## آخر أساسيات World Gold Council

| المؤشر | القيمة |
|---|---:|
| Period | 2026-Q2 |
| Mine production | 965.60 t |
| Recycled gold | 326.10 t |
| Bar & coin | 307.10 t |
| ETFs | -44.80 t |
| Central banks | 288.90 t |

## العوامل النقدية

| المؤشر | القيمة |
|---|---:|
| 10Y real yield (DFII10) | 2.55% |
| Broad USD (DTWEXBGS) | 118.07 |
| 10Y breakeven (T10YIE) | 2.36% |
| VIX | 17.84 |

## منهجية السعر المتعادل

إجمالي الطلب وإجمالي العرض في سوق الذهب يتساويان محاسبيًا تقريبًا، لذلك لا يستخدم النموذج نسبة `Total Demand / Total Supply` كإشارة. السعر المتعادل يجمع بين fair value نقدي مُعاير تاريخيًا وبين ضغط مكونات الطلب الاستراتيجي (البنوك المركزية، السبائك والعملات، ETF والتكنولوجيا) مقابل العرض الأولي والمعاد تدويره.

حالة **VALID** لا تُمنح إلا عند نجاح بوابتين مستقلتين: اختبار Walk‑Forward للنموذج النقدي، واكتمال/اعتماد السلسلة التاريخية الفيزيائية. وإلا تبقى النتيجة **PROVISIONAL**.

## المصادر

- World Gold Council — Gold Demand Trends / Historical demand & supply
- FRED — DFII10, DTWEXBGS, T10YIE, VIXCLS
- Stooq — XAUUSD historical calibration series
- XAUS / Gold API — indicative current market layer

آخر تحديث آلي: `2026-09-14T09:09:51.128886+00:00`

> للاستخدام التحليلي وليس توصية استثمارية.
