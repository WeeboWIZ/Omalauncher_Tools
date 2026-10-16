#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
'''Compose the store preview (1600×1000, 1.6:1).

The store shows one picture: in its grid at about 165×104 dp, and on the widget's page as wide as
the panel and at most 320 dp tall. So the picture is a single hero at 1.6:1 that still reads when
small: Neon Ramen full bleed at 2× (whole pixels, crisp), a pixel title on a chamfered glass panel,
and a strip of the other six scenes.

  python make_store_preview.py <full-screen ramen frame.png> <screen-box.json> <scene-thumbs dir> <out.png>

The frame is a launcher render of the full-screen page with the controls hidden (what "Set wallpaper"
exports); screen-box.json is ~/.cache/pixbg/screen-box.json; the thumbs are ~/.cache/pixbg/scene-thumbs.
'''
import json
import os
import sys
from PIL import Image, ImageDraw

W, H = 1600, 1000
INK = (6, 8, 12)
GLASS = (12, 17, 26)
PINK = (255, 79, 168)       # Neon Ramen's sign, first palette
WHITE = (238, 243, 250)
SOFT = (180, 190, 210)

# 5×7 pixel letters for the title and subtitle
FONT = {
    'A': ['.###.', '#...#', '#...#', '#####', '#...#', '#...#', '#...#'],
    'C': ['.####', '#....', '#....', '#....', '#....', '#....', '.####'],
    'D': ['####.', '#...#', '#...#', '#...#', '#...#', '#...#', '####.'],
    'E': ['#####', '#....', '#....', '####.', '#....', '#....', '#####'],
    'G': ['.####', '#....', '#....', '#.###', '#...#', '#...#', '.###.'],
    'I': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '#####'],
    'M': ['#...#', '##.##', '#.#.#', '#.#.#', '#...#', '#...#', '#...#'],
    'N': ['#...#', '##..#', '#.#.#', '#..##', '#...#', '#...#', '#...#'],
    'O': ['.###.', '#...#', '#...#', '#...#', '#...#', '#...#', '.###.'],
    'P': ['####.', '#...#', '#...#', '####.', '#....', '#....', '#....'],
    'R': ['####.', '#...#', '#...#', '####.', '#.#..', '#..#.', '#...#'],
    'S': ['.####', '#....', '#....', '.###.', '....#', '....#', '####.'],
    'T': ['#####', '..#..', '..#..', '..#..', '..#..', '..#..', '..#..'],
    'V': ['#...#', '#...#', '#...#', '#...#', '#...#', '.#.#.', '..#..'],
    'W': ['#...#', '#...#', '#...#', '#.#.#', '#.#.#', '##.##', '#...#'],
    '7': ['#####', '....#', '...#.', '..#..', '.#...', '.#...', '.#...'],
    '+': ['.....', '..#..', '..#..', '#####', '..#..', '..#..', '.....'],
    ' ': ['.....'] * 7,
}


def text_width(s, px):
    return len(s) * 6 * px - px


def pixel_text(d, s, x, y, px, color, shadow=None):
    for k, ch in enumerate(s):
        for r, row in enumerate(FONT[ch]):
            for c, v in enumerate(row):
                if v != '#':
                    continue
                X, Y = x + (k * 6 + c) * px, y + r * px
                if shadow:
                    d.rectangle([X + px // 2, Y + px // 2, X + px + px // 2 - 1, Y + px + px // 2 - 1], fill=shadow)
                d.rectangle([X, Y, X + px - 1, Y + px - 1], fill=color)


def chamfer_panel(d, x0, y0, x1, y1, u, fill, edge):
    '''PixelBtn's two-step chamfer: an outline, then the face inset by one step.'''
    for (a, b) in ((2 * u, 0), (u, u), (0, 2 * u)):
        d.rectangle([x0 + a, y0 + b, x1 - a, y1 - b], fill=edge)
    for (a, b) in ((3 * u, u), (2 * u, 2 * u), (u, 3 * u)):
        d.rectangle([x0 + a, y0 + b, x1 - a, y1 - b], fill=fill)


def main(frame, box_json, thumbs, out):
    box = json.load(open(box_json))['box']
    scene = Image.open(frame).convert('RGB').crop(tuple(box))
    # Shader cells in the frame are 4 px; take an 800×500 window on the stall, aligned to the grid, at 2×.
    sw, sh = scene.size
    # The stall sits right of center and above the strip, clear of the title in the top left.
    x0 = max(0, (sw - 800) // 2 - 84) // 4 * 4
    y0 = int(sh * 0.66 - 222) // 4 * 4
    img = scene.crop((x0, y0, x0 + 800, y0 + 500)).resize((W, H), Image.NEAREST)
    d = ImageDraw.Draw(img, 'RGBA')

    # Title panel, top left
    title, sub = 'TRIP VIEW', '7 ANIMATED SCENES + AI GENERATOR'
    tpx, spx = 11, 4
    pw = max(text_width(title, tpx), text_width(sub, spx)) + 2 * 44
    chamfer_panel(d, 36, 36, 36 + pw, 36 + 7 * tpx + 7 * spx + 3 * 34, 6, GLASS + (232,), PINK + (255,))
    pixel_text(d, title, 36 + 44, 36 + 34, tpx, WHITE, shadow=PINK)
    pixel_text(d, sub, 36 + 44, 36 + 34 + 7 * tpx + 30, spx, SOFT)

    # The other six scenes in a strip along the bottom
    names = ['60-kaiju', '30-star', '10-void', '40-forest', '50-zion', '20-cyber']
    tw, th, gap = 236, 170, 20
    sx = (W - (6 * tw + 5 * gap)) // 2
    band_y = H - th - 2 * 26
    d.rectangle([0, band_y, W, H], fill=GLASS + (215,))
    d.rectangle([0, band_y, W, band_y + 3], fill=PINK + (255,))
    for i, n in enumerate(names):
        t = Image.open(os.path.join(thumbs, n + '.png')).convert('RGB')
        t = t.crop((0, 0, t.width, int(t.width * th / tw))).resize((tw, th), Image.LANCZOS)
        x, y = sx + i * (tw + gap), band_y + 26
        d.rectangle([x - 4, y - 4, x + tw + 3, y + th + 3], fill=INK)
        img.paste(t, (x, y))
    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)
    print(out, os.path.getsize(out) // 1024, 'KB')


if __name__ == '__main__':
    main(*sys.argv[1:])
