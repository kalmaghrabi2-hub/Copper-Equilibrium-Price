# Equilibrium Prices — Hard Model Governance Standard

## Purpose separation
1. A one-week statistical forecast is a near-term market reference, not proof of structural equilibrium.
2. Structural equilibrium must be validated independently at the frequency of its economic inputs.
3. Physical/fundamental overlays have zero price weight until their own price-level OOS test passes.

## Non-bypass production gates
A weekly candidate may receive VALIDATED status only if ALL conditions pass on an untouched final 260-week OOS window:
- non-zero model weight selected before the final OOS window;
- MSE skill versus persistence >= 2.0%;
- relative MAPE improvement versus persistence >= 1.0%;
- one-sided Diebold-Mariano test p <= 0.05 using HAC/Newey-West lag 4;
- positive skill in at least 4 of 5 contiguous OOS sub-windows;
- directional accuracy >= 52.5%;
- basic sanity gate: R2 >= 0.60 and MAPE <= 12%.

Failing any condition means REFERENCE_ONLY. The system must fail closed and may not relax thresholds to preserve publication.

## Prohibited practices
- No tuning on the final OOS period.
- No arbitrary clipping/capping of model prices to make them closer to market.
- No labeling 100-MAPE as a probability or as equilibrium accuracy; it is a descriptive OOS fit score only.
- No interpolation or imputation of critical production inputs unless a separately approved method is validated.
- No application of a failed or unvalidated economic overlay.
- No hiding large market/model gaps. A validated model may disagree materially with market.

## Change control
Thresholds, benchmarks, data vintages, predictor definitions, roll methodology, and model objectives are controlled parameters. Any change requires documented rationale and must be evaluated without using the final OOS period for selection.

## Required next institutional upgrades
Use primary/official market and macro sources where available; implement point-in-time data vintages; validate continuous-futures roll methodology; add at least one benchmark beyond persistence; add structural-break and coefficient-stability tests; maintain explicit data-freshness and source-redundancy gates; and validate structural equilibrium separately at monthly/quarterly horizons.
