# Public learning site

The learning website is published at
<https://lipengyuan1994.github.io/bimanual-robotic-manipulation/>. It is a static
subset of the project, intentionally separate from the local FastAPI/React portal.
The public site contains the two lessons, their browser-only exercises, the shared
learning CSS/JavaScript, and the glossary. It contains no local run records,
operator controls, credentials, or simulator service.

## Deployment

[`pages.yml`](../.github/workflows/pages.yml) runs after a relevant change reaches
`main`, and can also be started manually from the Actions tab. It pins Node 24,
installs the lockfile with `npm ci`, type-checks the TypeScript portal, generates
the learning artifact, verifies the generated navigation, configures Pages, then
uses GitHub's official Pages artifact/deployment actions. The workflow uses the
current Node-24-compatible action releases to avoid the GitHub-hosted runner's
Node 20 deprecation path.

The Pages build copies tracked learning sources into `web/dist-learning` and
rewrites only repository-only navigation to static-site or source-repository URLs.
That generated directory is ignored and must never become the source of truth.

## Operational checks

After a deployment, open the public URL and verify lesson 01, lesson 02, glossary,
one quiz response, and the two-link slider. The deployment action exposes the exact
published URL and status. If the workflow cannot deploy, confirm that the
repository's Pages source is set to **GitHub Actions** in GitHub settings; no
alternative branch-based Pages source is used.
