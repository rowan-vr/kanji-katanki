"""Native model/view kanji tiles and Qt SVG stroke playback."""

from xml.etree import ElementTree as ET

from aqt.qt import (
    QAbstractListModel,
    QByteArray,
    QColor,
    QEvent,
    QFont,
    QModelIndex,
    QPainter,
    QPalette,
    QRectF,
    QSize,
    QSortFilterProxyModel,
    QStyle,
    QStyledItemDelegate,
    Qt,
    QTimer,
    QWidget,
)
from PyQt6.QtSvg import QSvgRenderer

from ..stats.groups import LABELS, STATE_SORT_ORDER, normalize_search

LIGHT = {
    "missing": "#e1e3e8",
    "new": "#e77d79",
    "learning": "#f3a450",
    "young": "#63d4c5",
    "mature": "#216334",
    "relearning": "#bc9aeb",
}
DARK = {
    "missing": "#414651",
    "new": "#a93636",
    "learning": "#f3a450",
    "young": "#63d4c5",
    "mature": "#216334",
    "relearning": "#bc9aeb",
}


def state_colors(state, palette):
    dark = palette.color(QPalette.ColorRole.Base).lightness() < 128
    background = QColor((DARK if dark else LIGHT)[state])
    foreground = QColor("#ffffff" if background.lightness() < 128 else "#17212b")
    return background, foreground


class OverviewBox(QWidget):
    """A single, softly tinted surface for a summary label and count."""

    def __init__(self, title, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setAccessibleName(title)

    def paintEvent(self, event):
        palette = self.palette()
        base = palette.color(QPalette.ColorRole.Window)
        dark = base.lightness() < 128
        if self.state == "total":
            background = base.lighter(110) if dark else base.darker(102)
        else:
            accent, _ = state_colors(self.state, palette)
            amount = 0.18 if dark else 0.12
            background = QColor(
                *[
                    round(channel * (1 - amount) + colour * amount)
                    for channel, colour in zip(base.getRgb()[:3], accent.getRgb()[:3], strict=True)
                ]
            )
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(base.lighter(140) if dark else base.darker(115))
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 5, 5)


class StateSwatch(QWidget):
    """Legend uses the exact tile colours, including after a theme change."""

    def __init__(self, state, parent=None):
        super().__init__(parent)
        self.state = state
        self.setFixedSize(18, 18)
        self.setAccessibleName(LABELS[state])

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        background, _ = state_colors(self.state, self.palette())
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(QRectF(self.rect()).adjusted(1, 1, -1, -1), 3, 3)


ROOT_INDEX = QModelIndex()


class KanjiModel(QAbstractListModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.rows = []
        self.mode = "recognition"

    def rowCount(self, parent=ROOT_INDEX):
        return 0 if parent.isValid() else len(self.rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not 0 <= index.row() < len(self.rows):
            return None
        row = self.rows[index.row()]
        if role == Qt.ItemDataRole.DisplayRole:
            return row["character"]
        if role == Qt.ItemDataRole.UserRole:
            return row
        if role == Qt.ItemDataRole.ToolTipRole:
            return f"{row['character']} — {LABELS[row[self.mode]]}\n" + ", ".join(
                row.get("meanings", ())
            )
        if role == Qt.ItemDataRole.AccessibleTextRole:
            return f"{row['character']}: {LABELS[row[self.mode]]}"
        return None

    def set_rows(self, rows, mode):
        self.beginResetModel()
        self.rows = rows
        self.mode = mode
        self.endResetModel()


class KanjiFilter(QSortFilterProxyModel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.query, self.state, self.mode = "", None, "recognition"
        self.sort_by = "state"

    def configure(self, query, state, mode, sort_by="state"):
        self.query, self.state, self.mode = normalize_search(query.strip()), state, mode
        self.sort_by = sort_by
        self.invalidate()
        self.sort(-1 if sort_by == "list" else 0)

    def lessThan(self, left, right):
        left_state = left.data(Qt.ItemDataRole.UserRole)[self.mode]
        right_state = right.data(Qt.ItemDataRole.UserRole)[self.mode]
        return (STATE_SORT_ORDER.index(left_state), left.row()) < (
            STATE_SORT_ORDER.index(right_state),
            right.row(),
        )

    def filterAcceptsRow(self, row, parent):
        source = self.sourceModel()
        entry = source.data(source.index(row, 0, parent), Qt.ItemDataRole.UserRole)
        if self.state is not None and entry[self.mode] != self.state:
            return False
        text = " ".join(
            [
                entry["character"],
                *entry.get("meanings", ()),
                *entry.get("on", ()),
                *entry.get("kun", ()),
            ]
        )
        return not self.query or self.query in normalize_search(text)


class KanjiDelegate(QStyledItemDelegate):
    def sizeHint(self, option, index):
        return QSize(49, 52)

    def paint(self, painter, option, index):
        row = index.data(Qt.ItemDataRole.UserRole)
        if not row:
            return
        state = row[self.parent().source.mode]
        background, foreground = state_colors(state, option.palette)
        painter.save()
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect = QRectF(option.rect).adjusted(3, 3, -3, -3)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(background)
        painter.drawRoundedRect(rect, 6, 6)
        if option.state & (QStyle.StateFlag.State_Selected | QStyle.StateFlag.State_HasFocus):
            painter.setPen(option.palette.color(QPalette.ColorRole.Highlight))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(rect.adjusted(1, 1, -1, -1), 5, 5)
        painter.setPen(foreground)
        font = QFont(option.font)
        font.setPointSize(20)
        painter.setFont(font)
        painter.drawText(rect, Qt.AlignmentFlag.AlignCenter, row["character"])
        painter.restore()


class StrokeDiagram(QWidget):
    """Reveal sanitized paths in source order, using Qt SVG and a Qt timer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.renderer = QSvgRenderer(self)
        self.original = None
        self.stroke_count = 0
        self.frame = 0
        self.timer = QTimer(self)
        self.timer.setInterval(40)
        self.timer.timeout.connect(self._advance)
        self.setMinimumSize(140, 160)
        self.setMaximumHeight(250)
        self.setAccessibleName("Offline stroke-order diagram")

    def set_svg(self, svg):
        self.timer.stop()
        self.original = svg
        self.stroke_count = (
            sum(node.tag.endswith("path") for node in ET.fromstring(svg).iter()) if svg else 0
        )
        self.frame = self.stroke_count * 8
        self._render_frame()

    def play(self):
        if self.stroke_count:
            self.frame = 0
            self._render_frame()
            self.timer.start()

    def reset(self):
        self.timer.stop()
        self.frame = self.stroke_count * 8
        self._render_frame()

    def _advance(self):
        self.frame += 1
        if self.frame >= self.stroke_count * 8:
            self.timer.stop()
        self._render_frame()

    def _render_frame(self):
        if self.original:
            root = ET.fromstring(self.original)
            color = self.palette().color(QPalette.ColorRole.Text).name()
            current, fraction = divmod(self.frame, 8)
            paths = [node for node in root.iter() if node.tag.endswith("path")]
            for index, path in enumerate(paths):
                path.set("stroke", color)
                path.set(
                    "opacity",
                    "1"
                    if index < current
                    else str((fraction + 1) / 8)
                    if index == current
                    else "0",
                )
            self.renderer.load(QByteArray(ET.tostring(root, encoding="utf-8")))
        else:
            self.renderer.load(QByteArray())
        self.update()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.PaletteChange and hasattr(self, "renderer"):
            self._render_frame()

    def paintEvent(self, event):
        if self.original:
            painter = QPainter(self)
            self.renderer.render(painter, QRectF(self.rect()))
