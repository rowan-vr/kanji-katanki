# Unofficial modern JLPT coverage

Settings → Statistics → Lists includes **JLPT N5–N1 (unofficial, OpenJLPT)**.
The Statistics dashboard shows separate per-level known (young + mature) coverage
bars and mature counts for recognition and writing. Select one level to see its
state distribution, missing cards and kanji grid. Ctrl/Cmd-select several levels
for a cumulative unique union; groups are exclusive, not cumulative by themselves.
Changing evidence mode never uses recognition as proof of writing.

## Source decision and validation

The [official JLPT FAQ](https://www.jlpt.jp/e/faq/) explains that current test
content specifications containing vocabulary, kanji and grammar lists are not
published. These are study targets, not an official syllabus or a guarantee of
exam readiness.

Reviewed candidates on 2026-10-25:

| Candidate | Provenance/license | Decision |
| --- | --- | --- |
| KANJIDIC2 `jlpt` | EDRDG, CC BY-SA 4.0; pre-2010 four-level system | Reject for modern N5–N1; cannot infer N2/N3 |
| [davidluzgouveia/kanji-data](https://github.com/davidluzgouveia/kanji-data) | Repository MIT license; mixes KANJIDIC, Waller levels and WaniKani material | Do not bundle the mixed dataset under an assumed MIT data license |
| [bagustris/kanji-data](https://github.com/bagustris/kanji-data) | Aggregates several sources; no repository-wide license declared at review | Do not select without further source-specific validation |
| [OpenJLPT](https://github.com/evanclan/OpenJLPT) | Explicit CC BY-SA 4.0 dataset license and per-source attribution; modern levels from Jonathan Waller | Select a pinned revision; extract character identities and assigned levels only |

Selected OpenJLPT revision:
`0d1d3410bec90bd4098a7c72de820543cb4f707c`.
Its [NOTICE](https://github.com/evanclan/OpenJLPT/blob/0d1d3410bec90bd4098a7c72de820543cb4f707c/NOTICE.md)
attributes modern level assignments to Jonathan Waller's community lists and
explains that the legacy KANJIDIC field is deliberately not used. Its explicit
CC BY-SA 4.0 redistribution terms cover our extracted adaptation. The bundled
pack retains OpenJLPT's full LICENSE and NOTICE, its source hashes and upstream
credits to Waller and EDRDG. We do not extract WaniKani content.

| Group | Unique kanji |
| --- | ---: |
| N5 | 84 |
| N4 | 169 |
| N3 | 387 |
| N2 | 398 |
| N1 | 1,345 |
| Union | 2,383 |

Validation checks every member against the shared exact Unicode policy, rejects
wrong-level rows and duplicates within or across levels, and pins the original
five JSON files with SHA-256 and their repository commit. Group order is N5 → N1;
member order follows each pinned file. No character normalization or dictionary
intersection changes targets. This includes supplementary Han characters such as
`𠮟`. Version and provenance remain visible in Settings source details; every list
and group title explicitly says unofficial.

Characters not assigned by this source remain outside this list. Existing owned
cards can still appear in **All kanji with cards**. An omitted character is not
classified automatically, and omission does not mean the JLPT cannot test it.
Dictionary/stroke gaps remain in target denominators and show missing data
separately. Source updates are independent of dictionary updates and require a
new explicitly reviewed list release.

## Reproducible maintenance

`datasets/sources/jlpt-openjlpt.json` records immutable raw URLs, SHA-256 and byte
counts. Fetching is an explicit maintainer action; runtime statistics never need
network access:

```bash
uv run python scripts/generate_jlpt_targets.py --fetch --version 2026-10-25 --bundle
```

The generator produces canonical JSON in ignored `dist/targets/` and the ignored
bundle directory, plus the manifest and a local candidate lock. Normal builds use
the reviewed pack entry in `datasets/bundled-lock.json`, not live upstream files.
Custom `--output` paths must name a `.json` file inside the repository's
`dist/targets/` directory; traversal and symlinks resolving outside it are rejected.
The source record's checksum in canonical provenance is the SHA-256 of the source
lock JSON, whose resources independently pin all five original level files.

The published data-only pack is
[`datasets-jlpt-2026-10-25`](https://github.com/rowan-vr/kanji-katanki/releases/tag/datasets-jlpt-2026-10-25).
Catalog/build-lock entries identify the exact ZIP checksum and size. Restore/build
paths reuse existing pack validation, private cache, update install and offline
fallback. Generated payloads and upstream notice copies remain outside Git.

Verification includes generator corruption/metadata/duplicate/Unicode tests,
mode-specific level counts and cumulative unions, real Anki/Qt coverage bars,
source-management provenance, unchanged notes/cards/revlog, package validation,
and clean/offline pack restoration. Run the real host smoke with:

```bash
QT_QPA_PLATFORM=offscreen QT_QPA_PLATFORMTHEME= QT_IM_MODULE=none /usr/bin/python scripts/smoke_jlpt_coverage.py
```
