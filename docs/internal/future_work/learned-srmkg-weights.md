# Learned SR-MKG Weights 🟢

> **Roadmap slot:** 0.4.x — Geometric memory
> **Owner:** unassigned
> **Status:** Immediate win — turns a heuristic into a calibrated classifier

## Why it matters

The SR-MKG topological scorer in
[`hydramem/verification/srmkg.py`](../../../hydramem/verification/srmkg.py) uses
hardcoded weights:

```
score = 0.4 * base + 0.4 * jaccard + 0.05 * type_boost − 0.3 * isolated
```

These are sensible defaults, but every deployment has a different
relation-type distribution and graph density. Each instance of HydraMem
has a *natural training signal* hiding in plain sight: the historical
log of `(score_components → final_decision)` pairs produced when VoG
overrules the borderline range, plus any human verifications via
`verify_relation_tool`. Fitting a small logistic regression on those
pairs turns SR-MKG into a real **per-deployment calibrated classifier**
without losing interpretability.

## State of the art

- **Platt scaling** (Platt, 1999) — logistic calibration of classifier
  scores
- **Isotonic regression** (Niculescu-Mizil & Caruana, 2005)
- **Learning-to-rank** (LambdaMART, etc.) — heavier alternative
- **Monotonic GBMs** — preserve monotonicity constraints if needed

For HydraMem, plain logistic with L2 + monotonicity priors is the right
tool: cheap, interpretable, debuggable.

## Proposed architecture

1. **Log score components.** Add a `srmkg_decisions` table:

   ```sql
   CREATE TABLE srmkg_decisions (
     id            INTEGER PRIMARY KEY,
     ts            TEXT,
     project       TEXT,
     base          REAL,
     jaccard       REAL,
     type_boost    REAL,
     isolated      REAL,
     final_label   INTEGER,   -- 1=accepted (after VoG/human), 0=rejected
     source        TEXT       -- 'vog' | 'manual' | 'inferred'
   );
   ```

2. **CLI command** `hydramem calibrate-srmkg --project X`:
   - Loads decisions for the project.
   - Requires `N >= 200` decisions, else aborts with a clear message.
   - Trains `sklearn.linear_model.LogisticRegression(penalty='l2', C=1.0)`.
   - Writes `~/.hydramem/projects/<p>/srmkg_weights.json`:

     ```json
     {
       "weights": {"base": 0.41, "jaccard": 0.38, "type_boost": 0.07, "isolated": -0.27},
       "intercept": -0.05,
       "n_train": 412,
       "auc": 0.83,
       "trained_at": "2026-05-08T10:00:00Z"
     }
     ```

3. **SRMKGScorer** loads project weights at init; falls back to defaults
   when absent. Always exposes both raw score components and final score
   for auditability.

## Risks

- **Bias inheritance**: if VoG was wrong, the calibration learns wrong.
  Mitigation: include a small validation slice from human-verified
  relations only, and refuse to ship weights with AUC below baseline.
- **Distribution shift** as the corpus grows. Mitigation: re-calibrate
  on a schedule and version weights.
- **Over-fitting to a tiny project**. Mitigation: hard floor of N=200,
  L2 regularisation, leakage check (no triple in both train and test).

## Computational cost

Trivial. < 1 second to train, < 1 ms to score with new weights.

## Privacy implications

None — purely local. Weights file is local-only and never exported.

## Local-first viability

Excellent. `scikit-learn` is already a transitive dependency.

## Suggested implementation strategy

1. Extend telemetry storage with the `srmkg_decisions` table.
2. Wire SR-MKG and VoG to log component values + final outcome.
3. Add `hydramem calibrate-srmkg` CLI subcommand.
4. Modify `SRMKGScorer.__init__` to optionally accept a project name and
   load project-specific weights.
5. Telemetry: expose `calibrated: true/false` and `auc` in
   `hydramem stats`.
6. Document workflow in `docs/verification.md`.

## Concrete code changes

| File | Change |
|------|--------|
| [`hydramem/verification/srmkg.py`](../../../hydramem/verification/srmkg.py) | Optional weights loader, project-aware |
| [`hydramem/verification/pipeline.py`](../../../hydramem/verification/pipeline.py) | Log components on every decision |
| [`hydramem/telemetry/storage.py`](../../../hydramem/telemetry/storage.py) | New `srmkg_decisions` table + DAO |
| [`hydramem/cli.py`](../../../hydramem/cli.py) | `calibrate-srmkg` subcommand |
| `hydramem/verification/calibration.py` | **NEW** — training routine |
| [`docs/verification.md`](../../verification.md) | Document calibration workflow |
| `tests/test_verify.py` | Test loaded weights override defaults |

## References

- Platt, *Probabilistic Outputs for Support Vector Machines*, 1999
- Niculescu-Mizil & Caruana, *Predicting Good Probabilities With
  Supervised Learning*, ICML 2005
- Burges, *From RankNet to LambdaRank to LambdaMART: An Overview*, 2010
