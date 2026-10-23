"""Refresh saved sources with progress, useful results, and correction paths."""

import logging

from aqt.operations import QueryOp
from aqt.utils import showWarning, tooltip

from ..anki.refresh import prepare_refresh
from ..config import load_settings
from .generation import CreationReviewDialog
from .refresh_feedback import source_feedback

logger = logging.getLogger(f"addon.{__name__}")


def open_refresh(mw, *, automatic=False):
    if getattr(mw, "_katanki_refresh_running", False):
        if not automatic:
            tooltip("Katanki refresh is already running. Please wait for it to finish.", parent=mw)
        return
    settings = load_settings(mw.col)
    if not settings.sources:
        if not automatic:
            source_feedback(
                mw,
                "Choose vocabulary sources in Katanki → Settings → Discovery, then refresh. "
                "Select a deck, note type, and at least one vocabulary field. "
                "Saving your changes will retry Refresh.",
            )
        return
    collection = mw.col
    mw._katanki_refresh_running = True

    def failed(error):
        mw._katanki_refresh_running = False
        logger.error("Katanki refresh failed", exc_info=(type(error), error, error.__traceback__))
        if mw.col is collection:
            if isinstance(error, ValueError) and (
                "source" in str(error).lower() or "Discovery" in str(error)
            ):
                if automatic:
                    tooltip(
                        "Katanki refresh needs attention. Run Refresh manually to correct "
                        "your vocabulary sources.",
                        parent=mw,
                    )
                else:
                    source_feedback(
                        mw,
                        f"Refresh could not read your sources:\n{error}\n\n"
                        "Correct the source rows and save to retry Refresh.",
                    )
            else:
                showWarning(
                    f"Katanki could not finish refreshing:\n{error}\n\n"
                    "Check Katanki → Settings → Dictionaries for enabled files that moved "
                    "or cannot be read. Then run Refresh again. "
                    "If this continues, check Anki’s debug console for details.",
                    parent=mw,
                )

    def present(result, updated=0):
        try:
            if mw.col is not collection:
                return
            if automatic:
                if not load_settings(collection).refresh.enabled:
                    return
                # Never open a creation review over a review session or another dialog.
                if mw.state != "deckBrowser" or mw.app.activeModalWidget() is not None:
                    mw._katanki_automatic_refresh.request(
                        "on_profile_open" if settings.refresh.on_profile_open else "after_sync"
                    )
                    return
            report, preview = result.report, result.preview
            summary = f"Existing-card updates on {updated:,} notes. " if updated else ""
            if not report.scan.scanned_notes:
                if not automatic:
                    mw._katanki_refresh_running = False
                    source_feedback(
                        mw,
                        "No vocabulary notes matched your saved sources. "
                        "Check the deck and note type in Settings → Discovery. "
                        "Use Test discovery to verify the corrected rows; save to retry Refresh.",
                    )
            elif not report.scan.candidates:
                if not automatic:
                    mw._katanki_refresh_running = False
                    source_feedback(
                        mw,
                        f"Refresh complete. {summary}No kanji found. "
                        "Select fields containing Japanese vocabulary in Settings → Discovery. "
                        "Use Test discovery to check them; save to retry Refresh.",
                    )
            elif not report.dictionary_loaded and any(
                item.auto_generate for item in settings.generation
            ):
                showWarning("Enable KANJIDIC2 in Katanki → Settings → Dictionaries, then refresh.")
            elif preview is not None and any(
                item.outcome == "create" for item in preview.plan.items
            ):
                ready = sum(item.outcome == "create" for item in preview.plan.items)
                tooltip(f"{ready:,} cards ready for review.", parent=mw)
                CreationReviewDialog(mw, preview).exec()
            else:
                existing = (
                    sum(item.outcome == "skip" for item in preview.plan.items) if preview else 0
                )
                unavailable = (
                    sum(item.outcome == "unavailable" for item in preview.plan.items)
                    if preview
                    else 0
                )
                tooltip(
                    "Refresh complete. No new cards.\n"
                    + (f"{summary.strip()}\n" if summary else "")
                    + f"{existing:,} existing · {result.ignored_count:,} ignored · "
                    f"{unavailable:,} missing.",
                    parent=mw,
                )
        except Exception as error:
            failed(error)
        finally:
            mw._katanki_refresh_running = False

    def finished(result):
        examples = getattr(result, "examples", None)
        if examples is None or not examples.updates:
            if examples and examples.conflicts:
                report_conflicts(examples.conflicts)
            present(result)
            return
        if mw.col is not collection:
            mw._katanki_refresh_running = False
            return
        if automatic and (
            not load_settings(collection).refresh.enabled
            or mw.state != "deckBrowser"
            or mw.app.activeModalWidget() is not None
        ):
            present(result)
            return
        try:
            migrate = False
            migrations = tuple(update for update in examples.updates if update.migration)
            if migrations and not automatic:
                from .example_refresh import review_migration

                migrate = review_migration(mw, migrations)
            from aqt.operations import CollectionOp

            from ..anki.refresh import apply_refresh_examples

            def applied(outcome):
                if mw.col is collection:
                    if outcome.conflicts:
                        report_conflicts(outcome.conflicts)
                present(result, outcome.updated)

            CollectionOp(
                parent=mw,
                op=lambda col: apply_refresh_examples(col, result, settings, migrate=migrate),
            ).success(applied).failure(failed).run_in_background()
        except Exception as error:
            failed(error)

    def report_conflicts(conflicts):
        message = "Existing-card refresh preserved notes with conflicts:\n" + "\n".join(conflicts)
        logger.warning(message)
        if mw.col is collection:
            if automatic:
                tooltip(
                    f"Existing-card refresh: {len(conflicts)} conflicts; notes preserved. "
                    "Run Refresh manually to review.",
                    parent=mw,
                )
            else:
                showWarning(message, parent=mw)

    try:
        QueryOp(
            parent=mw, op=lambda collection: prepare_refresh(collection, settings), success=finished
        ).failure(failed).with_progress("Katanki: refreshing…").run_in_background()
    except Exception:
        mw._katanki_refresh_running = False
        raise
