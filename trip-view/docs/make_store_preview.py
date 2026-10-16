#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
'''Compose the store preview (1600×1000, 1.6:1).

The store shows one picture: in its grid at about 165×104 dp, and on the widget's page as wide as
the panel and at most 320 dp tall. So the picture is a single hero at 1.6:1 that still reads when
small: Neon Ramen full bleed at 2× (whole pixels, crisp) and the TRIP VIEW title on a chamfered glass
panel. Nothing else: no strip of other scenes.

  python make_store_preview.py <full-screen ramen frame.png> <screen-box.json> <out.png>

The frame is a launcher render of the full-screen page with the controls hidden (what "Set wallpaper"
exports); screen-box.json is ~/.cache/pixbg/screen-box.json.
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
    '5': ['#####', '#....', '####.', '....#', '....#', '#...#', '.###.'],
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


def main(frame, box_json, out):
    box = json.load(open(box_json))['box']
    scene = Image.open(frame).convert('RGB').crop(tuple(box))
    # Shader cells in the frame are 4 px; take an 800×500 window on the stall, aligned to the grid, at 2×.
    sw, sh = scene.size
    # The stall and its neon sign sit right of center; the sky in the top left holds the title.
    x0 = max(0, (sw - 800) // 2 - 84) // 4 * 4
    y0 = int(sh * 0.66 - 214) // 4 * 4
    img = scene.crop((x0, y0, x0 + 800, y0 + 500)).resize((W, H), Image.NEAREST)
    d = ImageDraw.Draw(img, 'RGBA')

    # Title panel, top left, above the lantern and left of the neon sign
    title = 'TRIP VIEW'
    tpx = 11
    pw = text_width(title, tpx) + 2 * 44
    ph = 7 * tpx + 2 * 34
    x, y = 36, 36
    chamfer_panel(d, x, y, x + pw, y + ph, 6, GLASS + (232,), PINK + (255,))
    pixel_text(d, title, x + 44, y + 34, tpx, WHITE, shadow=PINK)

    img.quantize(colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE).save(out, optimize=True)
    print(out, os.path.getsize(out) // 1024, 'KB')


if __name__ == '__main__':
    main(*sys.argv[1:])
