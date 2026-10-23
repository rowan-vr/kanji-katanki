"""Refresh quietly; show one review window only when new cards can be created."""

import logging

from aqt.operations import QueryOp
from aqt.utils import showWarning, tooltip

from ..anki.refresh import prepare_refresh
from ..config import load_settings
from .generation import CreationReviewDialog

logger = logging.getLogger(f"addon.{__name__}")


def open_refresh(mw, *, automatic=False):
    if getattr(mw, "_katanki_refresh_running", False):
        return
    settings = load_settings(mw.col)
    if not settings.sources:
        showWarning("Choose vocabulary sources in Katanki → Settings → Discovery, then refresh.")
        return
    collection = mw.col
    mw._katanki_refresh_running = True

    def failed(error):
        mw._katanki_refresh_running = False
        logger.error("Katanki refresh failed", exc_info=(type(error), error, error.__traceback__))
        if mw.col is collection:
            showWarning(f"Katanki could not refresh:\n{error}\n\nReview Katanki → Settings.")

    def finished(result):
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
            if not report.scan.scanned_notes:
                tooltip(
                    "Refresh complete. No vocabulary notes matched your saved sources.", parent=mw
                )
            elif not report.scan.candidates:
                tooltip(
                    "Refresh complete. No kanji found in the selected vocabulary fields.", parent=mw
                )
            elif not report.dictionary_loaded and any(
                item.auto_generate for item in settings.generation
            ):
                showWarning("Enable KANJIDIC2 in Katanki → Settings → Dictionaries, then refresh.")
            elif preview is not None and any(
                item.outcome == "create" for item in preview.plan.items
            ):
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
                    f"Refresh complete. No new cards to create. {existing} already present · "
                    f"{result.ignored_count} ignored · {unavailable} unavailable.",
                    parent=mw,
                )
        except Exception as error:
            failed(error)
        finally:
            mw._katanki_refresh_running = False

    try:
        QueryOp(
            parent=mw, op=lambda collection: prepare_refresh(collection, settings), success=finished
        ).failure(failed).with_progress(
            "Katanki: refreshing vocabulary and dictionaries"
        ).run_in_background()
    except Exception:
        mw._katanki_refresh_running = False
        raise
