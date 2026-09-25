# Composite-feature failure identified during cache review

The current producer passes scalar `100` to `_safe_div`, which unconditionally calls `.abs()` on its numerator. There are three callers: `volume_price_divergence` (line159), `mean_reversion_extremity` (341) and `momentum_quality_score` (484). The first prevents the complete composite computation from returning. `compute_ml_features` then silently supplies zeros for all seven composite columns.

Those columns affect alpha scoring and observable direction, including the registered momentum strategy. They are also model/research feature inputs. Current ML isolation limits model influence; it does not make the observable direction inputs unused. This is a confirmed arithmetic integration defect. It does not establish how many September24 trades were lost or that a correction will be profitable.

The existing direct division test covers Series/Series zero handling, not scalar callers. Feature integration checks require columns and no NaNs, which fallback zeros satisfy. Direction tests inject feature values, while causal replay comparisons use the same producer on both sides. These are useful checks, but successful end-to-end composite production was a missing assertion.

A correction needs explicit scalar/Series safety tests, direct composite and full-feature success checks, preserved fallback/retry behavior and a source-bound before/after trading replay. It changes decision inputs and must receive the approved new forward boundary before deployment. Historical outputs retain their old source identity. No correction or runtime change was performed by this read-only review.

Exact paths, one-based source lines, source hashes and acceptance scope are recorded in `composite_feature_defect_review.json`.
