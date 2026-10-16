# SPDX-License-Identifier: MIT
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
"""產生 scenes/60-kaiju.actors.json：toys.py 畫的四隻軟膠玩具 + 直升機，加上五幕的演出。
位置都是畫面的比例：x 是玩具中線，y 是玩具腳底；[基準, 振幅, 頻率, 相位] → 基準 + 振幅 × sin(t × 頻率 + 相位)。"""
import json, os, subprocess, sys, tempfile

here = os.path.dirname(os.path.abspath(__file__))
tmp = os.path.join(tempfile.mkdtemp(), "toys.json")
subprocess.run([sys.executable, os.path.join(here, "toys.py"), tmp], check=True)
art = json.load(open(tmp))
# 直升機（UFOPUMP 的 HELI，機身 # 用場景亮色、尾巴 = 用對比色），吊著鋼絲繞著大猩猩
art["heli"] = {"frames": [["...#......", ".####.....", "######====", ".####....=", ".#..#....."],
                          [".........", ".####.....", "######====", ".####....=", ".#..#....."]],
               "pal": {"#": "#e8f0f8", "=": "#ffb82a"}, "w": 10, "h": 5, "s": 1, "cell": 2, "ox": 3, "oy": 0}

def at(toy, x, y):
    g = art[toy]
    return [round(g["ox"] + x * g["s"]), round(g["oy"] + y * g["s"])]

ROAR = [[0, 0], [1, 1], [3.4, 0]]          # 每 9 秒：吼、放光線、收招
acts = [
    # 1 黃昏片場：恐龍只露出冠，在畫面底下慢慢滑過
    {"id": "dino", "toy": "dino", "zones": [0], "x": [0.5, 0.28, 0.17, 0], "y": [1.0, 0, 0, 0], "sink": 34, "hop": [1, 1.6], "seq": [0]},
    # 2 怪獸警報：探出頭吼叫，光線往天上掃
    {"id": "dino", "toy": "dino", "zones": [1], "x": [0.5, 0.26, 0.17, 0], "y": [1.0, 0, 0, 0], "sink": 4, "hop": [1.5, 1.6], "cycle": 9, "keys": ROAR},
    # 3 大樓攻防：大猩猩抱著樓上下爬、偶爾捶胸；兩架直升機繞著牠；恐龍在底下探頭
    {"id": "dino", "toy": "dino", "zones": [2], "x": [0.3, 0.1, 0.17, 0], "y": [1.0, 0, 0, 0], "sink": 26, "hop": [1, 1.6], "seq": [0]},
    {"id": "kong", "toy": "kong", "zones": [2], "x": [0.68, 0, 0, 0], "y": [0.6, 0.18, 0.3, 0], "hop": [1, 3], "fps": 3, "seq": [0, 1, 0, 1, 0, 1, 2, 2, 2]},
    {"id": "heli1", "toy": "heli", "zones": [2], "x": [0.68, 0.3, 0.8, 0], "y": [0.42, 0.08, 0.8, 1.57], "fps": 10, "seq": [0, 1], "wire": True},
    {"id": "heli2", "toy": "heli", "zones": [2], "x": [0.68, 0.3, 0.8, 3.14], "y": [0.5, 0.08, 0.8, 4.71], "fps": 10, "seq": [1, 0], "wire": True},
    # 4 英雄登場：英雄從上面對著恐龍放光線，交會點來回推擠；打贏比讚，恐龍縮下去
    {"id": "dino", "toy": "dino", "zones": [3], "x": [0.5, 0.22, 0.17, 0], "y": [1.0, 0, 0, 0], "sink": 4, "hop": [1.5, 1.6], "cycle": 9, "keys": ROAR, "dip": [9, 3.2, 4.4, 10]},
    {"id": "hero", "toy": "hero", "zones": [3], "x": [0.5, 0.2, 0.17, 3.14], "y": [0.36, 0.015, 1.1, 0], "cycle": 9, "keys": [[0, 0], [1.5, 1], [3.2, 2], [4.4, 0]], "wire": True},
    # 5 高空決戰：鴨嘴怪拍著翅膀繞 8 字，英雄在後面追著打
    {"id": "duck", "toy": "duck", "zones": [4], "x": [0.5, 0.3, 0.45, 0], "y": [0.42, 0.14, 0.85, 1], "fps": 5, "seq": [0, 1], "wire": True},
    {"id": "hero", "toy": "hero", "zones": [4], "x": [0.5, 0.3, 0.45, -0.55], "y": [0.62, 0.14, 0.85, 0.05], "seq": [0], "wire": True},
]
fx = [
    {"type": "beam", "zones": [1], "from": ["dino"] + at("dino", 0, 22), "angle": [-90, 32, 2.4], "len": 0.9, "cycle": 9, "on": [1.5, 3.2], "color": "#8fd8ff", "width": 3},
    {"type": "clash", "zones": [3], "a": ["dino"] + at("dino", 0, 22), "b": ["hero"] + at("hero", 8, 18.4), "cycle": 9, "on": [1.5, 3.2], "color": "#8fd8ff", "color2": "#ffe14a", "width": 3},
    {"type": "sparks", "zones": [3], "at": ["hero"] + at("hero", 0, 22), "cycle": 9, "on": [3.2, 4.4], "color": "#ffe14a", "r": 14},
    {"type": "link", "zones": [4], "a": ["hero"] + at("hero", 11.6, 5.2), "b": ["duck"] + at("duck", 0, 22), "cycle": 1.6, "on": [0, 0.5], "color": "#ffe14a", "width": 2},
    {"type": "link", "zones": [2], "a": ["heli1", 0, 3], "b": ["kong"] + at("kong", 0, 20), "cycle": 1.2, "on": [0, 0.35], "color": "#ffe14a", "width": 1},
    {"type": "link", "zones": [2], "a": ["heli2", 0, 3], "b": ["kong"] + at("kong", 0, 26), "cycle": 1.2, "on": [0.6, 0.95], "color": "#ffe14a", "width": 1},
    {"type": "sparks", "zones": [2], "at": ["kong"] + at("kong", 0, 16), "cycle": 3, "on": [2, 3], "color": "#ffe14a", "r": 22},
]
out = os.path.join(here, "scenes", "60-kaiju.actors.json")
json.dump({"art": art, "acts": acts, "fx": fx}, open(out, "w"), ensure_ascii=False, separators=(",", ":"))
print(out, os.path.getsize(out))
