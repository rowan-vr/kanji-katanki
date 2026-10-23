# GitHub configuration

The `CodeQL` workflow analyzes Python with the `security-extended` query suite on
pushes to `main`, pull requests targeting `main`, Tuesdays at 04:23 UTC, and manual
dispatch. It analyzes source without building the add-on or downloading datasets.
Results appear under **Security > Code scanning** and on pull requests. The workflow
uses the automatic `GITHUB_TOKEN`; no extra secret is required. It starts running
once the workflow is pushed to GitHub; scheduled runs require it on `main`.
Keep CodeQL default setup disabled because this workflow uses advanced setup.

CI runs on pushes, pull requests, and manual dispatch. It checks the locked
Python environment, tests, and add-on packaging on Linux, Windows, and macOS
with Python 3.12 and 3.14. Ruff runs once on Linux/Python 3.12.

Each CI job measures line and branch coverage for the add-on and maintenance
scripts and uploads HTML and XML reports as `coverage-<os>-python-<version>`
artifacts retained for 14 days. Coverage is reported without a minimum threshold.

The Linux/Python 3.12 job uploads `kanji-katanki-addon`, containing the installable
`kanji-katanki.ankiaddon`, as a workflow artifact retained for 14 days. Download it from
the workflow run's Artifacts section and extract the outer ZIP before installing.

Builds fetch exact dictionary packs selected by `datasets/bundled-lock.json` from
this repository's dataset Releases, verify them, and bundle offline defaults.
Dataset payloads stay out of Git. Both workflows build before tests; they never
fetch mutable upstream data or refresh source locks. Dataset release tags are
excluded from the add-on release job.

The separate `Dataset packs` workflow prepares monthly candidate artifacts. Manual
runs can publish validated assets; catalog promotion is reviewed separately.
The initial `datasets-2026-10-23` prerelease is published and supplies cold CI builds.
See [dataset maintenance](../docs/DATASETS.md#maintainer-preparation-and-regular-updates).

These checks do not launch Anki or establish host compatibility on those operating
systems. Run the isolated real-host smoke test documented in the project README
for changes affecting Anki integration.

The Release workflow runs when a GitHub release or prerelease is published, including
one published from a draft. It checks out the release's tagged commit, runs Ruff and
tests on Linux/Python 3.12, builds the add-on, and uploads
`kanji-katanki.ankiaddon` directly to that release's Assets section. Drafts do not
trigger a build. The workflow uses the automatic `GITHUB_TOKEN`; no extra secret
is required. Include this workflow in the tagged commit before publishing a release.
An existing asset with the same name is not overwritten; remove it before rerunning
the upload if a replacement is needed.

Dependabot checks Python dependencies in `pyproject.toml` and `uv.lock` weekly using
the `uv` ecosystem, and GitHub Actions monthly. Each ecosystem allows up to five
open version-update pull requests. Updates require review and are not auto-merged.
Issue and pull request templates collect
reproduction details, validation, and collection impact.
