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
