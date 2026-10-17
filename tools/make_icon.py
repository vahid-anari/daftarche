"""Draw the app icon: a small rising chart on the app's warm dark background.

Run from the repository root: python tools/make_icon.py [bars|combo]
Writes src/finance/data/icons/app_icon.png (1024 x 1024, transparent corners,
macOS icon grid). Same family as linecat's and Maxwell Bloch Studio's icons,
in the Finance theme colours (style.py DEFAULTS).
"""
import sys

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter

OUT = "src/finance/data/icons/app_icon.png"
VARIANT = sys.argv[1] if len(sys.argv) > 1 else "bars"
S = 1024                      # canvas
SIDE = 824                    # icon body (macOS grid)
OFF = (S - SIDE) // 2
R = int(0.2237 * SIDE)        # corner radius
INCOME = "#2ecc71"
INCOME_CORE = "#b9f5d0"
ACCENT = "#7c6af7"
BASELINE = "#e8e0d0"


def background():
    """Warm near-black (bottom-left) to warm grey-brown, a touch of violet accent (top-right)."""
    yy, xx = np.mgrid[0:1:SIDE * 1j, 0:1:SIDE * 1j]
    g = (0.55 * xx + 0.45 * (1 - yy))[..., None]
    c0, c1, c2 = np.array([22, 20, 17]), np.array([46, 42, 35]), np.array([84, 72, 104])
    col = np.where(g < 0.5, c0 + (c1 - c0) * (g / 0.5), c1 + (c2 - c1) * ((g - 0.5) / 0.5))
    return Image.fromarray(col.astype(np.uint8), "RGB").convert("RGBA")


def glow(draw_fn, color, passes, core):
    """A shape drawn several times, wide and blurred to narrow and sharp."""
    out = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
    for i, (grow, blur, alpha) in enumerate(passes):
        layer = Image.new("RGBA", (SIDE, SIDE), (0, 0, 0, 0))
        draw_fn(ImageDraw.Draw(layer), core if i == len(passes) - 1 else color, grow)
        if blur:
            layer = layer.filter(ImageFilter.GaussianBlur(blur))
        if alpha < 1:
            layer.putalpha(layer.getchannel("A").point(lambda v, a=alpha: int(v * a)))
        out = Image.alpha_composite(out, layer)
    return out


def overlay(alpha_mask, rgb):
    layer = Image.new("RGBA", (SIDE, SIDE), rgb + (0,))
    layer.putalpha(alpha_mask)
    return layer


def hex_rgb(h):
    return tuple(int(h[i:i + 2], 16) for i in (1, 3, 5))


img = background()
x0, x1, base = 0.19 * SIDE, 0.81 * SIDE, 0.78 * SIDE

img = Image.alpha_composite(img, glow(
    lambda d, c, g: d.line((x0 - 10, base, x1 + 10, base), fill=c, width=8 + g),
    ACCENT, ((28, 18, 0.6), (0, 0, 1.0)), BASELINE))

heights = [0.22, 0.36, 0.30, 0.50]
n, gap = len(heights), 0.045 * SIDE
w = (x1 - x0 - (n - 1) * gap) / n
rects = [(x0 + i * (w + gap), base - h * SIDE - 14, x0 + i * (w + gap) + w, base - 14)
         for i, h in enumerate(heights)]

def bars(d, c, g):
    for (a, b, cc, e) in rects:
        d.rounded_rectangle((a - g, b - g, cc + g, e), radius=18 + g, fill=c)

bar_alpha = 1.0 if VARIANT == "bars" else 0.30
img = Image.alpha_composite(img, glow(bars, INCOME, ((30, 34, 0.45 * bar_alpha), (10, 10, 0.7 * bar_alpha),
                                                     (0, 0, bar_alpha)), INCOME))
hl = Image.new("L", (SIDE, SIDE), 0)
hd = ImageDraw.Draw(hl)
for (a, b, cc, e) in rects:
    hd.rounded_rectangle((a + 14, b + 14, a + 0.38 * (cc - a), e - 14), radius=10, fill=70)
if VARIANT == "bars":
    img = Image.alpha_composite(img, overlay(hl.filter(ImageFilter.GaussianBlur(6)), hex_rgb(INCOME_CORE)))
if VARIANT != "bars":
    pts = [((a + cc) / 2, b - 40) for (a, b, cc, e) in rects]
    tip = (pts[-1][0] + 0.035 * SIDE, pts[-1][1] - 0.06 * SIDE)

    def line(d, c, g):
        d.line(pts + [tip], fill=c, width=26 + g, joint="curve")
        for (px, py) in pts[:-1]:
            d.ellipse((px - 13 - g / 2, py - 13 - g / 2, px + 13 + g / 2, py + 13 + g / 2), fill=c)

    img = Image.alpha_composite(img, glow(line, INCOME, ((44, 30, 0.5), (16, 10, 0.85), (0, 0, 1.0)), INCOME_CORE))
    dx, dy = tip[0] - pts[-1][0], tip[1] - pts[-1][1]
    L = np.hypot(dx, dy)
    ux, uy = dx / L, dy / L
    head = [(tip[0] + 40 * ux, tip[1] + 40 * uy),
            (tip[0] - 40 * ux + 52 * uy, tip[1] - 40 * uy - 52 * ux),
            (tip[0] - 40 * ux - 52 * uy, tip[1] - 40 * uy + 52 * ux)]
    img = Image.alpha_composite(img, glow(lambda d, c, g: d.polygon(head, fill=c),
                                          INCOME, ((0, 18, 0.8), (0, 0, 1.0)), INCOME_CORE))

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
out.save(OUT)
print(f"-> {OUT} ({VARIANT})")
