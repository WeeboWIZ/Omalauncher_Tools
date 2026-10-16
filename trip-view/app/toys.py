# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
"""KAIJU TOKYO 的軟膠玩具：照 UFOPUMP（src/systems/backdrops/KaijuTokyo.ts）的 Toy 畫法移植，
離線畫成像素圖，再轉成小工具 Canvas sprite() 用的字母圖（每隻 ≤52 色，'.' 透明）。

  python3 toys.py <輸出.json> [預覽.png]   （輸出的是 actors.json 的 "art"）

座標以玩具的中線為 x＝0，左右對稱的部位鏡射後一格不差，整隻可以等比放大。
"""
import json, math, sys
from PIL import Image


def jr(x):  # JavaScript 的 Math.round（.5 往正無限大）
    return math.floor(x + 0.5)


def sign(x):
    return (x > 0) - (x < 0)


def hexrgb(c):
    return [int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)]


def mix(a, b, t):
    return [a[i] + (b[i] - a[i]) * t for i in range(3)]


def rgb_t(c):
    return tuple(jr(v) for v in c)


SHADE, GLOW, WHITE = [30, 18, 70], [255, 246, 216], [255, 255, 255]
SILVER, STEEL, INK = "#a9c0d4", "#5c7690", "#120c26"
SIDES = (-1, 1)


class Ctx:
    def __init__(self, w, h):
        self.im = Image.new("RGBA", (w, h), (0, 0, 0, 0))
        self.px = self.im.load()
        self.w, self.h = w, h
        self.fill = (0, 0, 0)

    def rect(self, x, y, w, h):
        for yy in range(max(0, int(y)), min(self.h, int(y + h))):
            for xx in range(max(0, int(x)), min(self.w, int(x + w))):
                self.px[xx, yy] = self.fill + (255,)


class Toy:
    def __init__(self, ctx, cx, oy, s):
        self.ctx, self.cx, self.oy, self.s = ctx, cx, oy, s
        self.base = self.dark = self.light = self.shine = (0, 0, 0)

    def X(self, x):
        return self.cx + sign(x) * jr(abs(x) * self.s)

    def Y(self, y):
        return jr(self.oy + y * self.s)

    def L(self, v):
        return max(1, jr(v * self.s))

    def c(self, col):
        b = hexrgb(col)
        self.base, self.dark = tuple(b), rgb_t(mix(b, SHADE, 0.34))
        self.light, self.shine = rgb_t(mix(b, GLOW, 0.4)), rgb_t(mix(b, WHITE, 0.82))
        return self

    def dot(self, px, py, R, style):
        self.ctx.fill = style
        for dy in range(-R, R + 1):
            half = math.floor(math.sqrt(max(0, R * R - dy * dy)) + 0.4)
            self.ctx.rect(px - half, py + dy, half * 2 + 1, 1)

    def o(self, x, y, rx, ry, mode=1):
        """橢圓。mode 0＝平塗，1＝帶明暗，2＝再加一顆高光"""
        cx, cy, RX, RY = self.X(x), self.Y(y), self.L(rx), self.L(ry)
        flat = mode == 0 or RX < 3 or RY < 3
        for dy in range(-RY, RY + 1):
            half = math.floor(RX * math.sqrt(max(0, 1 - (dy * dy) / (RY * RY))) + 0.4)
            if flat:
                self.ctx.fill = self.base
                self.ctx.rect(cx - half, cy + dy, half * 2 + 1, 1)
                continue
            for dx in range(-half, half + 1):
                nx, ny = dx / RX, dy / RY
                d, e = nx * 0.5 + ny * 0.8, nx * nx + ny * ny
                hi = mode == 2 and RX >= 6 and (nx + 0.4) ** 2 + (ny + 0.46) ** 2 < 0.03
                self.ctx.fill = self.shine if hi else self.dark if d > 0.52 or (e > 0.74 and d > 0.2) else self.light if d < -0.5 and e < 0.86 else self.base
                self.ctx.rect(cx + dx, cy + dy, 1, 1)
        return self

    def r(self, x, y, w, h, m=1):
        a, W = jr(x * self.s), self.L(w)
        self.ctx.fill = self.base
        self.ctx.rect(self.cx + a if m > 0 else self.cx - a - W + 1, self.Y(y), W, self.L(h))
        return self

    def leaf(self, x, y, w, dx, dy, length):
        n, px, py = max(2, jr(length * self.s)), self.X(x), self.Y(y)
        for pas in (0, 1):
            for i in range(n + 1):
                u = i / n
                R = jr(((w * self.s) / 2) * math.pow(1 - u, 0.8) - pas * 0.6)
                if R < 0:
                    continue
                self.dot(px + jr(dx * length * self.s * u) - pas, py + jr(dy * length * self.s * u) - pas, R, self.base if pas else self.dark)
        return self

    def limb(self, x0, y0, x1, y1, r):
        R, ax, ay, bx, by = self.L(r), self.X(x0), self.Y(y0), self.X(x1), self.Y(y1)
        n = max(1, math.ceil(math.hypot(bx - ax, by - ay)))
        for pas in (0, 1, 2):
            for i in range(n + 1):
                px, py = jr(ax + (bx - ax) * i / n), jr(ay + (by - ay) * i / n)
                if pas == 0:
                    self.dot(px, py, R, self.dark)
                elif pas == 1:
                    self.dot(px - 1, py - 1, R - 1, self.base)
                elif R >= 4:
                    self.dot(px - 2, py - 2, 0, self.light)
        return self


def draw_dino(t, roar):
    G, GD, LM, LD = "#2a9c6c", "#17684a", "#9ad84a", "#5a9a2a"
    t.c(G).limb(11, 47, 23, 50, 3.6).c(LM).leaf(23, 50, 5, 0.8, -0.7, 6)
    for m in SIDES:
        t.c(SILVER).leaf(m * 11, 17, 9, m * 0.85, -0.55, 11).leaf(m * 14, 26, 7, m, -0.25, 7)
        t.c(G).o(m * 10, 52, 7, 4.6)
        t.c(SILVER)
        for k in (-1, 0, 1):
            t.leaf(m * 10 + k * 4.2, 54.5, 3.4, k * 0.25, 1, 3.4)
        t.c(LM).leaf(m * 14, 44.5, 7, m, 0.2, 9)
    t.c(G).o(0, 40, 16.5, 14, 2)
    t.c(SILVER).o(0, 44, 10.5, 9.6)
    t.c(STEEL)
    y = 37.6
    while y <= 51:
        x = -7.5
        while x <= 7.5:
            if (jr(x / 2.7) + jr(y / 2.7)) & 1 and (x * x) / 90 + ((y - 44) * (y - 44)) / 72 < 1:
                t.r(x, y, 0.8, 0.8)
            x += 2.7
        y += 2.7
    for m in SIDES:
        t.c(LM).leaf(m * 14, 30, 6, m * 0.9, -0.45, 8).o(m * 6.3, 31.4, 6.3, 4.3, 2)
    t.c(LD).r(-0.4, 27.8, 0.9, 7.4)
    for m in SIDES:
        hx, hy = (m * 21, 24) if roar else (m * 17, 39)
        t.c(G).limb(m * 15.5, 31.5, hx, hy, 3.4).c(SILVER).o(hx, hy, 3.3, 3.1, 2)
        for k in (-1, 0, 1):
            if roar:
                t.leaf(hx + k * 2.2, hy - 2, 2.2, k * 0.3, -1, 3.4)
            else:
                t.leaf(hx + k * 2.1, hy + 2, 2.2, k * 0.25 - m * 0.3, 1, 3.4)
    t.c(SILVER).leaf(0, 6.5, 6.4, 0, -1, 7)
    for m in SIDES:
        t.leaf(m * 5.4, 7.6, 6, m * 0.4, -1, 6).leaf(m * 10, 10.5, 6, m * 0.75, -0.75, 6)
    if roar:
        t.c(GD).o(0, 25.5, 11, 5.2)
    t.c(G).o(0, 14, 13, 9.6, 2).o(0, 20.4, 14, 6.4)
    t.c(SILVER).o(0, 8.6, 6.4, 3.6).o(0, 12.6, 3.4, 3.4).o(0, 16.4, 2.4, 2.6)
    t.c(STEEL).r(-0.4, 6.4, 0.8, 9).r(-3.4, 8.4, 0.8, 2.4).r(2.6, 8.4, 0.8, 2.4)
    for m in SIDES:
        t.c("#ffd83a").o(m * 7, 14.2, 3.4, 2.5, 0).c(INK).o(m * 6.2, 14.5, 1.2, 1.5, 0).c("#ffffff").r(6.4 if m > 0 else 5.2, 13.2, 0.8, 0.8, m)
        t.c(GD)
        for i in range(10):
            t.r(2 + i, 11 - i * 0.34, 1.2, 2.3, m)
        t.r(1.8, 17.4, 1.1, 1.1, m)
    if roar:
        t.c("#5a0c24").o(0, 23.4, 9.4, 4.8, 0).c("#f0587a").o(0, 26, 4.6, 2)
        t.c("#ffffff")
        for k in range(-3, 4):
            t.r(k * 2.3 - 0.6, 19, 1.3, 2.2)
            if k % 2:
                t.r(k * 2.3 - 0.6, 26.4, 1.3, 1.6)
        for m in SIDES:
            t.r(6.6, 19, 1.7, 3.8, m)
    else:
        t.c("#0c2a22").r(-10.4, 21.6, 20.8, 1.3)
        for m in SIDES:
            t.r(10, 20.6, 1.3, 1.3, m)
        t.c("#ffffff")
        for k in range(-2, 3):
            t.r(k * 2.3 - 0.6, 22.8, 1.3, 1.4 if k & 1 else 2.1)
        for m in SIDES:
            t.r(6.4, 22.8, 1.7, 3.6, m)


def draw_kong(t, pose):
    B, BD, GD, GK, K = "#2c52bc", "#1b3488", "#e2b232", "#946a14", "#141a3a"
    for m in SIDES:
        up = pose == 2 or (m < 0 if pose == 0 else m > 0)
        fx, fy = m * 22, 13 if up else 31
        t.c(K).o(m * 7, 46.6, 6.6, 3.3)
        t.c(BD).limb(m * 9, 26.5, fx - m, fy, 4.6)
        t.c(GD)
        for k in (-1, 0, 1):
            t.o(fx + k * 3, fy - 3.6, 2, 1.9)
        t.o(fx, fy, 5.3, 5, 2).c(GK).r(fx - 3.2, fy + 1.4, 6.4, 0.8).r(fx - 0.4, fy - 2.6, 0.8, 4)
        t.c(B).o(m * 10, 15.4, 2.5, 3.3)
    t.c(B).o(0, 34.5, 12.6, 12, 2)
    t.c(BD)
    for i in range(11):
        t.r(-10.5 + i * 2.1, 28 + ((i * 7) % 13), 0.8, 3.2)
    for m in SIDES:
        t.c(GD).o(m * 5.2, 30.2, 4.3, 3.3, 2)
    t.c(GD).o(0, 39.6, 4.9, 4.3, 2).c(GK).r(-0.4, 39.4, 0.9, 0.9)
    t.c(GD).leaf(0, 3, 5, 0, -1, 3.4).c(B).o(0, 8, 6.6, 6.4).c(GD).o(0, 3.6, 3.7, 3.1)
    t.c(B).o(0, 15.6, 9.8, 9.4, 2)
    t.c(K).o(0, 13.6, 7.7, 3.9, 0)
    for m in SIDES:
        t.c("#ffe84a").o(m * 3.9, 13.7, 2.7, 2.7, 0).c(K).o(m * 3.9, 13.7, 1.3, 1.3, 0)
        t.c(BD)
        for i in range(7):
            t.r(1 + i, 10.6 - i * 0.3, 1.2, 1.5, m)
    t.c("#4f7ee6").o(0, 21.2, 8.7, 5.2).c(K).o(0, 17.8, 2.7, 1.4, 0)
    t.c(K).r(-6.6, 20.4, 13.2, 3.8).c("#ffffff")
    for k in range(-2, 3):
        t.r(k * 2.3 - 0.8, 21, 1.7, 1.5)
    for m in SIDES:
        t.r(4.9, 21, 1.6, 3.1, m)


def draw_hero(t, pose):
    Y, YD, V, S, R = "#ffb83a", "#e08a24", "#17a088", "#d4e0ec", "#e83a2a"

    def star(x, y, w, ln):
        t.leaf(x, y, w, 0, -1, ln).leaf(x, y, w, 0, 1, ln).leaf(x, y, w, -1, 0, ln).leaf(x, y, w, 1, 0, ln)

    for m in SIDES:
        t.c(Y).o(m * 4.8, 38, 4.6, 5.4).c(S).o(m * 5.4, 43.4, 5.2, 2.8).c(STEEL).r(1.2, 40.6, 7.4, 0.8, m)
    for m in SIDES:
        t.c(Y).leaf(m * 6.5, 23.6, 6.4, m * 0.95, -0.35, 6)
    t.c(Y).o(0, 29.5, 9, 9, 2)
    t.c(YD).r(-8.4, 33, 16.8, 2.2).c(S).r(-2.2, 32.4, 4.4, 3.4).c(STEEL).r(-1, 33.4, 2, 1.2)
    t.c(R).r(-0.4, 29.4, 0.9, 2.2)
    for deg, ln in ((0, 6.4), (-32, 5.6), (32, 5.6), (-62, 4.4), (62, 4.4), (-98, 2.8), (98, 2.8)):
        a = deg * math.pi / 180
        t.leaf(0, 29.6, 2.4, math.sin(a), -math.cos(a), ln)
    t.c(Y).leaf(0, 5, 5.6, 0, -1, 6).o(0, 12.5, 11, 10, 2)
    t.c("#0b4a44").o(0, 12.4, 9.8, 4.2, 0)
    for m in SIDES:
        t.c(V).o(m * 4.8, 12.4, 4.5, 3.2).c("#9ff6dc").r(2.4, 10.6, 3, 0.8, m)
    t.c(S)
    star(0, 8.6, 2.8, 3.8)
    t.c("#7a3a10").o(0, 18.4, 3.7, 1.9, 0).c("#ffffff").r(-2.7, 17.4, 5.4, 1.1)

    def hip(m):
        t.c(Y).limb(m * 8.6, 25, m * 10.6, 30, 3).c(S).o(m * 11, 32, 3.2, 3.2, 2)

    if pose == 0:
        hip(-1)
        t.c(Y).limb(8.6, 24.5, 11.2, 9, 3).c(S).o(11.6, 5.2, 3.7, 3.7, 2)
    elif pose == 1:
        t.c(Y).limb(-8.6, 26, 4, 26, 2.6).c(S).o(-10.6, 26, 3.2, 3.2, 2)
        t.c(Y).limb(8, 29, 8, 21, 2.6).c(S).o(8, 18.4, 3.3, 3.3, 2)
    else:
        hip(-1)
        t.c(Y).limb(8.6, 26, 12.4, 25, 3).c(S).o(14.6, 24.4, 3.6, 3.6, 2).limb(14.2, 21, 14.2, 18.4, 1.3)


def draw_duck(t, flap):
    O, OL, OD, P = "#f0582a", "#ff9464", "#c43c1a", "#f8dce0"
    for m in SIDES:
        for i in range(4):
            t.c(OL if i & 1 else O).leaf(m * 12, 17 + i * 3.2, 8, m, (-0.8 + i * 0.3) if flap else (0.05 + i * 0.28), 14)
    for i in range(14):
        a = (i / 14) * math.pi * 2 + 0.22
        t.c(OD if i & 1 else O).leaf(math.cos(a) * 12, 21.5 + math.sin(a) * 12, 8.4, math.cos(a), math.sin(a), 8)
    for m in SIDES:
        t.c(OD).o(m * 4.2, 40, 3.4, 4)
        t.c(SILVER)
        for k in (-1, 0, 1):
            t.leaf(m * 4.2 + k * 2.2, 43, 2.4, k * 0.35, 1, 3)
    t.c(O).o(0, 22, 15.5, 15)
    for j in range(2):
        for i in range(6 - j):
            a = math.pi * (0.14 + ((i + j * 0.5) / 5) * 0.72)
            t.c("#f86c3c" if j else OD).leaf(math.cos(a) * (11 - j * 4), 24 + math.sin(a) * (9 - j * 2), 5.6, math.cos(a) * 0.5, 1, 5)
    t.c(P).o(0, 18.5, 10.8, 10)
    t.c(O)
    for i in range(-3, 4):
        if abs(i) > 1:
            t.leaf(i * 2.8, 8.6 + abs(i) * 0.8, 3.6, i * 0.12, 1, 3)
    for x, y in ((0, 11.6), (-5.8, 17.6), (5.8, 17.6)):
        t.c("#a8707e").o(x, y, 4.2, 3.6, 0).c("#ffe14a").o(x, y, 3.6, 3, 0).c(INK).o(x, y + 0.7, 1.4, 1.5, 0)
        t.c("#ecc0ca").r(x - 3.8, y - 3.4, 7.6, 2.2).c("#a8707e").r(x - 3.8, y - 1.4, 7.6, 0.7)
    t.c("#a82c10").o(0, 28.2, 8, 2.8, 0).c("#e8541c").o(0, 27.8, 7.2, 2.4, 0)
    t.c("#a82c10").o(0, 25, 11.2, 4.2, 0).c("#ff8c3c").o(0, 24.8, 10.4, 3.6, 2)
    for m in SIDES:
        t.c("#a82c10").r(1.6, 23.2, 1, 1, m)
        t.c(SILVER).o(m * 12.6, 31, 3, 3.3, 2)
        for k in (-1, 0, 1):
            t.leaf(m * 12.6 + k * 1.8, 33, 2, k * 0.2, 1, 3)


def outline(im):
    """透明格子旁邊有實心格就描一格深色的邊：先看右、下（受光面的邊亮一點），再看左、上"""
    w, h = im.size
    src = im.copy().load()
    px = im.load()
    ink = hexrgb(INK)
    for y in range(h):
        for x in range(w):
            if src[x, y][3]:
                continue
            for dx, dy in ((1, 0), (0, 1), (-1, 0), (0, -1)):
                nx, ny = x + dx, y + dy
                if 0 <= nx < w and 0 <= ny < h and src[nx, ny][3]:
                    c = rgb_t(mix(list(src[nx, ny][:3]), ink, 0.62 if dx + dy > 0 else 0.8))
                    px[x, y] = c + (255,)
                    break
    return im


# 影格尺寸與放大倍率：UFOPUMP 的一半，顯示時一個美術像素佔兩格（CELL），畫面上一樣大。
# 小工具的 Canvas 一格畫面最多 2000 個 sprite 段，全尺寸的恐龍一隻就要 1500 段；減半後約 700。
HALF = 0.5
CELL = 2
TOYS = {name: (int(fw * HALF) + 4, int(fh * HALF) + 4, s * HALF, n, fn) for name, (fw, fh, s, n, fn) in {
    "dino": (90, 94, 1.5, 2, draw_dino),
    "kong": (78, 70, 1.3, 3, draw_kong),
    "hero": (56, 70, 1.4, 3, draw_hero),
    "duck": (74, 66, 1.3, 2, draw_duck),
}.items()}
LETTERS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ"


def render(name):
    fw, fh, s, n, fn = TOYS[name]
    frames = []
    for i in range(n):
        ctx = Ctx(fw, fh)
        fn(Toy(ctx, fw // 2, 3, s), i if n > 2 else i == 1)
        frames.append(outline(ctx.im))
    return frames


def crop_all(frames):
    """所有影格一起裁掉四周的空白（同一隻的影格要對齊）"""
    boxes = [f.getbbox() for f in frames if f.getbbox()]
    x0, y0 = min(b[0] for b in boxes), min(b[1] for b in boxes)
    x1, y1 = max(b[2] for b in boxes), max(b[3] for b in boxes)
    return [f.crop((x0, y0, x1, y1)) for f in frames], (x0, y0)


def to_sprite(frames):
    """影格 → 字母圖：所有影格共用一份 ≤52 色的調色盤"""
    w, h = frames[0].size
    sheet = Image.new("RGBA", (w * len(frames), h))
    for i, f in enumerate(frames):
        sheet.paste(f, (i * w, 0))
    rgb = sheet.convert("RGB")
    colors = {c for _, c in rgb.getcolors(1 << 20)} if rgb.getcolors(1 << 20) else set()
    q = rgb.quantize(colors=len(LETTERS), method=Image.Quantize.MEDIANCUT) if len(colors) > len(LETTERS) else rgb.quantize(colors=max(1, len(colors)))
    pal = q.getpalette()
    qp, ap = q.load(), sheet.load()
    used, rows_all = {}, []
    for i in range(len(frames)):
        rows = []
        for y in range(h):
            row = []
            for x in range(w):
                if ap[i * w + x, y][3] == 0:
                    row.append(".")
                    continue
                k = qp[i * w + x, y]
                used.setdefault(k, LETTERS[len(used)])
                row.append(used[k])
            rows.append("".join(row).rstrip("."))
        rows_all.append(rows)
    palette = {ch: "#%02x%02x%02x" % tuple(pal[k * 3:k * 3 + 3]) for k, ch in used.items()}
    return rows_all, palette, (w, h)


def main(out, preview=None):
    art = {}
    sheets = []
    for name, (fw, fh, s, n, fn) in TOYS.items():
        frames, (x0, y0) = crop_all(render(name))
        rows, pal, (w, h) = to_sprite(frames)
        # 錨點：玩具中線（x）與影格上緣（y），換算到裁切後的座標，演出時用來對位
        art[name] = {"frames": rows, "pal": pal, "w": w, "h": h, "s": s, "cell": CELL, "ox": fw // 2 - x0, "oy": 3 - y0}
        sheets.append(frames)
    with open(out, "w") as f:
        json.dump(art, f, ensure_ascii=False, separators=(",", ":"))
    if preview:
        W = sum(f[0].size[0] * len(f) for f in sheets) + 10 * len(sheets)
        H = max(f[0].size[1] for f in sheets)
        im = Image.new("RGBA", (W, H), (40, 30, 70, 255))
        x = 0
        for fr in sheets:
            for f in fr:
                im.alpha_composite(f, (x, 0))
                x += f.size[0]
            x += 10
        im.resize((W * 3, H * 3), Image.NEAREST).save(preview)


if __name__ == "__main__":
    main(*sys.argv[1:])
