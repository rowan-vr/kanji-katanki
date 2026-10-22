# GitHub configuration

CI runs on pushes, pull requests, and manual dispatch. It checks the locked
Python environment, tests, and add-on packaging on Linux, Windows, and macOS
with Python 3.12 and 3.14. Ruff runs once on Linux/Python 3.12.

The Linux/Python 3.12 job uploads `kanji-katanki-addon`, containing the installable
`kanji-katanki.ankiaddon`, as a workflow artifact retained for 14 days. Download it from
the workflow run's Artifacts section and extract the outer ZIP before installing.

Builds fetch checksum-locked upstream inputs when absent from the local cache and
prepare KANJIDIC2/KanjiVG defaults plus required notices/licenses. Payloads are not
committed to Git. Both workflows build before tests so data-dependent tests run.
Normal builds never update source locks; maintainers use an explicit refresh and
review metadata changes before a release.
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

Dependabot checks GitHub Actions monthly. Issue and pull request templates collect
reproduction details, validation, and collection impact.
