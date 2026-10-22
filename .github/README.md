# GitHub configuration

CI runs on pushes, pull requests, and manual dispatch. It checks the locked
Python environment, tests, and add-on packaging on Linux, Windows, and macOS
with Python 3.12 and 3.14. Ruff runs once on Linux/Python 3.12.

The Linux/Python 3.12 job uploads `kanji-katanki-addon`, containing the installable
`kanji-katanki.ankiaddon`, as a workflow artifact retained for 14 days. Download it from
the workflow run's Artifacts section and extract the outer ZIP before installing.

These checks do not launch Anki or establish host compatibility on those operating
systems. Run the isolated real-host smoke test documented in the project README
for changes affecting Anki integration.

Dependabot checks GitHub Actions monthly. Issue and pull request templates collect
reproduction details, validation, and collection impact.
