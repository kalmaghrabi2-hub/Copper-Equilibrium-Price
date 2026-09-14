# Economic Committee → Engineering Committee Implementation Standard

## Purpose
This repository must distinguish three concepts that may never be merged by presentation or code:
1. **Market Reference** — short-horizon market estimate / persistence fallback.
2. **Cyclical Fair Value** — medium-horizon macro/financial valuation layer; not yet production-validated unless its own gate passes.
3. **Structural Equilibrium** — long-horizon physical/economic equilibrium; not production-validated until a point-in-time structural backtest passes.

## Non-negotiable publication rules
- A low MAPE or high R² is not proof of equilibrium accuracy.
- `100 - MAPE` may only be labelled **OOS Fit Score**, never probability, confidence, or equilibrium accuracy.
- Final OOS observations must not participate in model/hyperparameter selection.
- No look-ahead, no interpolation of critical missing fundamentals, and no retrospective use of revised data as if known historically.
- Any failed or unavailable layer has **zero price weight**.
- No market-relative price clipping, cosmetic guardrail, or manual override may pull a model output toward the market merely because the gap appears large.
- If the strict publication gate fails, the public state must be `REFERENCE_ONLY` and `equilibrium_claim=WITHHELD_NOT_VALIDATED`.

## Weekly hard gate
Every condition must pass simultaneously:
- non-zero model weight;
- MSE skill vs persistence >= 2.0%;
- relative MAPE improvement vs persistence >= 1.0%;
- one-sided Diebold-Mariano p-value <= 0.05;
- positive skill in at least 4 of 5 contiguous 52-week regimes;
- directional accuracy >= 52.5%;
- R² >= 0.60;
- MAPE <= 12%;
- minimum final untouched OOS = 260 weeks.

## Structural equilibrium hard gate
Structural copper may not enter the published equilibrium price until the repository has a point-in-time monthly dataset with:
- >= 36 contiguous exact monthly fundamental observations;
- source-vintage/publication-lag mapping;
- no imputed critical ICSG observations;
- expanding/rolling walk-forward validation;
- comparison against persistence and at least one economically appropriate alternative benchmark;
- stability diagnostics across regimes;
- documented cost, inventory, supply-demand, capacity/production and elasticity methodology.

Until this gate passes, the structural value is diagnostic only and must retain price weight = 0.

## Daily production sequence
1. Compile and schema-check source code.
2. Refresh raw market/public proxy inputs.
3. Recalibrate candidate model without touching final OOS selection data.
4. Run strict statistical/economic validation.
5. Generate latest output.
6. Apply publication gate and zero failed layers.
7. Run publication-contract assertions.
8. Commit generated data/site only if assertions pass.
9. GitHub Pages deploys only after the update workflow succeeds.

## Engineering rule
When economics and presentation convenience conflict, economics wins. Large price gaps are permitted. Unsupported precision is not.
