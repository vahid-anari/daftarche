"""Small charts drawn with plain Flet controls and a canvas: bars and lines.

Plain controls keep the app free of chart packages (and of their build steps); these charts
only need to be clear on a phone, not interactive.
"""

from __future__ import annotations

import math

import flet as ft
import flet.canvas as cv

from .snapshot import money


def nice_max(value):
    """A round number at or above ``value`` (1, 1.5, 2, 2.5, 3, 4, 5, 6 or 8 times a power of ten)."""
    if value <= 0:
        return 1.0
    power = 10 ** math.floor(math.log10(value))
    for step in (1, 1.5, 2, 2.5, 3, 4, 5, 6, 8, 10):
        if value <= step * power:
            return step * power
    return 10 * power


def short_money(value):
    """$1.2k, $35k, $1.4M: axis labels."""
    a = abs(value)
    sign = "-" if value < 0 else ""
    if a >= 1e6:
        return f"{sign}${a / 1e6:.1f}M".replace(".0M", "M")
    if a >= 1e3:
        return f"{sign}${a / 1e3:.1f}k".replace(".0k", "k")
    return f"{sign}${a:.0f}"


def bar_chart(p, labels, groups, height=170, bar_width=10, gap=3, stacked=False):
    """Bars over months.

    ``groups``: ``[(colour, [value per label])]``, side by side, or one on top of the other
    with ``stacked``. Negative values (money back) are drawn as 0.
    """
    n = len(labels)
    if n == 0:
        return ft.Text("Nothing in this period", color=p.dim, size=13)
    totals = ([sum(max(v[i], 0) for _, v in groups) for i in range(n)] if stacked
              else [max((max(v[i], 0) for _, v in groups), default=0) for i in range(n)])
    top = nice_max(max(totals, default=0))

    columns = []
    for i, label in enumerate(labels):
        if stacked:
            pieces = [ft.Container(width=bar_width * 2 + gap, height=max(v[i], 0) / top * height, bgcolor=c)
                      for c, v in reversed(groups) if v[i] > 0]
            bar = ft.Column(pieces, spacing=0, alignment=ft.MainAxisAlignment.END, height=height)
        else:
            bar = ft.Row([ft.Container(width=bar_width, height=max(v[i], 0) / top * height, bgcolor=c,
                                       border_radius=ft.BorderRadius.only(top_left=3, top_right=3))
                          for c, v in groups],
                         spacing=gap, vertical_alignment=ft.CrossAxisAlignment.END, height=height)
        columns.append(ft.Column([bar, ft.Text(label, size=10, color=p.dim)], spacing=4,
                                 horizontal_alignment=ft.CrossAxisAlignment.CENTER))
    axis = ft.Column([ft.Text(short_money(top * f), size=10, color=p.dim) for f in (1, 0.5, 0)],
                     alignment=ft.MainAxisAlignment.SPACE_BETWEEN, height=height,
                     horizontal_alignment=ft.CrossAxisAlignment.END)
    bars = ft.Row(columns, spacing=10, scroll=ft.ScrollMode.AUTO, vertical_alignment=ft.CrossAxisAlignment.END)
    return ft.Row([ft.Column([axis, ft.Container(height=16)], spacing=0), ft.Container(bars, expand=True)],
                  vertical_alignment=ft.CrossAxisAlignment.START, spacing=8)


class LineChart(ft.Container):
    """Lines over months, one per series; the canvas is drawn again when its size changes."""

    def __init__(self, p, labels, series, height=190):
        """``series``: ``[(colour, [value per label])]``."""
        self.p, self.labels, self.series = p, labels, series
        self.canvas = cv.Canvas(shapes=[], on_resize=self._resized, expand=True)
        super().__init__(content=self.canvas, height=height)

    def _resized(self, e):
        self.canvas.shapes = self._shapes(e.width, e.height)
        self.canvas.update()

    def _shapes(self, w, h):
        p, labels = self.p, self.labels
        values = [v for _, vs in self.series for v in vs]
        if not labels or not values or w <= 0:
            return [cv.Text(0, 0, "Nothing in this period", ft.TextStyle(size=13, color=p.dim))]
        lo, hi = min(0.0, min(values)), max(0.0, max(values))
        hi = nice_max(hi) if hi > 0 else 0.0
        lo = -nice_max(-lo) if lo < 0 else 0.0
        if hi == lo:
            hi = lo + 1
        left, bottom, top = 44, 18, 6
        plot_w, plot_h = w - left - 6, h - bottom - top

        def x(i):
            return left + (plot_w * i / (len(labels) - 1) if len(labels) > 1 else plot_w / 2)

        def y(v):
            return top + plot_h * (hi - v) / (hi - lo)

        grid = ft.Paint(color=p.border, stroke_width=1)
        shapes = []
        ticks = {lo, hi} | ({hi / 2} if lo == 0 else {0.0})
        for v in sorted(ticks):
            shapes.append(cv.Line(left, y(v), w - 6, y(v), paint=grid))
            if v == 0 and lo < 0 and min(-lo, hi) / (hi - lo) < 0.12:
                continue  # too close to the end label: the line alone
            shapes.append(cv.Text(left - 6, y(v) - 7, short_money(v), ft.TextStyle(size=10, color=p.dim),
                                  text_align=ft.TextAlign.RIGHT, alignment=ft.Alignment.TOP_RIGHT))
        step = max(1, math.ceil(len(labels) / 5))
        for i in range(0, len(labels), step):
            shapes.append(cv.Text(x(i), h - 14, labels[i], ft.TextStyle(size=10, color=p.dim),
                                  alignment=ft.Alignment.TOP_CENTER))
        for colour, vs in self.series:
            if not vs:
                continue
            elements = [cv.Path.MoveTo(x(0), y(vs[0]))] + [cv.Path.LineTo(x(i), y(v)) for i, v in enumerate(vs)]
            shapes.append(cv.Path(elements, paint=ft.Paint(color=colour, stroke_width=2.2,
                                                           style=ft.PaintingStyle.STROKE,
                                                           stroke_join=ft.StrokeJoin.ROUND)))
            shapes.append(cv.Circle(x(len(vs) - 1), y(vs[-1]), 3, paint=ft.Paint(color=colour)))
        return shapes


def share_bar(p, fraction, colour, height=6):
    """A thin bar filled to ``fraction`` (0 to 1)."""
    fraction = min(max(fraction, 0.0), 1.0)
    return ft.Container(
        ft.Row([ft.Container(bgcolor=colour, expand=int(fraction * 1000) or None, height=height,
                             border_radius=height / 2, visible=fraction > 0),
                ft.Container(expand=int((1 - fraction) * 1000) or None, height=height,
                             visible=fraction < 1)], spacing=0),
        bgcolor=p.raised, border_radius=height / 2, height=height)


def legend(p, items):
    """``[(colour, text)]`` as small dots and names that wrap."""
    return ft.Row([ft.Row([ft.Container(width=9, height=9, bgcolor=c, border_radius=5),
                           ft.Text(t, size=12, color=p.dim)], spacing=5, tight=True) for c, t in items],
                  wrap=True, spacing=12, run_spacing=4)


__all__ = ["bar_chart", "LineChart", "share_bar", "legend", "nice_max", "short_money", "money"]
