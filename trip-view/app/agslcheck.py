# SPDX-License-Identifier: GPL-3.0-or-later
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
"""在 Linux 這邊檢查 AGSL 場景，不碰手機：
  1. AGSL 的限制（常數次數的 for、沒有 while／陣列／貼圖）
  2. 翻成 GLSL 交給 glslangValidator 做語法與型別檢查
  3. 估算每個像素的運算量（迴圈會乘上次數），超過預算就不准上手機

手機的 GPU 每秒要把整個畫面（1080×2400）算 60 次，太重的 shader 會讓 GPU 逾時、
整個啟動器被系統重啟，所以一律先在這裡擋下來。
"""
import os, re, subprocess, tempfile

# 一個像素的運算預算（單位約等於一次 sin）。內建場景都在這個範圍內
BUDGET = 130
MAX_LOOP = 16
MAX_SRC = 20000

# 內建函式的大約成本
COST = {"sin": 1, "cos": 1, "tan": 2, "asin": 2, "acos": 2, "atan": 2, "pow": 2, "exp": 1.5, "log": 1.5,
        "sqrt": 1, "inversesqrt": 1, "length": 1, "distance": 1, "normalize": 1.5, "smoothstep": 0.5,
        "fract": 0.2, "floor": 0.1, "mod": 0.3, "mix": 0.2, "dot": 0.2, "clamp": 0.1, "abs": 0.05, "step": 0.1}

PRELUDE = """#version 450
#define half float
#define half2 vec2
#define half3 vec3
#define half4 vec4
#define float2 vec2
#define float3 vec3
#define float4 vec4
#define int2 ivec2
#define int3 ivec3
#define int4 ivec4
#define bool2 bvec2
#define bool3 bvec3
#define bool4 bvec4
#define float2x2 mat2
#define float3x3 mat3
#define float4x4 mat4
#define half2x2 mat2
#define half3x3 mat3
uniform vec2 size;
uniform float time;
layout(location = 0) out vec4 pixbg_out;
"""


def _block(src, i):
    """src[i] 之後第一個 { ... } 區塊（或單一敘述）的 (開始, 結束)。"""
    j = i
    while j < len(src) and src[j] in " \t\r\n":
        j += 1
    if j < len(src) and src[j] == "{":
        depth = 0
        for k in range(j, len(src)):
            if src[k] == "{":
                depth += 1
            elif src[k] == "}":
                depth -= 1
                if depth == 0:
                    return j, k + 1
        return j, len(src)
    k = src.find(";", j)
    return j, (k + 1 if k >= 0 else len(src))


def _strip_comments(src):
    src = re.sub(r"/\*.*?\*/", " ", src, flags=re.S)
    return re.sub(r"//[^\n]*", "", src)


def functions(src):
    """{名稱: 函式本體}"""
    out = {}
    for m in re.finditer(r"\b(?:void|float|half|bool|int|float[234]|half[234]|int[234]|bool[234])\s+(\w+)\s*\([^)]*\)\s*\{", src):
        a, b = _block(src, m.end() - 1)
        out[m.group(1)] = src[a:b]
    return out


def cost(body, fns, memo, depth=0):
    if depth > 8:
        return 0
    total = 0.0
    rest = body
    while True:
        m = re.search(r"\bfor\s*\(\s*int\s+\w+\s*=\s*(-?\d+)\s*;\s*\w+\s*(<|<=)\s*(\d+)", rest)
        if not m:
            break
        close = rest.find(")", m.end())
        a, b = _block(rest, close + 1)
        n = int(m.group(3)) - int(m.group(1)) + (1 if m.group(2) == "<=" else 0)
        total += max(n, 1) * cost(rest[a:b], fns, memo, depth + 1)
        rest = rest[:m.start()] + rest[b:]
    for name in re.findall(r"\b(\w+)\s*\(", rest):
        if name in COST:
            total += COST[name]
        elif name in fns:
            if name not in memo:
                memo[name] = 0  # 擋遞迴
                memo[name] = cost(fns[name], fns, memo, depth + 1)
            total += memo[name]
    return total


def rules(body):
    """AGSL 不允許、GLSL 卻會放過的寫法。"""
    errs = []
    if len(body) > MAX_SRC:
        errs.append(f"程式太長（{len(body)} 字元，上限 {MAX_SRC}）")
    if re.search(r"\b(while|do)\b", body):
        errs.append("不能用 while／do 迴圈，只能用常數次數的 for")
    for m in re.finditer(r"\bfor\s*\(([^)]*)\)", body):
        hdr = m.group(1)
        lm = re.match(r"\s*int\s+(\w+)\s*=\s*(-?\d+)\s*;\s*(\w+)\s*(<|<=)\s*(\d+)\s*;\s*(\w+)\s*(\+\+|\+=\s*1)\s*$", hdr)
        if not lm:
            errs.append(f"for 迴圈要寫成 for (int i = 0; i < 常數; i++)：for ({hdr.strip()})")
        elif int(lm.group(5)) - int(lm.group(2)) > MAX_LOOP:
            errs.append(f"迴圈次數 {int(lm.group(5)) - int(lm.group(2))} 超過上限 {MAX_LOOP}")
    if re.search(r"\b(texture|sampler\w*|shader\s+\w+|eval)\b", body):
        errs.append("不能用貼圖或子 shader")
    if re.search(r"\w\s*\[\s*\d*\s*\]\s*(=|;)", body) or re.search(r"\b\w+\s*\[\s*\]", body):
        errs.append("不能用陣列")
    if not re.search(r"\bhalf4\s+main\s*\(\s*float2\s+\w+\s*\)", body):
        errs.append("要有 half4 main(float2 p)")
    return errs


def glsl(full, body_off=0):
    """用 glslangValidator 編譯；回傳錯誤文字或 None。"""
    code = re.sub(r"\bhalf4\s+main\s*\(", "vec4 pixbg_main(", full)
    code = PRELUDE + code + "\nvoid main() { pixbg_out = pixbg_main(gl_FragCoord.xy); }\n"
    with tempfile.NamedTemporaryFile("w", suffix=".frag", delete=False) as f:
        f.write(code)
        path = f.name
    try:
        r = subprocess.run(["glslangValidator", path], capture_output=True, text=True, timeout=30)
    finally:
        os.unlink(path)
    if r.returncode == 0:
        return None
    off = PRELUDE.count("\n") + body_off
    lines = []
    for l in (r.stdout + r.stderr).splitlines():
        m = re.match(r"ERROR: [^:]*:(\d+): (.*)", l)
        if m:
            lines.append(f"第 {int(m.group(1)) - off} 行：{m.group(2)}")
    return "\n".join(lines[:8]) or (r.stdout + r.stderr)[-600:]


def check(header, body):
    """回傳 (錯誤清單, 成本)。錯誤清單空的才可以上手機。"""
    src = _strip_comments(body)
    errs = rules(src)
    err = glsl(header + body, header.count("\n"))
    if err:
        errs.append("編譯錯誤：\n" + err)
    full = _strip_comments(header + body)
    fns = functions(full)
    c = cost(fns.get("main", ""), fns, {})
    if c > BUDGET:
        errs.append(f"每像素運算量約 {c:.0f}，超過預算 {BUDGET}：減少迴圈次數、每格的 hash／sin 呼叫，或在迴圈前先用距離判斷提早跳過")
    return errs, c
