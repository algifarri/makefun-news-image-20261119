#!/usr/bin/env python3
"""Draw one newspaper-style poster that sums up the world news of
Thursday 19 November 2026, and write it to /output/entry.png.

Pure standard library: a small RGB framebuffer, a hand-drawn 5x7 bitmap
font, flat-shaded editorial scenes for each story, and a manual PNG
encoder (zlib + struct). No network, no randomness: two runs of this
program write byte-identical files.

The day's stories, as reported on 19 November 2026:
  * Grand Theft Auto VI launches worldwide after a 13-year wait,
    rolling out at midnight in each region, with a 99 on Metacritic
    and about $1.5 billion in preorders (Reuters, Nov 19).
  * Donald Trump, Xi Jinping and Vladimir Putin meet in Shenzhen on
    the sidelines of the APEC summit: a first-ever trilateral, plus
    a separate Trump-Putin meeting; Ukraine, Iran and nuclear arms
    on the agenda (Reuters / AP, Nov 18-19).
  * The United States and Iran exchange fire again: Iran widens its
    attacks on Gulf states, striking a US base in Kuwait and
    hitting Bahrain again after the US struck Qeshm Island.
  * The International Court of Justice delivers its ruling in The
    Gambia v. Myanmar, the genocide case over the Rohingya.
  * NASA's Voyager 1 reaches one light-day from Earth, almost 50
    years after launch; NASA confirms it at a news conference.
  * Ticker: the EU plans a 45 billion euro loan for Ukraine's
    budget; Canada adjusts its China ties; Australia sanctions
    Israeli settlers in the West Bank.
"""

import math
import os
import struct
import zlib

W = 1024
H = 1024

# ------------------------------------------------------------------ colours
PAPER = (247, 242, 228)
INK = (24, 24, 28)
FAINT = (120, 112, 96)
RULE = (24, 24, 28)
SKY = (168, 205, 232)
SKY_DEEP = (110, 160, 205)
SEA = (38, 96, 150)
SEA_DEEP = (26, 70, 116)
SAND = (232, 205, 150)
LAND = (106, 142, 74)
FIRE = (238, 110, 32)
FIRE_CORE = (250, 196, 60)
SMOKE = (105, 105, 110)
SMOKE_LT = (165, 165, 170)
RED = (178, 34, 44)
BLUE = (40, 70, 160)
GOLD = (214, 164, 40)
WHITE = (250, 250, 248)
TICKER_BG = (24, 24, 28)
TICKER_FG = (247, 242, 228)
SPACE = (10, 12, 34)
SPACE_LT = (32, 40, 80)
NEON_PINK = (255, 80, 160)
NEON_ORANGE = (255, 140, 40)
NEON_PURPLE = (120, 60, 180)
VICE_TEAL = (40, 190, 180)

FB = bytearray(W * H * 3)
CLIP = None  # (x0, y0, x1, y1) while a scene is painting, else None


def put(x, y, c):
    if CLIP is not None and not (CLIP[0] <= x < CLIP[2] and CLIP[1] <= y < CLIP[3]):
        return
    if 0 <= x < W and 0 <= y < H:
        i = (y * W + x) * 3
        FB[i] = c[0]
        FB[i + 1] = c[1]
        FB[i + 2] = c[2]


def fill_rect(x, y, w, h, c):
    for yy in range(y, y + h):
        for xx in range(x, x + w):
            put(xx, yy, c)


def disc(cx, cy, r, c):
    r2 = r * r
    for yy in range(cy - r, cy + r + 1):
        for xx in range(cx - r, cx + r + 1):
            if (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= r2:
                put(xx, yy, c)


def half_disc_up(cx, cy, r, c):
    """Filled dome: the top half of a disc sitting on the line y=cy."""
    r2 = r * r
    for yy in range(cy - r, cy + 1):
        for xx in range(cx - r, cx + r + 1):
            if (xx - cx) * (xx - cx) + (yy - cy) * (yy - cy) <= r2:
                put(xx, yy, c)


def stroke(x0, y0, x1, y1, wdt, c):
    """Thick line: walk the segment and stamp a small disc at each step."""
    steps = max(abs(x1 - x0), abs(y1 - y0), 1)
    rad = max(wdt // 2, 0)
    for i in range(steps + 1):
        x = x0 + (x1 - x0) * i // steps
        y = y0 + (y1 - y0) * i // steps
        if rad == 0:
            put(x, y, c)
        else:
            disc(x, y, rad, c)


def poly(points, c):
    """Scanline fill of a simple polygon."""
    ys = [p[1] for p in points]
    n = len(points)
    for y in range(min(ys), max(ys) + 1):
        hits = []
        for i in range(n):
            xa, ya = points[i]
            xb, yb = points[(i + 1) % n]
            if ya == yb:
                continue
            if (ya <= y < yb) or (yb <= y < ya):
                hits.append(xa + (y - ya) * (xb - xa) // (yb - ya))
        hits.sort()
        for i in range(0, len(hits) - 1, 2):
            for x in range(hits[i], hits[i + 1] + 1):
                put(x, y, c)


def frame(x, y, w, h, c, t=3):
    fill_rect(x, y, w, t, c)
    fill_rect(x, y + h - t, w, t, c)
    fill_rect(x, y, t, h, c)
    fill_rect(x + w - t, y, t, h, c)


# ------------------------------------------------------------------ font
# 5x7 bitmap glyphs, seven rows of five pixels, '#' lit. Uppercase only:
# the poster speaks in headlines.
FONT = {
    "A": (".###.", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "B": ("####.", "#...#", "#...#", "####.", "#...#", "#...#", "####."),
    "C": (".####", "#....", "#....", "#....", "#....", "#....", ".####"),
    "D": ("####.", "#...#", "#...#", "#...#", "#...#", "#...#", "####."),
    "E": ("#####", "#....", "#....", "####.", "#....", "#....", "#####"),
    "F": ("#####", "#....", "#....", "####.", "#....", "#....", "#...."),
    "G": (".####", "#....", "#....", "#.###", "#...#", "#...#", ".###."),
    "H": ("#...#", "#...#", "#...#", "#####", "#...#", "#...#", "#...#"),
    "I": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "J": ("..###", "...#.", "...#.", "...#.", "...#.", "#..#.", ".##.."),
    "K": ("#...#", "#..#.", "#.#..", "##...", "#.#..", "#..#.", "#...#"),
    "L": ("#....", "#....", "#....", "#....", "#....", "#....", "#####"),
    "M": ("#...#", "##.##", "#.#.#", "#.#.#", "#...#", "#...#", "#...#"),
    "N": ("#...#", "##..#", "#.#.#", "#..##", "#...#", "#...#", "#...#"),
    "O": (".###.", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "P": ("####.", "#...#", "#...#", "####.", "#....", "#....", "#...."),
    "Q": (".###.", "#...#", "#...#", "#...#", "#.#.#", "#..#.", ".##.#"),
    "R": ("####.", "#...#", "#...#", "####.", "#.#..", "#..#.", "#...#"),
    "S": (".####", "#....", "#....", ".###.", "....#", "....#", "####."),
    "T": ("#####", "..#..", "..#..", "..#..", "..#..", "..#..", "..#.."),
    "U": ("#...#", "#...#", "#...#", "#...#", "#...#", "#...#", ".###."),
    "V": ("#...#", "#...#", "#...#", "#...#", "#...#", ".#.#.", "..#.."),
    "W": ("#...#", "#...#", "#...#", "#.#.#", "#.#.#", "##.##", "#...#"),
    "X": ("#...#", ".#.#.", "..#..", "..#..", "..#..", ".#.#.", "#...#"),
    "Y": ("#...#", "#...#", ".#.#.", "..#..", "..#..", "..#..", "..#.."),
    "Z": ("#####", "....#", "...#.", "..#..", ".#...", "#....", "#####"),
    "0": (".###.", "#..##", "#.#.#", "##..#", "#...#", "#...#", ".###."),
    "1": ("..#..", ".##..", "..#..", "..#..", "..#..", "..#..", "#####"),
    "2": (".###.", "#...#", "....#", "..##.", ".#...", "#....", "#####"),
    "3": ("####.", "....#", "....#", ".###.", "....#", "....#", "####."),
    "4": ("...#.", "..##.", ".#.#.", "#..#.", "#####", "...#.", "...#."),
    "5": ("#####", "#....", "####.", "....#", "....#", "#...#", ".###."),
    "6": (".###.", "#....", "#....", "####.", "#...#", "#...#", ".###."),
    "7": ("#####", "....#", "...#.", "..#..", "..#..", "..#..", "..#.."),
    "8": (".###.", "#...#", "#...#", ".###.", "#...#", "#...#", ".###."),
    "9": (".###.", "#...#", "#...#", ".####", "....#", "....#", ".###."),
    " ": (".....", ".....", ".....", ".....", ".....", ".....", "....."),
    ".": (".....", ".....", ".....", ".....", ".....", ".##..", ".##.."),
    ",": (".....", ".....", ".....", ".....", ".##..", ".##..", ".#..."),
    ";": (".....", ".##..", ".##..", ".....", ".##..", ".##..", ".#..."),
    ":": (".....", ".##..", ".##..", ".....", ".##..", ".##..", "....."),
    "-": (".....", ".....", ".....", "#####", ".....", ".....", "....."),
    "'": (".##..", ".##..", ".#...", ".....", ".....", ".....", "....."),
    "!": ("..#..", "..#..", "..#..", "..#..", "..#..", ".....", "..#.."),
    "?": (".###.", "#...#", "....#", "..##.", "..#..", ".....", "..#.."),
    "/": ("....#", "....#", "...#.", "..#..", ".#...", "#....", "#...."),
    "(": ("..##.", ".#...", "#....", "#....", "#....", ".#...", "..##."),
    ")": (".##..", "...#.", "....#", "....#", "....#", "...#.", ".##.."),
    "+": (".....", "..#..", "..#..", "#####", "..#..", "..#..", "....."),
    "&": (".##..", "#..#.", "#.#..", ".#...", "#.#.#", "#..#.", ".##.#"),
    "€": (".####", "#....", "####.", "#....", "####.", "#....", ".####"),
}


def text_w(s, scale):
    return len(s) * 6 * scale - scale


def draw_text(s, x, y, scale, c, bold=False):
    """Draw string s with its top-left corner at (x, y)."""
    cx = x
    for ch in s.upper():
        glyph = FONT.get(ch, FONT[" "])
        for row in range(7):
            bits = glyph[row]
            for col in range(5):
                if bits[col] == "#":
                    fill_rect(cx + col * scale, y + row * scale,
                              scale, scale, c)
                    if bold:
                        fill_rect(cx + col * scale + scale // 2,
                                  y + row * scale, scale, scale, c)
        cx += 6 * scale
    return cx


def text_c(s, cx, y, scale, c, bold=False):
    """Draw string s centred on cx."""
    return draw_text(s, cx - text_w(s, scale) // 2, y, scale, c, bold)


def text_l(s, x, y, scale, c, bold=False):
    return draw_text(s, x, y, scale, c, bold)


# ------------------------------------------------------------------ scenes
def scene_gta(x, y, w, h):
    """Vice City at sunset: a neon sun over a waterfront skyline."""
    # sunset sky in flat bands
    fill_rect(x, y, w, h // 4, NEON_PURPLE)
    fill_rect(x, y + h // 4, w, h // 4, NEON_PINK)
    fill_rect(x, y + h // 2, w, h // 4, NEON_ORANGE)
    fill_rect(x, y + (3 * h) // 4, w, h - (3 * h) // 4, (40, 20, 60))
    # the big setting sun, high enough to clear the skyline
    disc(x + int(w * 0.68), y + 34, 34, FIRE_CORE)
    disc(x + int(w * 0.68), y + 34, 23, (255, 220, 120))
    # skyline silhouettes, two rows of towers
    for i, bh in enumerate((58, 84, 66, 96, 74, 88, 60, 78)):
        bx = x + 14 + i * (w - 28) // 8
        bw = (w - 28) // 8 - 6
        fill_rect(bx, y + (3 * h) // 4 - bh, bw, bh, (30, 16, 48))
        for wy in range(6):
            for wx in range(3):
                if (i + wy + wx) % 3 == 0:
                    fill_rect(bx + 4 + wx * 8, y + (3 * h) // 4 - bh + 8 + wy * 12,
                              4, 5, GOLD)
    # water strip with a bright reflection under the sun
    sea_y = y + (3 * h) // 4
    fill_rect(x, sea_y, w, y + h - sea_y, SEA_DEEP)
    for i in range(7):
        stroke(x + w // 2 - 60 + i * 6, sea_y + 8 + i * 4,
               x + w // 2 + 60 - i * 6, sea_y + 8 + i * 4, 3, FIRE_CORE)
    # palm trees framing the scene
    for px, flip in ((x + 26, 1), (x + w - 26, -1)):
        stroke(px, sea_y - 4, px + 4 * flip, sea_y - 44, 4, (30, 60, 30))
        for k in range(5):
            ang = math.pi * (0.15 + k * 0.18)
            ex = px + int(30 * math.cos(ang) * flip)
            ey = sea_y - 44 - int(14 * math.sin(ang))
            stroke(px + 4 * flip, sea_y - 44, ex, ey, 3, (34, 110, 60))
    # a low sports car speeding along the waterfront road
    cy = sea_y - 12
    poly([(x + w // 2 - 52, cy), (x + w // 2 - 34, cy - 12),
          (x + w // 2 + 18, cy - 12), (x + w // 2 + 52, cy)], NEON_PINK)
    fill_rect(x + w // 2 - 52, cy, 104, 8, (20, 10, 30))
    disc(x + w // 2 - 34, cy + 8, 7, INK)
    disc(x + w // 2 + 34, cy + 8, 7, INK)
    disc(x + w // 2 + 48, cy - 2, 3, GOLD)  # headlight


def scene_summit(x, y, w, h):
    """Three leaders around a summit table in Shenzhen, flags behind."""
    fill_rect(x, y, w, h, (216, 226, 238))
    # three flags on poles across the back wall: US, China, Russia
    for i, col in enumerate((BLUE, RED, WHITE)):
        fx = x + 30 + i * (w - 90) // 2
        fill_rect(fx, y + 10, 3, 46, INK)
        fill_rect(fx + 3, y + 10, 52, 26, col)
    fx = x + 30  # US: stripes + canton
    for r in range(4):
        fill_rect(fx + 3, y + 14 + r * 6, 52, 3, WHITE)
    fill_rect(fx + 3, y + 10, 22, 13, BLUE)
    fx = x + 30 + (w - 90) // 2  # China: five gold stars
    for sx, sy in ((10, 14), (22, 12), (28, 18), (24, 26), (14, 24)):
        disc(fx + 3 + sx, y + sy, 2, GOLD)
    fx = x + 30 + (w - 90)  # Russia: white-blue-red tricolour
    fill_rect(fx + 3, y + 18, 52, 9, BLUE)
    fill_rect(fx + 3, y + 27, 52, 9, RED)
    # long summit table
    ty = y + h - 38
    fill_rect(x + 18, ty, w - 36, 16, (120, 84, 52))
    fill_rect(x + 18, ty + 16, w - 36, 6, (92, 62, 38))
    # seated leaders: head + shoulders along the table
    for i in range(5):
        cx = x + 52 + i * (w - 104) // 4
        disc(cx, ty - 16, 10, (216, 178, 140))
        poly([(cx - 15, ty), (cx + 15, ty), (cx + 9, ty - 12),
              (cx - 9, ty - 12)], (44, 48, 66))
        fill_rect(cx - 2, ty - 12, 4, 8, RED if i % 2 == 0 else BLUE)


def scene_radar(x, y, w, h):
    """A radome in the desert, drones coming in."""
    fill_rect(x, y, w, h // 2, (240, 214, 150))
    fill_rect(x, y + h // 2, w, h - h // 2, SAND)
    disc(x + w - 44, y + 26, 16, FIRE_CORE)  # sun
    # radome on its base
    cx, base = x + w // 3, y + h - 16
    fill_rect(cx - 44, base - 10, 88, 10, (150, 144, 132))
    half_disc_up(cx, base - 10, 42, WHITE)
    stroke(cx - 42, base - 10, cx + 42, base - 10, 3, SMOKE)
    # antenna mast beside it
    mx = cx + 74
    stroke(mx, base, mx, base - 62, 4, INK)
    stroke(mx - 18, base - 62, mx + 18, base - 62, 4, INK)
    stroke(mx, base - 62, mx + 26, base - 42, 3, INK)
    # three drones sweeping in from the right
    for dx, dy, s in ((188, 16, 1), (238, 40, 1), (292, 52, 0)):
        cx2, cy2 = x + dx, y + dy
        if s:
            stroke(cx2 - 14, cy2 - 10, cx2 + 14, cy2 + 10, 4, INK)
            stroke(cx2 - 14, cy2 + 10, cx2 - 14, cy2 - 10, 4, INK)
            disc(cx2 - 15, cy2 - 11, 5, INK)
            disc(cx2 + 15, cy2 - 11, 5, INK)
            disc(cx2 - 15, cy2 + 11, 5, INK)
            disc(cx2 + 15, cy2 + 11, 5, INK)
            disc(cx2, cy2, 5, RED)
        else:
            stroke(cx2 - 9, cy2 - 6, cx2 + 9, cy2 + 6, 3, INK)
            stroke(cx2 - 9, cy2 + 6, cx2 + 9, cy2 - 6, 3, INK)
            disc(cx2, cy2, 3, RED)


def scene_icj(x, y, w, h):
    """The Peace Palace courtroom: columns, bench and scales of justice."""
    fill_rect(x, y, w, h, (226, 220, 200))
    # courthouse facade: pediment and columns
    poly([(x + 20, y + 34), (x + w - 20, y + 34), (x + w // 2, y + 8)],
         (180, 60, 50))
    for i in range(4):
        cx = x + 40 + i * (w - 80) // 3
        fill_rect(cx - 7, y + 36, 14, 46, WHITE)
        fill_rect(cx - 9, y + 34, 18, 4, INK)
        fill_rect(cx - 9, y + 82, 18, 4, INK)
    # the scales of justice, centred below the columns
    cx, cy = x + w // 2, y + h - 30
    stroke(cx, cy - 34, cx, cy, 4, GOLD)
    stroke(cx - 26, cy - 34, cx + 26, cy - 34, 4, GOLD)
    disc(cx, cy - 38, 5, GOLD)
    for dx in (-26, 26):
        stroke(cx + dx, cy - 34, cx + dx, cy - 16, 3, GOLD)
        poly([(cx + dx - 12, cy - 16), (cx + dx + 12, cy - 16),
              (cx + dx, cy - 2)], GOLD)
    fill_rect(cx - 16, cy, 32, 4, GOLD)
    fill_rect(cx - 22, cy + 4, 44, 4, GOLD)


def scene_voyager(x, y, w, h):
    """Voyager 1 in deep space, one light-day from Earth."""
    fill_rect(x, y, w, h, SPACE)
    # starfield: fixed pattern of dots
    for i in range(60):
        sx = x + (i * 67) % (w - 8) + 4
        sy = y + (i * 41) % (h - 8) + 4
        r = 1 + (i % 3 == 0)
        disc(sx, sy, r, WHITE if i % 4 else GOLD)
    # a pale distant sun at top left
    disc(x + 30, y + 24, 10, (255, 240, 180))
    # the probe: bus, dish and long boom, angled across the frame
    cx, cy = x + w // 2, y + h // 2
    stroke(cx - 40, cy + 30, cx + 40, cy - 30, 6, (200, 200, 205))
    fill_rect(cx - 12, cy - 8, 24, 16, (160, 164, 170))
    # the big dish
    poly([(cx + 34, cy - 34), (cx + 52, cy - 16), (cx + 18, cy - 2)],
         (220, 222, 226))
    stroke(cx + 34, cy - 34, cx + 52, cy - 16, 3, SMOKE_LT)
    # radio waves arcing out from the dish
    for r in (58, 70, 82):
        for a in range(-50, 51, 10):
            ang = math.radians(a - 45)
            px = cx + 40 + int(r * math.cos(ang))
            py = cy - 24 + int(r * math.sin(ang))
            disc(px, py, 2, VICE_TEAL)
    # a tiny blue Earth far below
    disc(x + w - 40, y + h - 22, 9, (60, 120, 220))
    disc(x + w - 43, y + h - 25, 3, (120, 200, 120))


# ------------------------------------------------------------------ layout
def panel(x, y, w, h, scene, head_lines, detail_lines, accent):
    global CLIP
    fill_rect(x, y, w, h, PAPER)
    frame(x, y, w, h, INK, 3)
    fill_rect(x, y, w, 8, accent)
    CLIP = (x + 3, y + 3, x + w - 3, y + h - 3)
    scene(x + 10, y + 14, w - 20, 84)
    CLIP = None
    ty = y + 106
    for ln in head_lines:
        text_c(ln, x + w // 2, ty, 3, INK, bold=True)
        ty += 25
    ty += 2
    for ln in detail_lines:
        text_c(ln, x + w // 2, ty, 2, (70, 64, 54))
        ty += 17


def compose():
    global CLIP
    fill_rect(0, 0, W, H, PAPER)

    # ---- masthead
    text_c("WORLD NEWS SUMMARY", W // 2, 18, 3, FAINT)
    text_c("THURSDAY", W // 2, 46, 7, INK, bold=True)
    text_c("19 NOVEMBER 2026", W // 2, 104, 9, RED, bold=True)
    fill_rect(28, 176, W - 56, 5, RULE)
    fill_rect(28, 186, W - 56, 2, RULE)

    # ---- hero: GTA VI launches worldwide
    hx, hy, hw, hh = 28, 196, W - 56, 284
    frame(hx, hy, hw, hh, INK, 3)
    CLIP = (hx + 3, hy + 3, hx + hw - 3, hy + hh - 3)
    scene_gta(hx + 8, hy + 8, hw - 16, 150)
    CLIP = None
    text_c("GTA VI IS FINALLY HERE", W // 2, hy + 168, 4, INK, bold=True)
    text_c("VICE CITY OPENS WORLDWIDE AFTER 13 YEARS;", W // 2, hy + 206, 3,
           (70, 64, 54))
    text_c("99 ON METACRITIC, $1.5BN IN PREORDERS", W // 2, hy + 236, 3,
           (70, 64, 54))

    # ---- four panels, two by two
    pw = (W - 56 - 14) // 2
    ph = 210
    py1 = 492
    py2 = py1 + ph + 10
    panel(28, py1, pw, ph, scene_summit,
          ["TRUMP, XI AND PUTIN", "MEET IN SHENZHEN"],
          ["FIRST-EVER TRILATERAL", "AT THE APEC SUMMIT"], BLUE)
    panel(28 + pw + 14, py1, pw, ph, scene_radar,
          ["US AND IRAN EXCHANGE", "FIRE AGAIN"],
          ["IRAN WIDENS ITS ATTACKS", "ON GULF STATES"], RED)
    panel(28, py2, pw, ph, scene_icj,
          ["WORLD COURT RULES", "ON MYANMAR"],
          ["GENOCIDE CASE OVER THE", "ROHINGYA DECIDED"], GOLD)
    panel(28 + pw + 14, py2, pw, ph, scene_voyager,
          ["VOYAGER 1 REACHES", "ONE LIGHT-DAY"],
          ["ALMOST 50 YEARS AFTER", "LAUNCH FROM EARTH"], SPACE_LT)

    # ---- ticker
    ty = py2 + ph + 12
    fill_rect(28, ty, W - 56, H - ty - 12, TICKER_BG)
    text_c("EU PLANS €45BN LOAN TO FUND UKRAINE", W // 2, ty + 8, 3,
           TICKER_FG, bold=True)
    text_c("CANADA ADJUSTS ITS CHINA TIES, CARNEY SAYS",
           W // 2, ty + 36, 3, TICKER_FG)
    text_c("AUSTRALIA SANCTIONS ISRAELI SETTLERS", W // 2, ty + 62, 2,
           (196, 188, 168))


def png_bytes():
    raw = bytearray()
    row = W * 3
    for y in range(H):
        raw.append(0)
        raw += FB[y * row:(y + 1) * row]

    def chunk(tag, data):
        out = struct.pack(">I", len(data)) + tag + data
        out += struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
        return out

    ihdr = struct.pack(">IIBBBBB", W, H, 8, 2, 0, 0, 0)
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(bytes(raw), 9))
            + chunk(b"IEND", b""))


def main():
    compose()
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, "entry.png")
    with open(path, "wb") as fh:
        fh.write(png_bytes())
    print("wrote", path)


if __name__ == "__main__":
    main()
