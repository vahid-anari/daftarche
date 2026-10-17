"""Draw the app icon and the splash image: a small rising chart on the app's warm dark background.

Run from the repository root: python tools/make_icon.py [bars|combo]
Writes src/daftarche/data/icons/app_icon.png (1024 x 1024, transparent corners,
macOS icon grid) and src/daftarche/data/icons/splash.png (1600 x 900, chart on the
right, room for the title on the left). Same family as linecat's and Maxwell
Bloch Studio's icons, in the Finance theme colours (style.py DEFAULTS).
"""
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

ICON_OUT = "src/daftarche/data/icons/app_icon.png"
SPLASH_OUT = "src/daftarche/data/icons/splash.png"
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "bars"
S = 1024                      # icon canvas
SIDE = 824                    # icon body (macOS grid)
OFF = (S - SIDE) // 2
R = int(0.2237 * SIDE)        # corner radius
SPLASH = (1600, 900)
INCOME = "#2ecc71"
INCOME_CORE = "#b9f5d0"
ACCENT = "#7c6af7"
BASELINE = "#e8e0d0"
HEIGHTS = [0.22, 0.36, 0.30, 0.50]   # bar heights, in units of the chart scale


def background(w, h):
    """Warm near-black (bottom-left) to warm grey-brown, a touch of violet accent (top-right)."""
    yy, xx = np.mgrid[0:1:h * 1j, 0:1:w * 1j]
    g = (0.55 * xx + 0.45 * (1 - yy))[..., None]
    c0, c1, c2 = np.array([22, 20, 17]), np.array([46, 42, 35]), np.array([84, 72, 104])
    col = np.where(g < 0.5, c0 + (c1 - c0) * (g / 0.5), c1 + (c2 - c1) * ((g - 0.5) / 0.5))
    return Image.fromarray(col.astype(np.uint8), "RGB").convert("RGBA")


def glow(size, draw_fn, color, passes, core):
    """A shape drawn several times, wide and blurred to narrow and sharp."""
    out = Image.new("RGBA", size, (0, 0, 0, 0))
    for i, (grow, blur, alpha) in enumerate(passes):
        layer = Image.new("RGBA", size, (0, 0, 0, 0))
        draw_fn(ImageDraw.Draw(layer), core if i == len(passes) - 1 else color, grow)
        if blur:
            layer = layer.filter(ImageFilter.GaussianBlur(blur))
        if alpha < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v, a=alpha: int(v * a)))
        out = Image.alpha_composite(out, layer)
    return out


def overlay(alpha_mask, rgb):
    layer = Image.new("RGBA", alpha_mask.size, rgb + (0,))
    layer.putalpha(alpha_mask)
    return layer


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


def chart(img, x0, x1, base, unit, variant):
    """Baseline, four bars and (combo) a trend arrow; `unit` scales heights, widths and glow."""
    size, k = img.size, unit / SIDE
    img = Image.alpha_composite(img, glow(
        size, lambda d, c, g: d.line((x0 - 10 * k, base, x1 + 10 * k, base), fill=c, width=round((8 + g) * k)),
        ACCENT, ((28, 18 * k, 0.6), (0, 0, 1.0)), BASELINE))

    n, gap = len(HEIGHTS), 0.045 * unit
    w = (x1 - x0 - (n - 1) * gap) / n
    rects = [(x0 + i * (w + gap), base - h * unit - 14 * k, x0 + i * (w + gap) + w, base - 14 * k)
             for i, h in enumerate(HEIGHTS)]

    def bars(d, c, g):
        for (a, b, cc, e) in rects:
            d.rounded_rectangle((a - g * k, b - g * k, cc + g * k, e), radius=(18 + g) * k, fill=c)

    bar_alpha = 1.0 if variant == "bars" else 0.30
    img = Image.alpha_composite(img, glow(size, bars, INCOME, ((30, 34 * k, 0.45 * bar_alpha),
                                                               (10, 10 * k, 0.7 * bar_alpha),
                                                               (0, 0, bar_alpha)), INCOME))
    if variant == "bars":
        hl = Image.new("L", size, 0)
        hd = ImageDraw.Draw(hl)
        for (a, b, cc, e) in rects:
            hd.rounded_rectangle((a + 14 * k, b + 14 * k, a + 0.38 * (cc - a), e - 14 * k), radius=10 * k, fill=70)
        return Image.alpha_composite(img, overlay(hl.filter(ImageFilter.GaussianBlur(6 * k)), hex_rgb(INCOME_CORE)))

    pts = [((a + cc) / 2, b - 40 * k) for (a, b, cc, e) in rects]
    tip = (pts[-1][0] + 0.035 * unit, pts[-1][1] - 0.06 * unit)

    def line(d, c, g):
        d.line(pts + [tip], fill=c, width=round((26 + g) * k), joint="curve")
        for (px, py) in pts[:-1]:
            r = (13 + g / 2) * k
            d.ellipse((px - r, py - r, px + r, py + r), fill=c)

    img = Image.alpha_composite(img, glow(size, line, INCOME, ((44, 30 * k, 0.5), (16, 10 * k, 0.85), (0, 0, 1.0)),
                                          INCOME_CORE))
    dx, dy = tip[0] - pts[-1][0], tip[1] - pts[-1][1]
    ux, uy = dx / np.hypot(dx, dy), dy / np.hypot(dx, dy)
    a, b = 40 * k, 52 * k
    head = [(tip[0] + a * ux, tip[1] + a * uy),
            (tip[0] - a * ux + b * uy, tip[1] - a * uy - b * ux),
            (tip[0] - a * ux - b * uy, tip[1] - a * uy + b * ux)]
    return Image.alpha_composite(img, glow(size, lambda d, c, g: d.polygon(head, fill=c),
                                           INCOME, ((0, 18 * k, 0.8), (0, 0, 1.0)), INCOME_CORE))


def make_icon():
    img = chart(background(SIDE, SIDE), 0.19 * SIDE, 0.81 * SIDE, 0.78 * SIDE, SIDE, VARIANT)

    # glossy highlight, light rim on top, dark rim at the bottom (as Studio's icon)
    hl = Image.new("L", (SIDE, SIDE), 0)
    ImageDraw.Draw(hl).ellipse((-SIDE * 0.3, -SIDE * 0.9, SIDE * 1.3, SIDE * 0.38), fill=26)
    img = Image.alpha_composite(img, overlay(hl.filter(ImageFilter.GaussianBlur(90)), (255, 255, 255)))
    mask = Image.new("L", (SIDE, SIDE), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, SIDE - 1, SIDE - 1), R, fill=255)
    rim = np.array(ImageChops.subtract(mask, mask.filter(ImageFilter.GaussianBlur(10))), dtype=float)
    up = np.linspace(1, 0, SIDE)[:, None]
    img = Image.alpha_composite(img, overlay(Image.fromarray((rim * up * 0.9).astype(np.uint8)), (255, 255, 255)))
    img = Image.alpha_composite(img, overlay(Image.fromarray((rim * (1 - up) * 0.8).astype(np.uint8)), (20, 12, 0)))

    out = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow_mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(shadow_mask).rounded_rectangle((OFF, OFF + 12, OFF + SIDE, OFF + SIDE + 12), R, fill=90)
    shadow = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    shadow.putalpha(shadow_mask.filter(ImageFilter.GaussianBlur(18)))
    out = Image.alpha_composite(out, shadow)
    out.paste(img, (OFF, OFF), mask)
    out.save(ICON_OUT)
    print(f"-> {ICON_OUT} ({VARIANT})")


def make_splash():
    w, h = SPLASH
    unit = 0.95 * h
    img = chart(background(w, h), 0.60 * w, 0.92 * w, 0.80 * h, unit, VARIANT)
    # soft dark band on the left keeps the title readable
    shade = np.clip(1 - np.linspace(0, 1, w) / 0.6, 0, 1)[None, :] * np.ones((h, 1))
    img = Image.alpha_composite(img, overlay(Image.fromarray((shade * 70).astype(np.uint8)), (10, 8, 6)))
    img.convert("RGB").save(SPLASH_OUT)
    print(f"-> {SPLASH_OUT} ({VARIANT})")


make_icon()
make_splash()
