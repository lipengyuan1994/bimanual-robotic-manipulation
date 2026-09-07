# Project context retrieval

OpenViking is an optional local search aid. The repository remains the source of
truth. The project instructions select the collection automatically when a task
benefits from background retrieval; no separate skill or repeated collection name
is required. MCP availability alone does not require a search on every turn.

- MCP server: `openviking-local`.
- Collection: `viking://resources/bimanual-robotic-manipulation/`.
- Current indexing state: project ingestion has not been performed by this change.
- Read current status, roadmap, and preparation-boundary files directly before
  consulting indexed snapshots. Worktrees may differ from those snapshots.

## Initial indexing prompt

Copy this into a Codex task opened in this repository:

```text
Create the initial local OpenViking documentation index for this project using
the existing Docker OpenViking service and native Ollama. Use the collection
viking://resources/bimanual-robotic-manipulation/.

Index only AGENTS.md, MISSION.md, docs/STATUS.md, docs/ROADMAP.md,
docs/ARCHITECTURE.md, docs/REQUIREMENTS.md, docs/SETUP.md,
docs/TROUBLESHOOTING.md, docs/LEARNING.md, and docs/decisions/*.md.

Preserve repository-relative paths and original text. Record the indexing time
in UTC, repository root, Git HEAD, dirty flag, and SHA-256 of every source file
in a local manifest that maps source paths to indexed URIs. Stage an exact copy
and verify its digest before upload so uncommitted files are identified correctly.
Use a versioned snapshot within the collection and record the active snapshot in
docs/OPENVIKING.md only after verification. Do not overwrite an existing snapshot.

Use local model endpoints only. The MCP connection allows retrieval only: keep
that allowlist unchanged and use the existing local authenticated upload API for
this explicitly requested ingestion. Never print credentials. Import no other
files, follow no external links, and enable no watchers or conversation capture.

Use asynchronous ingestion and check each task's terminal result. Report partial
failures honestly. Verify project-scoped retrieval and reading original sources
for: the current preparation boundary; ACT/Qwen/supervisor responsibilities; and
the native setup/validation commands. Compare answers with current source files.
Report indexed files, snapshot URI, manifest location, and validation results.
```

The explicit upload authorization is in this prompt, not in ordinary retrieval.
The local service setup and verified API example are in the sibling
`openviking-local` project. Locate that project on the current host rather than
assuming it is checked into this repository.

## Normal use and refresh

Ordinary questions such as “Explain the supervisor's responsibilities” or “Find
the relevant setup decision” can trigger scoped retrieval through AGENTS.md.
For a guaranteed explicit request, say “Consult the project's indexed context,
then verify the answer against current files.”

After important documentation changes, ask: “Refresh this project's OpenViking
documentation snapshot using the existing allowlist and manifest procedure;
verify retrieval before updating the active snapshot reference.” Keep old
snapshots distinguishable and scope retrieval to the recorded active snapshot
once one exists. Never assume that the newest-looking search result is current.

Only original files and independently verified evidence establish current scope
or success. Neither summaries nor a successful index alter the preparation-only
boundary. Indexing and retrieval are documentation support, not manipulation
implementation or training.
