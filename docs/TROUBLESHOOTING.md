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
| No ACT/VLM commands | They are pending M2, not hidden behind another runtime option. |
| Intel result missing | A Mac runtime check cannot substitute for the required Intel machine. |

Capture command, versions, run ID and error in an [experiment record](experiments/TEMPLATE.md).
