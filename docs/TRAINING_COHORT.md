# Remaining dinner-skill training cohort

The frozen cohort protocol is
[`experiments/six-skill-training-protocol-v1.json`](experiments/six-skill-training-protocol-v1.json).
It covers, in order: bar placement/return, cup placement, plate placement, drawer
opening, spoon retrieval, and fork retrieval. Each uses the verified nominal-v2
skill view, small ACT, horizon10, batch4, seed0,20,000 native-MPS updates, terminal
learning-rate decay, and the final checkpoint only.

The protocol binds the completed hand-off training and all three evaluations that
were frozen before it: the630-frame recorded-input run and physical prefix2/prefix5.
Both physical runs failed and remain recorded as failures. They authorize no
quality claim; the remaining skill datasets are independent bounded intervals.

Reverify the protocol before starting or resuming any skill:

```sh
.venv/bin/bimanual training-cohort-check \
  docs/experiments/six-skill-training-protocol-v1.json
```

Run exactly one skill from the native training environment:

```sh
PYTORCH_ENABLE_MPS_FALLBACK=0 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
  .artifacts/training-venv/bin/bimanual training-cohort-run \
  docs/experiments/six-skill-training-protocol-v1.json \
  --skill bar_place_and_return
```

The runner holds one coordinator lease and the shared model-job lease across
allocation, training, checkpoint verification, and wrapper sealing. Each attempt
uses a child evidence store. A completed verified attempt is reused on resume. A
sealed failure is never retried automatically. If the coordinator dies after the
child seals, the next invocation reconciles that exact child; an incomplete child
is preserved and sealed failed only after the shared lease proves no model job is
still active. Ambiguous attempts stop without selecting one.

Training completion requires all20,000 ordered updates, the checkpoint schedule,
all processor/sampler/loss/schedule reload flags, and a reconstructed skill binding.
It does not establish physical manipulation, generalization, or release readiness.
