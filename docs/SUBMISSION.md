# Submission package

The local submission packager creates a versioned, self-checking directory only
after every required declaration and evidence source verifies. It performs no model
loading, rendering, upload, form submission, or external-account access.

Required inputs are a clean checkout at the exact Git `HEAD`, a verified local workflow release protocol,
its matching verified release-suite run directory, a credential-free HTTPS interactive
application URL, an MP4 video, PDF slides, and a 16:9 PNG/JPG cover. The release protocol
and suite do not exist until their upstream gates have run; absence is reported as a
missing requirement and creates no partial package.

Inspect every requirement without creating output:

```sh
.venv/bin/bimanual submission-check \
  --revision GIT_HEAD --release-protocol RELEASE.json \
  --release-suite .artifacts/runs/RELEASE_SUITE \
  --interactive-url https://example.invalid/app \
  --video demo.mp4 --slides slides.pdf --cover cover.png
```

Replace `submission-check` with `submission-create --destination PACKAGE` after the
report is complete. The destination must not already exist and should be outside the
checkout or in an ignored artifact directory so package creation does not dirty the
bound revision. Recheck it with
`.venv/bin/bimanual submission-verify PACKAGE` before upload. The equivalent Python
API exposes `SubmissionInputs`, `inspect_submission_requirements`,
`create_submission_package` and `verify_submission_package`.

The package copies the declared media and release evidence, records every file digest,
binds the current repository revision and source evidence identities, and preserves the
suite's local-prequalification, Intel-validation, and release-success values exactly.
`package_complete` means the required files are sealed together. It does not mean the
project passed local evaluation, ran on Intel hardware, achieved release success, or was
submitted to the event. `submission_status` remains `package_complete_not_submitted`.
