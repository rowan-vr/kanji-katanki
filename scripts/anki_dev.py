"""Run with Anki's Python interpreter to prepare an isolated development profile."""

import argparse
import os
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.build_addon import build  # noqa: E402


def prepare(base: Path) -> None:
    import anki.lang
    from aqt.profiles import ProfileManager

    marker = base / ".katanki-development"
    if base.exists() and not marker.exists():
        raise RuntimeError(f"Refusing to reuse an unmarked Anki base: {base}")
    base.mkdir(parents=True, exist_ok=True)
    marker.touch()
    anki.lang.set_lang("en_US")
    pm = ProfileManager(base)
    pm.setupMeta()
    pm.meta.update({"defaultLang": "en_US", "firstRun": False, "updates": False})
    pm.set_check_for_addon_updates(False)
    pm.create("Katanki Development")
    pm.load("Katanki Development")
    pm.profile["autoSync"] = False
    pm.save()
    pm.db.close()
    destination = base / "addons21" / "katanki"
    # Replace only our own staged code, preserving every profile and collection.
    if destination.exists():
        shutil.rmtree(destination)
    from zipfile import ZipFile

    with ZipFile(build(ROOT / "dist" / "kanji-katanki.ankiaddon")) as archive:
        archive.extractall(destination)


def smoke(base: Path) -> None:
    import aqt
    from aqt import gui_hooks
    from aqt.qt import QMenu, QMessageBox, QTimer

    passed = False

    def check() -> None:
        nonlocal passed
        try:
            mw = aqt.mw
            assert mw is not None and mw.col is not None
            assert Path(mw.pm.base) == base
            menu = mw.form.menuTools.findChild(QMenu, "katanki_menu")
            assert menu is not None, "Kanji Katanki menu was not registered"
            before = (mw.col.note_count(), mw.col.card_count())
            dialog_seen = False

            def dismiss() -> None:
                nonlocal dialog_seen
                for widget in mw.app.topLevelWidgets():
                    if isinstance(widget, QMessageBox) and widget.windowTitle().startswith(
                        "Kanji Katanki"
                    ):
                        dialog_seen = True
                        widget.accept()

            QTimer.singleShot(100, dismiss)
            menu.actions()[0].trigger()
            assert dialog_seen, "Kanji Katanki dialog did not appear"
            assert before == (mw.col.note_count(), mw.col.card_count())
            passed = True
            print(
                "PASS: real Anki loaded packaged Kanji Katanki; menu/dialog work; counts unchanged."
            )
        finally:
            aqt.mw.unloadProfileAndExit()

    gui_hooks.profile_did_open.append(lambda: QTimer.singleShot(100, check))
    app = aqt._run(["anki", "-b", str(base), "-p", "Katanki Development"], exec=False)
    if app is None:
        raise RuntimeError("Anki did not start")
    QTimer.singleShot(30_000, app.quit)
    app.exec()
    if not passed:
        raise RuntimeError("Anki integration smoke test failed or timed out")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--smoke", action="store_true", help="Open and verify Anki, then exit")
    args = parser.parse_args()
    os.environ.setdefault("QT_QUICK_BACKEND", "software")
    os.environ["ANKI_SINGLE_INSTANCE_KEY"] = "katanki-development"
    base = (ROOT / ".anki-test").resolve()
    prepare(base)
    if args.smoke:
        smoke(base)
    else:
        print(
            "Prepared isolated profile. Launch: "
            "env QT_QUICK_BACKEND=software ANKI_SINGLE_INSTANCE_KEY=katanki-development "
            f'anki -b "{base}" '
            '-p "Katanki Development"'
        )
