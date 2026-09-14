---
title: Gold Equilibrium Price
---

# Gold Equilibrium Price

> **UNAVAILABLE · GOVERNANCE GATE ACTIVE**

السعر المتعادل للذهب مقابل سعر السوق. النموذج يفصل بين **طبقة نقدية يومية** و**طبقة أساسيات عرض/طلب ربع سنوية**، ولا يملأ البيانات الحرجة المفقودة اصطناعيًا.

| المؤشر | القيمة |
|---|---:|
| XAU/USD Spot | **$4,309.80/oz** |
| Equilibrium P* | **$—/oz** |
| Market vs P* | **—** |
| Macro fair value | $—/oz |
| Physical multiplier | — |

## الاختبار والحوكمة

| البند | الحالة |
|---|---:|
| Macro walk-forward gate | **—** |
| Physical-history gate | **—** |
| Walk-forward MAPE | —% |
| Walk-forward R² | — |
| Mean bias | —% |
| No-imputation | **ACTIVE** |

## آخر أساسيات World Gold Council

| المؤشر | القيمة |
|---|---:|
| Period | — |
| Mine production | — t |
| Recycled gold | — t |
| Bar & coin | — t |
| ETFs | — t |
| Central banks | — t |

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

آخر تحديث آلي: `2026-09-14T09:09:13.730145+00:00`

> للاستخدام التحليلي وليس توصية استثمارية.
