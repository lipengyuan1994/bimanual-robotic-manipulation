# Troubleshooting

| Symptom | Check / action |
|---|---|
| Python reports x86_64 on this Mac | Stop using that environment; select the verified aarch64 path with the bootstrap. Do not reuse ambient `python3`. |
| `uv sync --frozen` reports stale lock | Inspect dependency changes; regenerate deliberately on native Python, review the diff, then repeat checks. |
| MPS is unavailable | Inspect `doctor` output; use the explicit CPU profile for preparation and record the limitation. |
| MPS arithmetic fails | Preserve the failed probe and use CPU; do not claim a model works on MPS. |
| Blank or failed render | Inspect `lab` failure evidence and run the render test; offscreen OpenGL is separate from MPS. |
| Native viewer fails on macOS | Use `.venv/bin/mjpython`, as described in setup. |
| Portal returns 503 | Build `web` with native Node using `npm ci` and `npm run build`, then restart `serve`. |
| Port already in use | Select another port; do not terminate unrelated processes. |
| Run integrity failed | Preserve original files and inspect digests; never reseal changed files as the original run. |
| A process died mid-run | Inspect the unsealed run directory; do not count it as successful. |
| ACT/VLM runtime unavailable | Follow [skill training](SKILL_TRAINING.md) and [planner setup](PLANNER_LIVE_INTEGRATION.md); the base environment does not include every ML dependency or model. Runtime availability does not establish learned task success. |
| `A workflow worker still holds this lease` | A supported worker or guardian still owns the evidence store. Allow bounded cleanup to finish; do not delete `.workflow-worker.lock` or launch against a different store to bypass ownership. Inspect the run's guardian journal and terminal record. |
| `cleanup unconfirmed` or `group ownership unconfirmed` | Preserve the unsealed parent directory and partial child evidence. Do not infer success from a child completion message or signal an old numeric PID. Investigate the recorded guardian state before restarting. |
| `Guardian PID pin requires validated Python 3.12` | Use the verified Python3.12 project runtime. Guardian process ownership relies on that validated multiprocessing implementation. |
| Intel result missing | A Mac runtime check cannot substitute for the required Intel machine. |

Capture command, versions, run ID and error in an [experiment record](experiments/TEMPLATE.md).

After an application crash, `guardian/terminal.json` can certify that the supported
worker was reaped. It cannot certify dinner-task success or replace the missing
parent manifest. Retain the entire interrupted run; the next supported workflow
must acquire the same evidence store's lease normally. Guardian handling covers
one worker with threads on POSIX, not independent subprocess trees or OS failure.
See [execution ownership](WORKFLOW_EXECUTION.md) for the evidence boundaries.
