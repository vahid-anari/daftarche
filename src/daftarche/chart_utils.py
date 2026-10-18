"""
chart_utils.py — Shared chart styling helpers.

Key fixes:
- Qt QValueAxis uses C printf format: "$%.0f"
- Thousands separator: chart.setLocale(en_US) + chart.setLocalizeNumbers(True)
- X-axis label rotation: setLabelsAngle(-45) + setTruncateLabels(False)
"""
from PySide6.QtCharts import QValueAxis, QBarCategoryAxis, QChart, QLegend, QChartView
from PySide6.QtGui import QColor, QBrush, QFont, QPen, QPainter
from PySide6.QtCore import Qt, QLocale, QMargins, QEvent, Signal, QPointF, QRectF
from PySide6.QtWidgets import QLabel, QWidget

from daftarche.style import get_settings


class HoverChartView(QChartView):
    mouseMoved = Signal(object)
    mouseLeft = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setRenderHint(QPainter.Antialiasing)
        self.setMouseTracking(True)
        self.viewport().setMouseTracking(True)
        self.viewport().installEventFilter(self)

        self._hover_label = QLabel("", self.viewport())
        self._hover_label.setAlignment(Qt.AlignCenter)
        self._hover_label.setWordWrap(True)
        self._hover_label.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._hover_label.hide()

        self._last_mouse_pos = None
        self._style_hover_label()

    def eventFilter(self, obj, event):
        if obj is self.viewport():
            if event.type() == QEvent.MouseMove:
                pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
                self._last_mouse_pos = pos
                self.mouseMoved.emit(pos)

            elif event.type() == QEvent.Leave:
                self._last_mouse_pos = None
                self.hide_hover()
                self.mouseLeft.emit()

        return super().eventFilter(obj, event)

    def setChart(self, chart):
        """QChartView.setChart lets go of the old chart without deleting it: every refresh of
        a tab leaked its charts. Delete the old one (unless it is the same chart)."""
        old = self.chart()
        super().setChart(chart)
        if old is not None and old is not chart:
            old.deleteLater()

    def last_mouse_pos(self):
        return self._last_mouse_pos

    def refresh_hover_style(self):
        self._style_hover_label()

    def _style_hover_label(self, border_color=None):
        s = get_settings()
        border = border_color or "rgba(255,255,255,40)"

        self._hover_label.setStyleSheet(
            f"color:{s.get('text')}; background: rgba(20,20,30,200);"
            f" border: 1px solid {border};"
            f" border-radius: 6px; padding: 4px 10px;"
            f" font-size: {s.get('font_size')}pt;"
        )

    def show_hover(self, text, viewport_pos=None, border_color=None):
        if not text:
            self.hide_hover()
            return

        self._style_hover_label(border_color)

        self._hover_label.setText(text)
        self._hover_label.adjustSize()
        self._hover_label.raise_()

        if viewport_pos is None:
            viewport_pos = self._last_mouse_pos

        if viewport_pos is not None:
            vp = self.viewport()
            w = self._hover_label.width()
            h = self._hover_label.height()

            x = max(4, min(viewport_pos.x() + 12, vp.width() - w - 4))
            y = max(4, min(viewport_pos.y() - h - 8, vp.height() - h - 4))

            self._hover_label.move(x, y)

        self._hover_label.show()

    def hide_hover(self):
        self._hover_label.hide()


# _StackedOverlay  — paints per-month sorted stacked bars over QChartView
class StackedOverlay(QWidget):

    def __init__(self, chart_view, paint_data, on_hover_cb=None):
        super().__init__(chart_view.viewport())
        self._chart_view = chart_view
        self._paint_data = paint_data
        self._on_hover_cb = on_hover_cb
        self._hovered = None
        self.setAttribute(Qt.WA_TransparentForMouseEvents, False)
        self.setMouseTracking(True)
        self.resize(chart_view.viewport().size())
        chart_view.viewport().installEventFilter(self)

    def eventFilter(self, obj, event):
        if obj is self._chart_view.viewport() and event.type() == QEvent.Resize:
            self.resize(obj.size())
            self.update()
        return False

    def _bar_rects(self):
        chart = self._chart_view.chart()
        pd = self._paint_data
        periods = pd["all_periods"]
        order = pd["per_month_order"]
        data = pd["data"]
        n = len(periods)
        if n == 0 or not chart:
            return []

        rects = []
        for pi, period in enumerate(periods):
            cats_sorted = order[pi]
            baseline = 0.0
            for cat in cats_sorted:
                val = data[period].get(cat, 0)
                if val <= 0:
                    continue
                top_scene = chart.mapToScene(chart.mapToPosition(QPointF(pi, baseline + val)))
                bottom_scene = chart.mapToScene(chart.mapToPosition(QPointF(pi, baseline)))
                top_vp = self._chart_view.mapFromScene(top_scene)
                bottom_vp = self._chart_view.mapFromScene(bottom_scene)

                if n > 1:
                    left_scene = chart.mapToScene(chart.mapToPosition(QPointF(pi - 0.35, baseline)))
                    right_scene = chart.mapToScene(chart.mapToPosition(QPointF(pi + 0.35, baseline)))
                    left_vp = self._chart_view.mapFromScene(left_scene)
                    right_vp = self._chart_view.mapFromScene(right_scene)
                    bar_left = left_vp.x()
                    bar_right = right_vp.x()
                else:
                    plot = chart.plotArea()
                    bar_left = plot.left() + plot.width() * 0.25
                    bar_right = plot.right() - plot.width() * 0.25

                rect = QRectF(
                    bar_left,
                    top_vp.y(),
                    bar_right - bar_left,
                    abs(bottom_vp.y() - top_vp.y()),
                )
                rects.append((rect, pi, cat, val, baseline))
                baseline += val
        return rects

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing, False)
        colors = self._paint_data.get("cat_colors", {})

        for rect, pi, cat, val, baseline in self._bar_rects():
            color = QColor(colors.get(cat, "#888888"))
            painter.fillRect(rect, color)
            pen = QPen(QColor(255, 255, 255, 255))
            pen.setWidth(1)
            painter.setPen(pen)
            painter.drawRect(rect)

        painter.end()

    def mouseMoveEvent(self, event):
        pos = event.position().toPoint() if hasattr(event, "position") else event.pos()
        hit = None
        for rect, pi, cat, val, baseline in self._bar_rects():
            if rect.contains(pos):
                hit = (pi, cat, val, baseline, pos)
                break
        if hit != self._hovered:
            self._hovered = hit
            if self._on_hover_cb:
                self._on_hover_cb(hit)

    def leaveEvent(self, event):
        self._hovered = None
        if self._on_hover_cb:
            self._on_hover_cb(None)


def make_chart(title="", animated=True):
    s = get_settings()
    chart = QChart()
    if title:
        chart.setTitle(title)
        chart.setTitleFont(QFont(s.get("font_family"), s.get("font_size") + 1, QFont.Bold))
        chart.setTitleBrush(QBrush(QColor(s.get("text"))))

    chart.setBackgroundBrush(QBrush(QColor(s.get("bg_surface"))))

    if animated:
        chart.setAnimationOptions(QChart.SeriesAnimations)
    else:
        chart.setAnimationOptions(QChart.NoAnimation)

    chart.legend().setLabelColor(QColor(s.get("text")))
    chart.legend().setAlignment(Qt.AlignRight)
    chart.legend().setBackgroundVisible(False)
    chart.legend().setFont(QFont(s.get("font_family"), s.get("font_size")))
    chart.legend().setMarkerShape(QLegend.MarkerShapeRectangle)
    chart.setMargins(QMargins(10, 10, 10, 10))

    locale = QLocale(QLocale.Language.English, QLocale.Country.UnitedStates)
    chart.setLocale(locale)
    chart.setLocalizeNumbers(True)

    return chart


def make_y_axis(min_val=None, max_val=None):
    """Y axis with dollar values, proper Qt format string."""
    s = get_settings()
    ax = QValueAxis()
    ax.setLabelFormat("$%.0f")
    ax.setLabelsColor(QColor(s.get("text")))
    ax.setGridLineColor(QColor(s.get("border")))
    ax.setLinePen(QPen(QColor(s.get("border"))))
    ax.setTitleBrush(QBrush(QColor(s.get("text_dim"))))
    ax.setLabelsFont(QFont(s.get("font_family"), s.get("font_size") - 1))
    if min_val is not None:
        ax.setMin(min_val)
    if max_val is not None:
        ax.setMax(max_val)
    return ax


def make_x_axis(labels, rotate=None):
    """X axis with category labels, rotated for readability."""
    s = get_settings()
    ax = QBarCategoryAxis()
    ax.append(labels)
    ax.setLabelsColor(QColor(s.get("text")))
    ax.setGridLineColor(QColor(s.get("border")))
    ax.setLinePen(QPen(QColor(s.get("border"))))
    ax.setLabelsFont(QFont(s.get("font_family"), s.get("font_size") - 1))
    effective_rotate = rotate if rotate is not None else (-45 if len(labels) > 12 else 0)
    if effective_rotate:
        ax.setLabelsAngle(effective_rotate)
        ax.setTruncateLabels(False)
    return ax


def style_chart_view(view, bordered=True):
    s = get_settings()
    if bordered:
        view.setStyleSheet(
            f"background:{s.get('bg_surface')}; "
            f"border:1px solid {s.get('border')}; "
            f"border-radius:8px;"
        )
    else:
        view.setStyleSheet(
            "background: transparent; "
            "border: none;"
        )
