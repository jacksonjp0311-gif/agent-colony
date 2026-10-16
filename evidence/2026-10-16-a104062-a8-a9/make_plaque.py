#!/usr/bin/env python3
"""Generate plaque.png: an instrument-style card for A104062 a(8), a(9).

4000x2100 px (1200x630 OG proportions at 300 DPI). Requires Pillow and
IBM Plex fonts (Serif, Sans Condensed, Mono); falls back to DejaVu.
Usage: python3 make_plaque.py  -> writes plaque.png next to this script.
"""
import math, os, glob
from PIL import Image, ImageDraw, ImageFont

W, H = 4000, 2100
BG, BONE, SAGE = "#1c1d1b", "#eeeee6", "#b7c4b6"
DIM = "#5d625b"  # sage at low intensity for hairlines

def font(names, size):
    roots = ["/usr/share/fonts", os.path.expanduser("~/.fonts"),
             os.path.expanduser("~/.local/share/fonts")]
    for n in names:
        for r in roots:
            hits = glob.glob(os.path.join(r, "**", n), recursive=True)
            if hits:
                return ImageFont.truetype(hits[0], size)
    return ImageFont.truetype("DejaVuSans.ttf", size)

serif = lambda s: font(["IBMPlexSerif-Light.ttf", "DejaVuSerif.ttf"], s)
serif_i = lambda s: font(["IBMPlexSerif-LightItalic.ttf", "DejaVuSerif.ttf"], s)
sans = lambda s: font(["IBMPlexSansCondensed-Regular.ttf", "DejaVuSans.ttf"], s)
sans_m = lambda s: font(["IBMPlexSansCondensed-Medium.ttf", "DejaVuSans.ttf"], s)
mono = lambda s: font(["IBMPlexMono-Light.ttf", "DejaVuSansMono.ttf"], s)
mono_r = lambda s: font(["IBMPlexMono-Regular.ttf", "DejaVuSansMono.ttf"], s)

img = Image.new("RGB", (W, H), BG)
d = ImageDraw.Draw(img)

def spaced(xy, text, f, fill, track=0.18, anchor="l"):
    """Draw letter-spaced text; anchor l/r/m on x."""
    x, y = xy
    widths = [d.textlength(c, font=f) for c in text]
    gap = f.size * track
    total = sum(widths) + gap * (len(text) - 1)
    if anchor == "r": x -= total
    elif anchor == "m": x -= total / 2
    for c, w in zip(text, widths):
        d.text((x, y), c, font=f, fill=fill)
        x += w + gap

M = 170  # outer margin
# frame: hairline border with corner registration ticks
d.rectangle([M - 60, M - 60, W - M + 60, H - M + 60], outline=DIM, width=3)
for cx, cy in [(M-60, M-60), (W-M+60, M-60), (M-60, H-M+60), (W-M+60, H-M+60)]:
    d.line([cx - 40, cy, cx + 40, cy], fill=SAGE, width=3)
    d.line([cx, cy - 40, cx, cy + 40], fill=SAGE, width=3)
# top/bottom ruler ticks
for i in range(0, 121):
    x = M + i * (W - 2 * M) / 120
    L = 34 if i % 10 == 0 else (20 if i % 5 == 0 else 10)
    d.line([x, H - M + 60, x, H - M + 60 - L], fill=DIM, width=2)

# ---- wordmark ----
spaced((M + 20, M + 30), "AGENT", sans_m(64), BONE, 0.42)
wa = sum(d.textlength(c, font=sans_m(64)) for c in "AGENT") + 64*0.42*5
d.text((M + 20 + wa + 30, M + 14), "Colony", font=serif_i(80), fill=SAGE)
spaced((W - M - 20, M + 40), "OEIS  A104062  ·  EVIDENCE CARD", sans(52), SAGE, 0.2, "r")
d.line([M + 20, M + 150, W - M - 20, M + 150], fill=DIM, width=2)

# ---- left column ----
LX = M + 20
d.text((LX, M + 230), "Four consecutive primes,", font=serif(120), fill=BONE)
d.text((LX, M + 370), "each 6 apart.", font=serif(120), fill=BONE)
d.text((LX, M + 545), "p,  p+6,  p+12,  p+18     e.g.  251 · 257 · 263 · 269",
       font=mono(54), fill=SAGE)

def readout(x, y, label, value, subs):
    spaced((x, y), label, sans_m(46), SAGE, 0.25)
    d.text((x, y + 62), value, font=mono_r(112), fill=BONE)
    for i, sub in enumerate(subs):
        d.text((x, y + 205 + i * 56), sub, font=sans(42), fill=SAGE)
C2 = LX + 980
readout(LX, M + 700, "a(8)", "1,031,312", ["first 2·10⁹ primes"])
readout(C2, M + 700, "a(9)", "7,863,231", ["first 2·10¹⁰ primes"])
readout(LX, M + 1040, "a(10)", "61,341,010", ["first 2·10¹¹ primes"])
readout(C2, M + 1040, "a(11)", "487,855,645",
        ["first 2·10¹² primes", "up to 61,427,839,512,211"])

# ---- gauge (log scale of relative error) ----
GX, GY, R = 3000, 1250, 600
A0, A1 = 180, 0          # degrees: 1% at A0, 0.0001% at A1
def ang(err_pct):
    t = (0 - math.log10(err_pct)) / 4.0
    return math.radians(A0 + (A1 - A0) * t)
def pt(a, r):
    return GX + r * math.cos(a), GY - r * math.sin(a)

d.arc([GX - R, GY - R, GX + R, GY + R], -A0, -A1, fill=SAGE, width=3)
d.arc([GX - R + 110, GY - R + 110, GX + R - 110, GY + R - 110], -A0, -A1, fill=DIM, width=2)
labels = {0: "1%", 1: "0.1%", 2: "0.01%", 3: "0.001%", 4: "0.0001%"}
for dec in range(0, 5):
    for m in range(1, 10):
        if dec == 4 and m > 1: break
        e = m * 10.0 ** (-dec)
        if e > 1.0000001: continue
        a = ang(e)
        major = (m == 1)
        L = 70 if major else 34
        d.line([pt(a, R), pt(a, R - L)], fill=BONE if major else SAGE,
               width=4 if major else 2)
        if major:
            x, y = pt(a, R + (130 if dec in (0, 4) else 85))
            d.text((x, y), labels[dec], font=mono(46), fill=SAGE, anchor="mm")

def needle(err, label, primary, r_lab, side):
    a = ang(err)
    col = BONE if primary else SAGE
    d.line([pt(a, 40), pt(a, R - 20)], fill=col, width=7 if primary else 3)
    tx, ty = pt(a + math.radians(side), r_lab)
    d.text((tx, ty), label, font=sans_m(44), fill=col, anchor="mm")
needle(0.09, "a(8)", False, 400, 8)
needle(0.009, "a(9)", False, 470, 7)
needle(0.012, "a(10)", False, 300, -10)
needle(0.0005, "a(11)", True, 400, -8)
d.ellipse([GX - 34, GY - 34, GX + 34, GY + 34], outline=BONE, width=4, fill=BG)
# arrow hint of direction along inner arc
spaced((GX, M + 215), "PREDICTION ERROR", sans_m(46), SAGE, 0.3, "m")
spaced((GX, M + 285), "log scale", sans(40), DIM, 0.2, "m")

# headline numbers under gauge
d.text((GX, GY + 175), "0.09%  →  0.0005%", font=mono_r(120), fill=BONE, anchor="mm")
d.text((GX, GY + 320), "Hardy–Littlewood k-tuple conjecture, 1923",
       font=serif_i(56), fill=SAGE, anchor="mm")
d.text((GX, GY + 395), "with consecutive-prime correction",
       font=sans(44), fill=SAGE, anchor="mm")

# ---- footer ----
FY = H - M - 70
d.text((LX, FY), "independent counters agree",
       font=sans(48), fill=SAGE, anchor="ls")
spaced((W - M - 20, FY - 40), "COMPUTED, NOT PROOF",
       sans(42), DIM if False else SAGE, 0.22, "r")

out = os.path.join(os.path.dirname(os.path.abspath(__file__)), "plaque.png")
img.save(out, dpi=(300, 300))
print(out)
