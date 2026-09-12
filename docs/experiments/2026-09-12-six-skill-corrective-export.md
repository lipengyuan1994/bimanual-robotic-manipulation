# Six-skill corrective archive export

- **Date:** September 12, 2026
- **Code revision:** `4a7c0e2`
- **Input view:** `six-skill-corrective-views-v7.json`, seal `6af40e2dcea7c43541e518f447039beb3a88cf16fe872748835383d8ef86a08f`
- **Output:** `.artifacts/datasets/six-skill-corrective-all-v1`
- **Runtime:** native arm64 Python 3.12.13, LeRobot 0.6.1, offline Hugging Face mode

The local export retained seven raw sealed teacher sources and produced 4,143
image-backed transitions. Its export seal is
`588e701aa3cd8e7e6101d6c227b9a98ecd915643f5851152bc7efd6d27a00668`.
A separate offline verifier recomputed file hashes, source-view lineage, and
decoded RGB, joint, action, timestamp, and index parity. It completed
successfully. The Objective-C AVFoundation duplicate-class warning from the
local PyAV/Homebrew runtime was observed, but did not interrupt the export or
verification.

The archive is teacher evidence and is not a model-quality result. The training
path derives each policy's corrective subset from the sealed view and rejects
empty or substituted skill selections. Corrective retraining and physical
evaluation remain outstanding.
