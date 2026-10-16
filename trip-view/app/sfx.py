# SPDX-License-Identifier: MIT
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
"""pixbg 的 8-bit 音效：短短的方波／三角波，寫成 22 kHz 單聲道 WAV。
小工具用 paplay 直接播，不必啟動 Python，點下去馬上有聲音。"""
import math, os, struct, wave

RATE = 22050
VOLUME = 0.28  # 手機喇叭，常在安靜的地方用，音量放低


def tone(f0, ms, wave_="square", f1=None, decay=4.0, vib=0.0):
    """一個音：f0 滑到 f1（Hz），指數衰減，加一點點顫音。方波只取前幾個奇次諧波，不刺耳。"""
    n = int(RATE * ms / 1000)
    f1 = f1 or f0
    out, ph, low = [], 0.0, 0.0
    for i in range(n):
        t = i / n
        f = f0 * (f1 / f0) ** t * (1 + vib * math.sin(2 * math.pi * 12 * i / RATE))
        ph = (ph + f / RATE) % 1.0
        x = 2 * math.pi * ph
        if wave_ == "tri":
            v = 4 * abs(ph - 0.5) - 1
        elif wave_ == "noise":
            v = math.sin(x * 37.1 + math.sin(i * 0.37) * 9) * 0.6
        else:
            v = (math.sin(x) + math.sin(3 * x) / 4 + math.sin(5 * x) / 10) * 0.85
        env = min(1.0, i / 60) * min(1.0, (n - i) / 200) * math.exp(-decay * t)
        low += 0.45 * (v * env - low)
        out.append(low)
    return out


def seq(*parts):
    out = []
    for p in parts:
        out += p
    return out


def mix(a, b, gb=0.5):
    n = max(len(a), len(b))
    return [(a[i] if i < len(a) else 0) + gb * (b[i] if i < len(b) else 0) for i in range(n)]


def notes(fs, ms, **kw):
    return seq(*[tone(f, ms, **kw) for f in fs])


SOUNDS = {
    "tap": lambda: tone(660, 50, f1=990, decay=5),
    "next": lambda: notes([523, 784], 55, decay=4),
    "prev": lambda: notes([784, 523], 55, decay=4),
    "zone": lambda: notes([1047, 1319, 1568], 45, wave_="tri", decay=3),
    "speed": lambda: tone(330, 120, f1=880, wave_="tri", decay=2),
    "hide": lambda: tone(880, 90, f1=440, wave_="tri", decay=3),
    "boing": lambda: tone(392, 180, f1=880, wave_="tri", decay=2.5, vib=0.03),
    "beam": lambda: mix(tone(220, 420, f1=1320, wave_="tri", decay=1.5, vib=0.06), tone(1200, 300, wave_="noise", decay=4), 0.15),
    "wall": lambda: seq(tone(1400, 25, wave_="noise", decay=6), tone(900, 30, wave_="noise", decay=6), notes([784, 1047], 70, decay=3)),
    "gen": lambda: mix(tone(262, 600, f1=1047, decay=1.5, vib=0.04), seq([0.0] * int(RATE * 0.45), notes([1568, 2093], 60, wave_="tri")), 0.5),
    "done": lambda: seq(notes([523, 659, 784], 70, decay=3), tone(1047, 260, decay=2, vib=0.02)),
    "error": lambda: notes([330, 247], 120, wave_="tri", decay=2),
}


def write(path, samples):
    peak = max(1e-6, max(abs(x) for x in samples))
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(b"".join(struct.pack("<h", int(32767 * VOLUME * x / peak)) for x in samples))


def ensure(folder):
    os.makedirs(folder, exist_ok=True)
    for name, make in SOUNDS.items():
        path = os.path.join(folder, name + ".wav")
        if not os.path.exists(path):
            write(path, make())
