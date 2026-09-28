---
title: Gold Equilibrium Price
---

# Gold Equilibrium Price

> **PROVISIONAL · GOVERNANCE GATE ACTIVE**

السعر المتعادل للذهب مقابل سعر السوق. النموذج يفصل بين **طبقة نقدية مُعايرة تاريخيًا** و**طبقة أساسيات عرض/طلب ربع سنوية**، ولا يملأ البيانات الحرجة المفقودة اصطناعيًا.

| المؤشر | القيمة |
|---|---:|
| XAU/USD Spot | **$4,307.10/oz** |
| Equilibrium P* | **$4,531.64/oz** |
| Market vs P* | **-4.95%** |
| Macro fair value | $4,531.64/oz |
| Macro predicted return | 2.662% |
| Physical multiplier | 1.0000 |
| Outlier flag | **NO** |

## الاختبار والحوكمة

| البند | الحالة |
|---|---:|
| Macro walk-forward gate | **PASS** |
| Physical-history gate | **PROVISIONAL_5Q_NORMALIZATION** |
| Walk-forward MAPE | 2.37% |
| Naive baseline MAPE | 2.94% |
| Improvement vs naive | 19.47% |
| Return R² | 0.266 |
| Price R² | 0.991 |
| Directional accuracy | 77.17% |
| Mean bias | -0.92% |
| No-imputation | **ACTIVE** |
| Market-price clipping | **DISABLED** |

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

النموذج النقدي لا يفسر مستوى السعر مباشرة؛ بل يقدّر **التغير الشهري العادل** انطلاقًا من تغير العائد الحقيقي، قوة الدولار، توقعات التضخم، التقلب وزخم الذهب، ثم يختبر نفسه زمنيًا مقابل baseline بسيط هو سعر الشهر السابق. بعد ذلك تُطبق طبقة ضغط العرض/الطلب من World Gold Council.

إجمالي الطلب وإجمالي العرض في سوق الذهب يتساويان محاسبيًا تقريبًا، لذلك لا نستخدم `Total Demand / Total Supply` كإشارة سعرية. كما لا يتم قص P* ليقترب من سعر السوق؛ إذا خرجت النتيجة بعيدًا تُرفع علامة Outlier بدل تعديلها قسرًا.

حالة **VALID** لا تُمنح إلا عند نجاح بوابتين مستقلتين: اختبار Walk‑Forward للنموذج النقدي، واعتماد السلسلة التاريخية الفيزيائية. وإلا تبقى النتيجة **PROVISIONAL**.

## المصادر

- World Gold Council — Gold Demand Trends / Historical demand & supply
- FRED — DFII10, DTWEXBGS, T10YIE, VIXCLS
- Public-domain GOLD history repository + XAUS recent history — historical calibration
- XAUS / Gold API — indicative current market layer

آخر تحديث آلي: `2026-09-14T09:14:31.206544+00:00`

> للاستخدام التحليلي وليس توصية استثمارية.
