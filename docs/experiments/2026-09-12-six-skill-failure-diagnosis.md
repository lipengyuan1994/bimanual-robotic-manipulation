# Six-skill learned physical failure diagnosis

Date: September 12, 2026  
Status: completed, read-only diagnosis; no checkpoint is promoted

This record reproduces the frozen v2 component-suite failures without executing a
policy or changing data, checkpoints, scenes, or outcome records. The source suite
is `20260912T081226-097d224c93cd` (manifest
`8b93c3543edb15278afbabe4b3dab0acfd8dbf38f08fe7acf3a89f8ea5005488`). The
diagnosis is sealed as `20260912T082839-aeac50b451ba` (manifest
`2eb10f4ccf30455950a8282f5ad2677c2331423a34f7f9eb96e74c5a12b15c97`).

Every component policy loaded on actual local `mps:0`. This is local Apple Silicon
evidence only; it does not satisfy the Intel/OpenVINO requirement.

| Skill | Verified physical signal | Finding | Correction boundary to define before training |
|---|---|---|---|
| Bar | 52 confirmed actions, then a 48-sample rejected 53rd action | The left arm contacts the practice bar during learned motion. The evaluation summary says zero actions because the exception occurred before it could update that field; the append-only action log records the 52 confirmed actions. | Inspect the action-53 trajectory; retain the contact guard. |
| Cup | 1,038 actions; zero target-contact samples | The cup stayed at its start pose. | Target approach and contact acquisition. |
| Plate | 1,964 actions; zero target-contact samples | The plate stayed at its start pose. | Target approach and contact acquisition. |
| Drawer | 1,120 actions; 33,985 handle-contact samples; 10.74 mm maximum opening | Contact is sustained but cannot produce the required 80 mm opening. | Sustained handle pull and opening displacement. |
| Spoon | 1,408 actions; 53,616 contact samples; 4.63 mm maximum displacement | Contact occurs but no stable grasp/lift follows. | Gripper closure and lift after contact. |
| Fork | 1,408 actions; zero target-contact samples | The fork stayed at its start pose. | Target approach and contact acquisition. |

The immediate next work is to freeze distinct corrective collection/training
protocols for these three failure families and only then collect new teacher data.
The v2 results remain immutable and are not replaced. Intel setup and OpenVINO
conversion remain deferred until this local correction and retraining work is
complete, as requested.
