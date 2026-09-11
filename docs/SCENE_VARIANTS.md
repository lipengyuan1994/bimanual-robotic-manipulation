# Frozen dinner-scene perturbations

The robustness suite now has a deterministic generator and a write-once seed
allocation for all six required families. This is evaluation infrastructure;
no perturbed learned workflow has run yet.

| Family | Bounded change |
|---|---|
| Placement | Object XY offsets: up to 6 mm for the bar, cup and plate; 1.5 mm for each drawer utensil |
| Mass | Independent per-object scale from 0.85 to 1.15 |
| Friction | Independent scale from 0.8 to 1.2 on explicit sliding-friction coefficients |
| Shape | Independent horizontal geometry scale from 0.94 to 1.06; vertical dimensions stay fixed |
| Lighting | World-light diffuse and ambient intensity within declared ranges |
| Background | Floor and workbench RGB colors within declared ranges |

`src/bimanual/scene_variants.py` changes the MuJoCo XML before model loading.
Each output report contains the source and result hashes, sampled parameters and
every XML attribute changed. It never changes actions, labels, controller code or
object state during an episode. Generated XML must compile with the actual SO-101
assets before it can be sealed as a prepared scene.

The frozen protocol is
[`experiments/dinner-perturbation-protocol-v1.json`](experiments/dinner-perturbation-protocol-v1.json),
seal `3aba583eecc9ba96d6e703d61fcf58d236fdafcd907c45ba01b3bab36446cff7`.
Seed `29001` is reserved for the six one-factor diagnostics. Seeds `30001` through
`30010` are the ten combined test cases; every combined case applies all six
families. The diagnostic seed cannot count as a held-out combined result. The
allocation binds the nominal scene, layout, plan, asset manifest and generator
source before any generated scene is evaluated.

Verify the allocation and prepare a scene with:

```sh
.venv/bin/bimanual scene-variant-protocol-check \
  docs/experiments/dinner-perturbation-protocol-v1.json
.venv/bin/bimanual scene-variant-prepare \
  docs/experiments/dinner-perturbation-protocol-v1.json \
  --family combined --seed 30001
```

`scene-variant-prepare` only seals a compilable XML bundle. Its outcome is
`prepared`, `evaluation_attempted=false`, and `task_success=null`. Later workflow
evaluation must consume these exact bundles, retain every attempt and report
learned task outcomes separately. We will run the one-factor diagnostics first
to classify failures, then all ten combined seeds without replacing difficult
cases.
