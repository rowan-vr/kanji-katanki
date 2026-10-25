"""Read-only, modeless Qt statistics with list/group coverage and a kanji explorer."""

from dataclasses import replace
from datetime import datetime

from aqt import dialogs, gui_hooks
from aqt.operations import QueryOp
from aqt.qt import (
    QAbstractItemView,
    QComboBox,
    QDialog,
    QFont,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QItemSelectionModel,
    QLabel,
    QLineEdit,
    QListView,
    QPlainTextEdit,
    QProgressBar,
    QPushButton,
    QScrollArea,
    QSplitter,
    Qt,
    QTimer,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..anki.statistics import character_details, dashboard_snapshot
from ..config import load_settings, save_settings
from ..stats.groups import (
    LABELS,
    STATE_SORT_ORDER,
    count_description,
    counts_for,
    coverage_sections,
)
from ..stats.progress import STATES
from .statistics_widgets import (
    KanjiDelegate,
    KanjiFilter,
    KanjiModel,
    OverviewBox,
    StateSwatch,
    StrokeDiagram,
)


def label(text="", *, wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    return widget


class StatisticsDialog(QDialog):
    def __init__(self, mw):
        super().__init__(mw)
        self.mw, self.collection = mw, mw.col
        self.snapshot = None
        self.allowed = set()
        self.loading = False
        self.reload_pending = False
        self.closed = False
        self.selected_character = None
        self.detail_data = None
        self.sections = ()
        self.section_items = {}
        self.counts = {}
        self.setWindowTitle("Katanki — Statistics")
        self.setObjectName("katanki_statistics")
        self.resize(1280, 850)
        self.setMinimumSize(850, 540)
        layout = QVBoxLayout(self)
        heading = QHBoxLayout()
        title = label("Kanji statistics")
        font = title.font()
        font.setPointSize(21)
        font.setBold(True)
        title.setFont(font)
        heading.addWidget(title)
        heading.addStretch()
        self.manage = QPushButton("Manage lists…")
        self.manage.clicked.connect(self._settings)
        self.refresh = QPushButton("Refresh")
        self.refresh.clicked.connect(self.reload)
        self.history = QPushButton("History…")
        self.history.clicked.connect(self._history)
        heading.addWidget(self.history)
        heading.addWidget(self.manage)
        heading.addWidget(self.refresh)
        layout.addLayout(heading)
        layout.addWidget(
            label(
                "Katanki kanji cards · Entire collection · Recognition and writing are independent"
            )
        )
        filters = QHBoxLayout()
        filters.addWidget(label("Mode"))
        self.mode = QComboBox()
        self.mode.setAccessibleName("Evidence mode")
        self.mode.addItem("Recognition", "recognition")
        self.mode.addItem("Writing", "writing")
        filters.addWidget(self.mode)
        self.search = QLineEdit()
        self.search.setClearButtonEnabled(True)
        self.search.setPlaceholderText("Search kanji, meaning or reading…")
        self.search.setAccessibleName("Search kanji")
        filters.addWidget(self.search, 1)
        self.state_filter = QComboBox()
        self.state_filter.setAccessibleName("Progress state filter")
        self.state_filter.addItem("All states", None)
        for state in STATES:
            self.state_filter.addItem(LABELS[state], state)
        filters.addWidget(self.state_filter)
        filters.addWidget(label("Sort"))
        self.sort_by = QComboBox()
        self.sort_by.setAccessibleName("Kanji sort order")
        self.sort_by.addItem("Learning state", "state")
        self.sort_by.addItem("List order", "list")
        self.sort_by.setToolTip(
            "Learning state: "
            + ", ".join(LABELS[state].lower() for state in STATE_SORT_ORDER)
            + ". "
            "Within each state, preserve list order. List order follows the dataset sequence."
        )
        filters.addWidget(self.sort_by)
        layout.addLayout(filters)
        summaries = QHBoxLayout()
        self.count_labels = {}
        for state, title in (("total", "Unique targets"), *LABELS.items()):
            box = OverviewBox(title, state)
            box_layout = QVBoxLayout(box)
            box_layout.setContentsMargins(10, 8, 10, 10)
            box_layout.setSpacing(5)
            box_layout.addWidget(label(title))
            value = label("0")
            value.setAlignment(Qt.AlignmentFlag.AlignCenter)
            font = value.font()
            font.setPointSize(17)
            font.setBold(True)
            value.setFont(font)
            box_layout.addWidget(value)
            self.count_labels[state] = value
            summaries.addWidget(box)
        layout.addLayout(summaries)
        legend = QHBoxLayout()
        legend.addWidget(label("Colours:"))
        for state in STATES:
            legend.addWidget(StateSwatch(state, self))
            legend.addWidget(label(LABELS[state]))
            legend.addSpacing(8)
        legend.addStretch()
        layout.addLayout(legend)
        layout.addWidget(
            label(
                "Known = young + mature. Mature = review interval ≥21 days. "
                "Relearning takes priority for mixed cards, then the least advanced state. "
                "Suspended/buried cards retain their state.",
                wrap=True,
            )
        )
        self.status = label("Loading target lists and Anki progress…", wrap=True)
        layout.addWidget(self.status)
        self.warning_button = QPushButton()
        self.warning_button.setCheckable(True)
        self.warning_button.hide()
        self.warnings = QPlainTextEdit()
        self.warnings.setReadOnly(True)
        self.warnings.setMaximumHeight(100)
        self.warnings.hide()
        self.warning_button.toggled.connect(self.warnings.setVisible)
        layout.addWidget(self.warning_button)
        layout.addWidget(self.warnings)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        layout.addWidget(splitter, 1)
        self.scope = QTreeWidget()
        self.scope.setObjectName("katanki_statistics_groups")
        self.scope.setHeaderLabels(["List / group", "Known / targets", "Mature"])
        self.scope.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.scope.setToolTip(
            "Select a list or grade to inspect it. Ctrl/Cmd-click combines groups; "
            "overlapping targets count once."
        )
        self.scope.setMinimumWidth(420)
        self.scope.header().setStretchLastSection(False)
        self.scope.header().setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        self.scope.header().setSectionResizeMode(1, QHeaderView.ResizeMode.Fixed)
        self.scope.header().setSectionResizeMode(2, QHeaderView.ResizeMode.ResizeToContents)
        self.scope.setColumnWidth(1, 145)
        splitter.addWidget(self.scope)
        center = QWidget()
        center_layout = QVBoxLayout(center)
        center_layout.setContentsMargins(3, 0, 3, 0)
        self.scope_title = label("All enabled lists", wrap=True)
        self.visible_count = label()
        center_layout.addWidget(self.scope_title)
        center_layout.addWidget(self.visible_count)
        self.source = KanjiModel(self)
        self.proxy = KanjiFilter(self)
        self.proxy.setSourceModel(self.source)
        self.grid = QListView()
        self.grid.setObjectName("katanki_statistics_grid")
        self.grid.setAccessibleName("Kanji progress grid")
        self.grid.setViewMode(QListView.ViewMode.IconMode)
        self.grid.setResizeMode(QListView.ResizeMode.Adjust)
        self.grid.setMovement(QListView.Movement.Static)
        self.grid.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        self.grid.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.grid.setUniformItemSizes(True)
        self.grid.setModel(self.proxy)
        self.grid.setItemDelegate(KanjiDelegate(self))
        center_layout.addWidget(self.grid, 1)
        self.empty = label("Enable a target list under Settings → Statistics → Lists.", wrap=True)
        self.empty.hide()
        center_layout.addWidget(self.empty)
        splitter.addWidget(center)
        detail_scroll = QScrollArea()
        detail_scroll.setWidgetResizable(True)
        detail_scroll.setMinimumWidth(230)
        details = QWidget()
        detail_layout = QVBoxLayout(details)
        detail_layout.addWidget(label("Character details"))
        self.character = label()
        font = QFont(self.character.font())
        font.setPointSize(48)
        self.character.setFont(font)
        detail_layout.addWidget(self.character)
        self.definition = label("Select a kanji to inspect both evidence modes.", wrap=True)
        detail_layout.addWidget(self.definition)
        self.readings = label(wrap=True)
        detail_layout.addWidget(self.readings)
        self.evidence_boxes, self.evidence_labels, self.browse_buttons = {}, {}, {}
        for mode, title in (("recognition", "Recognition"), ("writing", "Writing")):
            box = QGroupBox(title)
            box_layout = QVBoxLayout(box)
            text = label(wrap=True)
            box_layout.addWidget(text)
            button = QPushButton("View matching cards in Anki")
            button.clicked.connect(lambda checked=False, mode=mode: self._browse(mode))
            box_layout.addWidget(button)
            detail_layout.addWidget(box)
            self.evidence_boxes[mode], self.evidence_labels[mode], self.browse_buttons[mode] = (
                box,
                text,
                button,
            )
            box.hide()
        self.stroke_box = QGroupBox("Offline stroke order")
        stroke_layout = QVBoxLayout(self.stroke_box)
        self.strokes = StrokeDiagram()
        stroke_layout.addWidget(self.strokes)
        stroke_actions = QHBoxLayout()
        self.play = QPushButton("Play strokes")
        self.play.clicked.connect(self.strokes.play)
        self.reset = QPushButton("Reset")
        self.reset.clicked.connect(self.strokes.reset)
        stroke_actions.addWidget(self.play)
        stroke_actions.addWidget(self.reset)
        stroke_layout.addLayout(stroke_actions)
        detail_layout.addWidget(self.stroke_box)
        self.stroke_box.hide()
        self.detail_warnings = label(wrap=True)
        detail_layout.addWidget(self.detail_warnings)
        detail_layout.addStretch()
        detail_scroll.setWidget(details)
        splitter.addWidget(detail_scroll)
        splitter.setSizes([410, 480, 330])
        splitter.setCollapsible(0, False)
        splitter.setCollapsible(1, False)
        splitter.setCollapsible(2, False)
        self.scope.itemSelectionChanged.connect(self._render_scope)
        self.mode.currentIndexChanged.connect(self._mode_changed)
        self.search.textChanged.connect(self._filter)
        self.state_filter.currentIndexChanged.connect(self._filter)
        self.sort_by.currentIndexChanged.connect(self._filter)
        self.grid.selectionModel().currentChanged.connect(self._choose_kanji)
        gui_hooks.operation_did_execute.append(self._changed)
        gui_hooks.profile_will_close.append(self.close)
        QTimer.singleShot(0, self.reload)

    def _valid(self):
        return not self.closed and self.mw.col is self.collection

    def _set_loading(self, loading):
        self.loading = loading
        for control in (
            self.refresh,
            self.manage,
            self.scope,
            self.mode,
            self.search,
            self.state_filter,
            self.sort_by,
        ):
            control.setEnabled(not loading)

    def reload(self):
        if not self._valid():
            return
        if self.loading:
            self.reload_pending = True
            return
        self._set_loading(True)
        self.status.setText("Loading target lists and Anki progress…")
        QueryOp(parent=self.mw, op=dashboard_snapshot, success=self._loaded).failure(
            self._failed
        ).run_in_background()

    def _loaded(self, snapshot):
        if not self._valid():
            return
        self._set_loading(False)
        if self.reload_pending:
            self.reload_pending = False
            self.reload()
            return
        selected = [
            tuple(item.data(0, Qt.ItemDataRole.UserRole)) for item in self.scope.selectedItems()
        ]
        if not self.snapshot and hasattr(self.collection, "get_config"):
            selected = list(load_settings(self.collection).statistics_selection)
        self.snapshot = snapshot
        registry, progress, metadata, warnings = snapshot
        self.sections = coverage_sections(registry, progress)
        self.allowed = {char for section in self.sections for char in section.characters}
        self.scope.blockSignals(True)
        self.scope.clear()
        self.section_items = {}
        for section in self.sections:
            parent = self.section_items.get(section.parent)
            item = QTreeWidgetItem(parent if parent is not None else self.scope, [section.title])
            item.setData(0, Qt.ItemDataRole.UserRole, section.key)
            item.setExpanded(True)
            self.section_items[section.key] = item
        self._update_group_counts()
        for key in selected or [("", None)]:
            if key in self.section_items:
                self.section_items[key].setSelected(True)
        if not self.scope.selectedItems():
            self.section_items[("", None)].setSelected(True)
        self.scope.blockSignals(False)
        self.warnings.setPlainText("\n\n".join([*progress.warnings, *warnings]))
        count = len(progress.warnings) + len(warnings)
        self.warning_button.setText(f"Data warnings ({count})")
        self.warning_button.setVisible(bool(count))
        self.warnings.setVisible(bool(count) and self.warning_button.isChecked())
        self.status.setText(
            "Snapshot: " + datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")
        )
        self._render_scope()

    def _update_group_counts(self):
        mode = self.mode.currentData()
        for section in self.sections:
            counts = counts_for(self.snapshot[1], section.characters, mode)
            total = len(set(section.characters))
            known = counts["young"] + counts["mature"]
            item = self.section_items[section.key]
            item.setText(2, f"{counts['mature']:,}")
            item.setTextAlignment(2, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            tooltip = (
                "Generated from Katanki recognition and writing cards across the collection. "
                "Includes suspended/buried cards; membership is shared by both modes.\n"
                if section.key == ("@cards", None)
                else ""
            ) + (
                f"{section.title}\n{count_description(counts)}\nEach group has its own denominator."
            )
            for column in range(3):
                item.setToolTip(column, tooltip)
            bar = self.scope.itemWidget(item, 1)
            if bar is None:
                bar = QProgressBar()
                self.scope.setItemWidget(item, 1, bar)
            bar.setRange(0, max(total, 1))
            bar.setValue(known)
            bar.setFormat(f"{known:,} / {total:,} (%p%)")
            bar.setToolTip(tooltip)

    def select_scope(self, key):
        self.scope.setCurrentItem(
            self.section_items[key], 0, QItemSelectionModel.SelectionFlag.ClearAndSelect
        )

    def _render_scope(self):
        if not self.snapshot:
            return
        selected = [
            section for section in self.sections if self.section_items[section.key].isSelected()
        ]
        characters = tuple(
            dict.fromkeys(char for section in selected for char in section.characters)
        )
        if self._valid() and hasattr(self.collection, "get_config"):
            selection = tuple(section.key for section in selected)
            settings = load_settings(self.collection)
            if settings.statistics_selection != selection:
                save_settings(self.collection, replace(settings, statistics_selection=selection))
        self.current_targets = characters
        self.scope_title.setText(
            " · ".join(section.title for section in selected) or "Select a list or group"
        )
        progress, metadata = self.snapshot[1:3]
        payload = progress.payload(characters)
        self.counts = payload["counts"][self.mode.currentData()]
        self.count_labels["total"].setText(f"{len(characters):,}")
        for state in STATES:
            self.count_labels[state].setText(f"{self.counts[state]:,}")
        rows = [row | metadata.get(row["character"], {}) for row in payload["rows"]]
        self.source.set_rows(rows, self.mode.currentData())
        self._clear_details()
        self._filter()

    def _mode_changed(self):
        if self.snapshot:
            self._update_group_counts()
            self._render_scope()

    def _filter(self):
        self.proxy.configure(
            self.search.text(),
            self.state_filter.currentData(),
            self.mode.currentData(),
            self.sort_by.currentData(),
        )
        total, shown = self.source.rowCount(), self.proxy.rowCount()
        self.visible_count.setText(f"{shown:,} shown · {total:,} unique targets")
        self.empty.setVisible(shown == 0)
        self.empty.setText(
            "No kanji match these filters."
            if total
            else "Select a list or group. Enable lists under Settings → Statistics → Lists."
        )

    def _clear_details(self):
        self.selected_character = None
        self.detail_data = None
        self.character.clear()
        self.definition.setText("Select a kanji to inspect both evidence modes.")
        self.readings.clear()
        self.detail_warnings.clear()
        for box in self.evidence_boxes.values():
            box.hide()
        self.strokes.set_svg(None)
        self.stroke_box.hide()

    def _choose_kanji(self, index, previous=None):
        if not index.isValid() or not self._valid():
            self._clear_details()
            return
        character = index.data(Qt.ItemDataRole.DisplayRole)
        if character not in self.allowed:
            return
        self._clear_details()
        self.selected_character = character
        self.character.setText(character)
        self.definition.setText("Loading details…")
        progress = self.snapshot[1]
        QueryOp(
            parent=self.mw,
            op=lambda col: character_details(col, progress, character),
            success=lambda data: (
                self._details_loaded(data)
                if self.snapshot and self.snapshot[1] is progress
                else None
            ),
        ).failure(lambda error: self._detail_failed(character, error)).run_in_background()

    def _details_loaded(self, data):
        if not self._valid() or data["character"] != self.selected_character:
            return
        self.detail_data = data
        dictionary = data.get("dictionary")
        self.definition.setText(
            " · ".join(dictionary["meanings"])
            if dictionary
            else "No dictionary entry available; this target remains in the list."
        )
        self.readings.setText(
            "On: "
            + ("、".join(dictionary["on"]) or "—")
            + "\nKun: "
            + ("、".join(dictionary["kun"]) or "—")
            if dictionary
            else ""
        )
        for mode, evidence in data["evidence"].items():
            lines = [LABELS[evidence["state"]]]
            if not evidence["cards"]:
                lines.append(
                    "Matching note exists, but has no cards."
                    if evidence["note_ids"]
                    else f"No matching {'production' if mode == 'writing' else 'recognition'} note."
                )
            else:
                answered, passed = evidence["answered"], evidence["passed"]
                lines.append(
                    f"{answered:,} answered reviews"
                    + (f" · {passed / answered:.0%} pass rate" if answered else "")
                )
                lines.append("All recorded answers; manual reschedules excluded.")
                for card in evidence["cards"]:
                    flags = (" · Suspended" if card["suspended"] else "") + (
                        " · Buried" if card["buried"] else ""
                    )
                    lines.append(
                        f"\nCard {card['card_id']}: {LABELS[card['state']]}{flags}\n"
                        f"Interval {card['interval']} d · {card['reviews']} reviews · "
                        f"{card['lapses']} lapses"
                    )
            self.evidence_labels[mode].setText("\n".join(lines))
            self.browse_buttons[mode].setEnabled(bool(evidence["cards"]))
            self.evidence_boxes[mode].show()
        self.strokes.set_svg(data.get("svg"))
        self.stroke_box.setVisible(bool(data.get("svg")))
        self.detail_warnings.setText("\n".join(data["warnings"]))

    def _detail_failed(self, character, error):
        if self._valid() and self.selected_character == character:
            self.definition.setText(f"Could not load details: {error}")

    def _browse(self, mode):
        if self.detail_data and self._valid():
            cards = self.detail_data["evidence"][mode]["cards"]
            if cards:
                query = " or ".join(f"cid:{card['card_id']}" for card in cards)
                dialogs.open("Browser", self.mw).search_for(query)

    def _history(self):
        from .history import HistoryDialog

        dialog = HistoryDialog(self.mw)
        dialog.exec()

    def _settings(self):
        from .settings import open_settings

        open_settings(self.mw, tab="Statistics")
        self.reload()

    def _failed(self, error):
        if self._valid():
            self._set_loading(False)
            self.status.setText(f"Could not load statistics: {error}")
            if self.reload_pending:
                self.reload_pending = False
                self.reload()

    def _changed(self, changes, handler):
        if self._valid():
            self.status.setText("Collection changed. Refresh to update this snapshot.")

    def closeEvent(self, event):
        self._cleanup()
        super().closeEvent(event)

    def done(self, result):
        self._cleanup()
        super().done(result)

    def _cleanup(self):
        if not self.closed:
            self.closed = True
            self.strokes.timer.stop()
            gui_hooks.operation_did_execute.remove(self._changed)
            gui_hooks.profile_will_close.remove(self.close)


def open_statistics(mw):
    dialog = getattr(mw, "_katanki_statistics", None)
    if dialog is None or dialog.closed:
        dialog = StatisticsDialog(mw)
        mw._katanki_statistics = dialog
    else:
        dialog.reload()
    dialog.show()
    dialog.raise_()
    dialog.activateWindow()
