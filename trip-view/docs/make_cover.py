#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
'''Make store/cover.png: the tile before the local tools exist, and so what the store's previews show.

Neon Ramen in the default palette (3) with TRIP VIEW on its neon sign, cut to the 4×2 tile
(692×360). It is kept at 4 px per shader cell: the launcher scales images smoothly, so a smaller
picture would blur, and a larger one costs widget bytes (this is about 6 KB).

  python make_cover.py <full-screen ramen frame.png> <screen-box.json> <out.png>

The frame is a launcher render of the full-screen page in export mode with palette 3 (zone 2);
screen-box.json is ~/.cache/pixbg/screen-box.json.
'''
from collections import Counter
import io
import json
import os
import sys
from PIL import Image

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from make_store_preview import FONT

SIGN = (55, 51, 119, 65)      # the sign's frame, in cells of the window below
TOP = 44                      # first cell row of the tile: the sign with a little sky above


def main(frame, box_json, out):
    box = json.load(open(box_json))['box']
    scene = Image.open(frame).convert('RGB').crop(tuple(box))
    sw, sh = scene.size
    # The stall's window in the frame (its cells are about 4 px), sampled once per cell.
    ww, wh = 692, 736
    x0 = max(0, (sw - ww) // 2) // 4 * 4
    y0 = int(sh * 0.66 - 300) // 4 * 4
    cell = scene.crop((x0, y0, x0 + ww, y0 + wh)).resize((ww // 4, wh // 4), Image.NEAREST)
    px = cell.load()

    # TRIP VIEW in the sign's own colours, replacing its glyphs
    x1, y1, x2, y2 = SIGN
    inside = [(x, y) for x in range(x1 + 2, x2 - 1) for y in range(y1 + 2, y2 - 1)]
    counts = Counter(px[p] for p in inside)
    ground = counts.most_common(1)[0][0]
    ink = max((c for c in counts if c != ground), key=lambda c: counts[c] * (max(c) - min(c) + 1))
    for x in range(x1 + 1, x2):
        for y in range(y1 + 1, y2):
            px[x, y] = ground
    text = 'TRIP VIEW'
    tx = x1 + 1 + (x2 - x1 - 1 - (len(text) * 6 - 1)) // 2
    ty = y1 + 1 + (y2 - y1 - 1 - 7) // 2
    for k, ch in enumerate(text):
        for r, row in enumerate(FONT[ch]):
            for c, v in enumerate(row):
                if v == '#':
                    px[tx + k * 6 + c, ty + r] = ink

    tile = cell.crop((0, TOP, cell.width, TOP + 90)).resize((cell.width * 4, 90 * 4), Image.NEAREST)
    b = io.BytesIO()
    tile.quantize(256, method=Image.Quantize.FASTOCTREE, dither=Image.Dither.NONE).save(b, format='PNG', optimize=True)
    open(out, 'wb').write(b.getvalue())
    print(out, len(b.getvalue()), 'bytes')


if __name__ == '__main__':
    main(*sys.argv[1:])
