"""Refresh preconditions and failures must leave no running operation behind."""

import importlib.util
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest

import katanki
from katanki.config import GenerationSettings, Settings, SourceRule


@pytest.fixture
def refresh(monkeypatch):
    operations = ModuleType("aqt.operations")
    operations.QueryOp = Mock()
    operations.CollectionOp = Mock()
    utils = ModuleType("aqt.utils")
    utils.tooltip, utils.showWarning = Mock(), Mock()
    generation = ModuleType("katanki.ui.generation")
    generation.CreationReviewDialog = Mock()
    for module in (operations, utils, generation):
        monkeypatch.setitem(sys.modules, module.__name__, module)
    path = Path(katanki.__file__).parent / "ui/refresh.py"
    spec = importlib.util.spec_from_file_location("katanki.ui._test_refresh", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.load_settings = Mock(return_value=Settings())
    return module, operations, utils, SimpleNamespace(col=Mock())


def test_missing_sources_points_to_settings_without_starting_scan(refresh):
    module, operations, utils, mw = refresh
    module.open_refresh(mw)
    operations.QueryOp.assert_not_called()
    assert "Settings → Discovery" in utils.showWarning.call_args.args[0]
    assert not getattr(mw, "_katanki_refresh_running", False)


def test_disabled_categories_still_refresh_without_creation_prompt(refresh):
    module, operations, utils, mw = refresh
    module.load_settings.return_value = Settings(
        sources=(SourceRule("*", 10, ("Front",)),),
        generation=(GenerationSettings(),) * 3,
    )
    module.open_refresh(mw)
    finished = operations.QueryOp.call_args.kwargs["success"]
    finished(
        SimpleNamespace(
            report=SimpleNamespace(
                scan=SimpleNamespace(scanned_notes=1, candidates=("景",)), dictionary_loaded=True
            ),
            preview=SimpleNamespace(plan=SimpleNamespace(items=())),
            ignored_count=0,
        )
    )
    module.CreationReviewDialog.assert_not_called()
    utils.tooltip.assert_called_once()
    assert not mw._katanki_refresh_running


def test_duplicate_click_is_ignored_and_async_failure_unblocks_retry(refresh):
    module, operations, utils, mw = refresh
    module.load_settings.return_value = Settings(sources=(SourceRule("*", 10, ("Front",)),))
    module.open_refresh(mw)
    module.open_refresh(mw)
    operations.QueryOp.assert_called_once()
    assert mw._katanki_refresh_running
    failed = operations.QueryOp.return_value.failure.call_args.args[0]
    failed(ValueError("Missing source deck"))
    assert not mw._katanki_refresh_running
    assert "Missing source deck" in utils.showWarning.call_args.args[0]


def test_operation_start_failure_clears_running_flag(refresh):
    module, operations, _, mw = refresh
    module.load_settings.return_value = Settings(sources=(SourceRule("*", 10, ("Front",)),))
    operations.QueryOp.side_effect = RuntimeError("Could not start")
    with pytest.raises(RuntimeError, match="Could not start"):
        module.open_refresh(mw)
    assert not mw._katanki_refresh_running


def test_closed_profile_discards_background_result(refresh):
    module, operations, utils, mw = refresh
    module.load_settings.return_value = Settings(sources=(SourceRule("*", 10, ("Front",)),))
    module.open_refresh(mw)
    mw.col = None
    operations.QueryOp.call_args.kwargs["success"](None)
    module.CreationReviewDialog.assert_not_called()
    utils.showWarning.assert_not_called()
    assert not mw._katanki_refresh_running


def test_automatic_result_waits_if_review_started_during_scan(refresh):
    module, operations, _, mw = refresh
    from katanki.config import RefreshSettings

    module.load_settings.return_value = Settings(
        sources=(SourceRule("*", 10, ("Front",)),), refresh=RefreshSettings(True)
    )
    mw.state = "review"
    mw._katanki_automatic_refresh = Mock()
    module.open_refresh(mw, automatic=True)
    operations.QueryOp.call_args.kwargs["success"](None)
    module.CreationReviewDialog.assert_not_called()
    mw._katanki_automatic_refresh.request.assert_called_once_with("on_profile_open")
    assert not mw._katanki_refresh_running


@pytest.mark.parametrize("automatic", [False, True])
def test_refresh_applies_examples_in_collection_operation_and_reviews_migration(
    refresh, monkeypatch, automatic
):
    import katanki.anki.refresh as workflow
    from katanki.config import RefreshSettings

    module, operations, utils, mw = refresh
    module.load_settings.return_value = Settings(
        sources=(SourceRule("*", 10, ("Front",)),), refresh=RefreshSettings(enabled=True)
    )
    mw.state = "deckBrowser"
    mw.app = SimpleNamespace(activeModalWidget=lambda: None)
    review = ModuleType("katanki.ui.example_refresh")
    review.review_migration = Mock(return_value=True)
    monkeypatch.setitem(sys.modules, review.__name__, review)
    apply = Mock()
    monkeypatch.setattr(workflow, "apply_refresh_examples", apply)
    result = SimpleNamespace(
        report=SimpleNamespace(
            scan=SimpleNamespace(scanned_notes=1, candidates=("景",)), dictionary_loaded=True
        ),
        preview=None,
        ignored_count=0,
        examples=SimpleNamespace(updates=(SimpleNamespace(migration=True),), conflicts=()),
    )
    module.open_refresh(mw, automatic=automatic)
    operations.QueryOp.call_args.kwargs["success"](result)
    assert mw._katanki_refresh_running
    if automatic:
        review.review_migration.assert_not_called()
    else:
        review.review_migration.assert_called_once()
    operations.CollectionOp.call_args.kwargs["op"](mw.col)
    assert apply.call_args.kwargs["migrate"] is (not automatic)
    operations.CollectionOp.return_value.success.call_args.args[0](
        SimpleNamespace(updated=1, conflicts=())
    )
    assert not mw._katanki_refresh_running
    assert "Existing-card updates on 1 notes" in utils.tooltip.call_args.args[0]
