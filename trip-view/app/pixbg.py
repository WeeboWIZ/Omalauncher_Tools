#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
"""pixbg（也叫 tripview）：Trip View 的場景管理與 AI 生成，給 omalauncher 的 Trip View 小工具用。

  pixbg list                 列出場景（內建 + AI 生成）
  pixbg use <id|編號>         切換場景（小工具自己切換時不必呼叫）
  pixbg next | prev          下一個／上一個
  pixbg bundle               重新打包場景給小工具
  pixbg gen <一句話>          交給終端 agent（Codex 或 Claude，使用 CLI 預設模型）生成新場景
  pixbg del [id]             刪除 AI 生成的場景（預設目前這個）
  pixbg wall [id]            把場景定格成啟動器桌布
  pixbg lang <代碼>           小工具和進度訊息的語言（語言包在 ~/.local/share/pixbg/lang/<代碼>.json）
  pixbg langs                列出語言包
  pixbg thumbs [--all] [id]  補上（或重畫）場景卡片的縮圖
  pixbg preview              請手機重畫一次預覽，印出全螢幕 PNG 的路徑（檢查翻譯排版用）
  pixbg walls                列出相簿（~/Pictures/pixbg）裡的桌布
  pixbg setwall <檔名>        換成相簿裡的某一張
  pixbg rmwall <檔名>         從相簿刪掉一張
  pixbg check [id]           在本機檢查場景（編譯、AGSL 規則、GPU 運算量），不碰手機
  pixbg agent <claude|codex> [model]   換生成用的 agent 與模型

小工具讀 ~/.cache/pixbg/bundle.json（所有通過檢查的場景）、ui.json（語言）與 status.json（進度）。
切換場景是小工具自己的狀態，不經過這支程式，所以按下去馬上換；這裡改了目前場景時用 owl-send 通知它。
"""
import json, os, re, shutil, subprocess, sys, time, glob

sys.path.insert(0, os.path.dirname(os.path.realpath(__file__)))
import agslcheck
import sfx

HOME = os.path.expanduser("~")
DATA = os.path.join(HOME, ".local/share/pixbg")
SCENES = os.path.join(DATA, "scenes")
CACHE = os.path.join(HOME, ".cache/pixbg")
BUNDLE = os.path.join(CACHE, "bundle.json")     # 所有通過檢查的場景（含 shader），小工具切換場景不必再跑程式
EXPORT = os.path.join(CACHE, "export.json")     # 設為桌布時：要畫哪個場景、隱藏介面
SEL = os.path.join(CACHE, "sel")                # 目前的場景（小工具的 sel 狀態，pixbg 改它時順便記下）
CHECKED = os.path.join(CACHE, "checked.json")   # 通過檢查的 shader 雜湊，不用每次重跑 glslang
LANGS = os.path.join(DATA, "lang")
UI = os.path.join(CACHE, "ui.json")
STATUS = os.path.join(CACHE, "status.json")
CONFIG = os.path.join(HOME, ".config/pixbg/config.json")
WIDGETS = os.path.join(HOME, ".config/omalauncher/widgets")
STYLE = os.path.join(HOME, ".config/omalauncher/style/style.toml")
BOX = os.path.join(CACHE, "screen-box.json")
GALLERY = os.path.join(HOME, "Pictures/pixbg")  # 生成過的桌布都留在這裡，也可以自己丟圖進來
THUMBS = os.path.join(CACHE, "thumbs")
SCENE_THUMBS = os.path.join(CACHE, "scene-thumbs")   # 場景卡片的縮圖
WALLS = os.path.join(CACHE, "walls.json")
BLANK = "half4 main(float2 p) { return half4(0.0, 0.0, 0.0, 1.0); }"


def write_json(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(obj, f, ensure_ascii=False)
    os.replace(tmp, path)


def read_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except Exception:
        return default


_job = {}
LANG = os.path.join(CACHE, "lang")


def lang():
    try:
        code = open(LANG).read().strip()
    except OSError:
        code = "zh" if os.path.exists(os.path.join(LANGS, "zh.json")) else "en"
    return code if os.path.exists(os.path.join(LANGS, code + ".json")) else "en"


def pack(code):
    """語言包：缺的字串用英文補，英文也沒有就用中文。"""
    out = {"name": code, "names": "en", "wd": [], "T": {}, "msg": {}}
    for c in ("zh", "en", code):
        d = read_json(os.path.join(LANGS, c + ".json"), {})
        for k in ("name", "names", "wd", "ideas"):
            if d.get(k):
                out[k] = d[k]
        for k in ("T", "msg"):
            out[k].update({a: b for a, b in (d.get(k) or {}).items() if isinstance(b, str) and b})
    return out


def M(key, **kw):
    """pixbg 的訊息，跟著小工具的語言。"""
    tmpl = pack(lang())["msg"].get(key, key)
    try:
        return tmpl.format(**kw)
    except (KeyError, IndexError, ValueError):
        return tmpl


def langs():
    return [{"code": os.path.basename(f)[:-5], "name": read_json(f, {}).get("name") or os.path.basename(f)[:-5]}
            for f in sorted(glob.glob(os.path.join(LANGS, "*.json")))]


def build_ui(code=None):
    """ui.json：小工具用的語言包（介面字串、星期、場景名顯示哪一半）和可選的語言清單。"""
    code = code or lang()
    # 所有語言包都放進去：小工具切換語言只改自己的狀態，馬上就換
    packs = {x["code"]: {k: v for k, v in pack(x["code"]).items() if k != "msg"} for x in langs()}
    # 全螢幕頁的內容框（設為桌布時量的）：小工具據此把背景放大、位移，蓋住啟動器的標題列與外框
    box = read_json(BOX, {})
    write_json(UI, {"code": code, "packs": packs, "langs": langs(), "screen": box if box.get("box") else None, "agent": config()["agent"]})


def split_name(name):
    """「VOID SPACE 虛空」→（"VOID SPACE", "虛空"）：開頭的英文是英文名，其餘是中文名；缺一邊就用另一邊。"""
    m = re.match(r"^\s*([A-Za-z0-9][A-Za-z0-9 .'&!?:+\-]*?)\s*([^\x00-\x7f].*)?$", name or "")
    en = (m.group(1) if m else "").strip()
    zh = ((m.group(2) or "") if m else name or "").strip()
    return en or zh or name, zh or en or name


def status(state, msg="", p=None, to=None, eta=None, **extra):
    """進度寫進 status.json，小工具據此畫進度條。

    p 是目前進度（0..1）。給了 to 和 eta（秒），小工具會在 eta 秒內把進度條從 p 慢慢推到 to：
    用在等 agent 這種不知道確切進度、只知道大概要多久的步驟。
    """
    if state == "working" and not _job.get("started"):
        _job["started"] = int(time.time())
    write_json(STATUS, {"state": state, "msg": msg, "t": int(time.time()), "job": _job.get("job"),
                        "started": _job.get("started"), "p": p, "to": to if to is not None else p,
                        "eta": eta or 1, "since": int(time.time()), **extra})


def header():
    with open(os.path.join(DATA, "header.agsl")) as f:
        return f.read()


def meta(src, key):
    m = re.search(r"^//\s*%s:\s*(.+)$" % key, src, re.M)
    return m.group(1).strip() if m else None


MASCOTS = ("ufo", "car", "star", "firefly", "sentinel")


def palettes(src):
    """palette() 裡五組配色，給小工具的時鐘、吉祥物用同一套顏色：[{bg, c0, c1, c2, ac}, ...]"""
    m = re.search(r"void\s+palette\s*\(.*?\)\s*\{(.*?)\n\}", src, re.S)
    out = []
    for name, hexv in re.findall(r"\b(bg|c0|c1|c2|ac)\s*=\s*hx\(\s*0x([0-9a-fA-F]{6})\s*\)", m.group(1) if m else ""):
        if name == "bg" or not out:
            out.append({})
        out[-1][name] = "#" + hexv.lower()
    out = [z for z in out if len(z) == 5]
    for z in out:
        # 時鐘與文字用：ink 是最暗的顏色（太亮就壓暗），lite 最亮；fg 是在底色上看得清楚的那個
        lum = lambda h: (0.2126 * int(h[1:3], 16) + 0.7152 * int(h[3:5], 16) + 0.0722 * int(h[5:7], 16)) / 255
        ink = min(z.values(), key=lum)
        if lum(ink) > 0.25:
            ink = "#" + "".join(f"{int(int(ink[i:i + 2], 16) * 0.35):02x}" for i in (1, 3, 5))
        lite = max(z.values(), key=lum)
        z.update(ink=ink, lite=lite, fg=ink if lum(z["bg"]) > 0.5 else lite)
    return (out * 5)[:5] if out else []


def scenes():
    out = []
    for path in sorted(glob.glob(os.path.join(SCENES, "*.agsl"))):
        sid = os.path.basename(path)[:-5]
        with open(path) as f:
            src = f.read()
        out.append({"id": sid, "name": meta(src, "name") or sid, "prompt": meta(src, "prompt"),
                    "kind": "ai" if sid.startswith("ai-") else "preset", "path": path})
    return out


def current_id():
    try:
        return open(SEL).read().strip() or None
    except OSError:
        return None


def checked(body):
    """本機檢查，結果依內容雜湊記下來：同一份 shader 只跑一次 glslang。回傳錯誤清單。"""
    import hashlib
    key = hashlib.sha256((header() + body).encode()).hexdigest()
    memo = read_json(CHECKED, {})
    if key in memo:
        return []
    errs, c = agslcheck.check(header(), body)
    if not errs:
        memo[key] = round(c)
        write_json(CHECKED, memo)
    return errs


def entry(sc, body):
    mascot = meta(body, "mascot")
    en, zh = split_name(sc["name"])
    return {"id": sc["id"], "name": sc["name"], "en": en, "zh": zh, "kind": sc["kind"], "prompt": sc["prompt"],
            "pal": palettes(body), "mascot": mascot if mascot in MASCOTS else "ufo", "code": header() + body,
            # 角色層：<場景>.actors.json（美術 + 每一幕的演出），小工具用 Canvas 疊在 shader 上面
            "actors": read_json(sc["path"][:-5] + ".actors.json", None),
            # 場景卡片：縮圖（pixbg thumbs 請手機畫的）與標籤
            "tag": meta(body, "tag") or ("ai" if sc["kind"] == "ai" else "ufopump"),
            "thumb": thumb_path(sc["id"]) if os.path.exists(thumb_path(sc["id"])) else None}


def thumb_path(sid):
    return os.path.join(SCENE_THUMBS, sid + ".png")


def make_thumbs(ids=None, force=False):
    """請手機把每個場景畫一張全螢幕畫面（用它代表性的那一幕），裁成卡片縮圖。每張要重新載入一次小工具。"""
    from PIL import Image
    os.makedirs(SCENE_THUMBS, exist_ok=True)
    box = read_json(BOX, {}).get("box")
    if not box:
        sys.exit("pixbg: 先「設為桌布」一次，量出全螢幕畫面的範圍")
    todo = [sc for sc in scenes() if (ids is None or sc["id"] in ids) and (force or not os.path.exists(thumb_path(sc["id"])))]
    try:
        for sc in todo:
            z = meta(open(sc["path"]).read(), "thumb")
            write_json(EXPORT, {"on": True, "id": sc["id"], "zone": int(z) if z and z.isdigit() else None})
            im = Image.open(render()).convert("RGB").crop(tuple(box))
            w, h = im.size
            ch = int(w * 0.72)                    # 卡片的比例，取畫面偏下的地方（角色和地景多在那裡）
            top = max(0, min(h - ch, int(h * 0.62) - ch // 2))
            im.crop((0, top, w, top + ch)).resize((360, 259), Image.NEAREST).save(thumb_path(sc["id"]))
            print("縮圖：", sc["id"], flush=True)
    finally:
        write_json(EXPORT, {"on": False})
    build_bundle()


def build_bundle():
    """所有通過檢查的場景打包成 bundle.json。沒通過的不放進去：壞掉或太重的 shader 絕不送上手機。"""
    out, bad = [], []
    for sc in scenes():
        body = open(sc["path"]).read()
        errs = checked(body)
        if errs:
            bad.append((sc, errs))
        else:
            out.append(entry(sc, body))
    write_json(BUNDLE, {"scenes": out, "t": int(time.time())})
    build_ui()
    return out, bad


def notify_sel(sid):
    """記下目前場景，並告訴正在跑的小工具切過去（owl-send 是啟動器給腳本用的正式管道）。"""
    with open(SEL, "w") as f:
        f.write(sid)
    try:
        subprocess.run(["owl-send", widget_file(), "set", "sel", json.dumps(sid)], capture_output=True, timeout=10)
    except Exception:
        pass


def use(sid):
    all_ = scenes()
    sc = next((s for s in all_ if s["id"] == sid), None)
    if sc is None and sid.isdigit() and 0 < int(sid) <= len(all_):
        sc = all_[int(sid) - 1]
    if sc is None:
        sys.exit(f"pixbg: 找不到場景 {sid}")
    errs = checked(open(sc["path"]).read())
    if errs:
        status("error", M("notPassed", name=sc["name"]) + errs[0][:120])
        sys.exit("pixbg: " + "\n".join(errs))
    if not any(x["id"] == sc["id"] for x in read_json(BUNDLE, {}).get("scenes", [])):
        build_bundle()
    notify_sel(sc["id"])
    return sc


def step(d):
    ids = [x["id"] for x in read_json(BUNDLE, {}).get("scenes", [])] or [x["id"] for x in build_bundle()[0]]
    cur = current_id()
    i = ids.index(cur) if cur in ids else -1
    use(ids[(i + d) % len(ids)])


# ── 手機上的預覽（只在「設為桌布」時用）──

def widget_file():
    hits = sorted(glob.glob(os.path.join(WIDGETS, "*trip-view*.owl"))) or sorted(glob.glob(os.path.join(WIDGETS, "*pixel-bg*.owl")))
    if not hits:
        sys.exit("pixbg: 找不到 Trip View 小工具檔（~/.config/omalauncher/widgets/30-trip-view.owl）")
    return hits[0]


def render():
    """請啟動器畫一張全螢幕預覽，回傳 PNG 路徑。

    預覽只在小工具檔內容改變時才重畫，所以改寫檔尾的一行註解：這是啟動器正常的重新載入流程，
    不去動它內部的 .check／.errors 檔。
    """
    f = widget_file()
    with open(f) as fh:
        text = fh.read()
    text = re.sub(r"\n// pixbg-frame: \d+\n?$", "\n", text).rstrip("\n") + f"\n// pixbg-frame: {int(time.time() * 1000)}\n"
    with open(f, "w") as fh:
        fh.write(text)
    r = subprocess.run(["owl-check", f], capture_output=True, text=True, timeout=120)
    m = re.search(r"screen: (\S+\.png)", r.stdout)
    if not m:
        raise RuntimeError("啟動器沒有畫出預覽：" + (r.stdout + r.stderr).strip()[-200:])
    return m.group(1)


# ── AI 生成 ──

def config():
    agent = "claude"
    try:
        agent = open(os.path.join(HOME, ".config/omalauncher/agent")).read().strip() or agent
    except OSError:
        pass
    cfg = {"agent": agent if agent in ("claude", "codex") else "claude"}
    cfg.update(read_json(CONFIG, {}))
    if cfg.get("agent") not in ("codex", "claude"):
        cfg = {"agent": "claude", "model": ""}
    cfg.setdefault("model", "")
    return cfg


PROMPT = """你是像素藝術家兼 shader 工程師。為 Android 啟動器 omalauncher 寫一個「像素動畫背景」場景，
用 AGSL（Android 的 SkSL 片段著色器，語法近似 GLSL ES）。

使用者的一句話：「{wish}」

規則（和 UFOPUMP 遊戲背景同一套像素語言）：
1. 下面這段標頭會自動加在你的程式前面，不要重寫它，直接用裡面的 PX、hash*、band、dith、hx、ramp、segd、zone、speed、size、time：
```agsl
{header}
```
2. 先算 `float s = PX(); float2 c = floor(p / s); float2 G = floor(size / s); float t = time * max(speed, 0.0);`
   之後所有繪圖都在整數格座標 c 上做（邏輯寬約 216 格，y 向下）。不用抗鋸齒、不用平滑漸層：漸層一律用 band() 量化成 4–6 階並抖色。
3. 一定要寫 `void palette(float z, out half3 bg, out half3 c0, out half3 c1, out half3 c2, out half3 ac)`，
   依 zone（0..4）給五組配色：底色 bg、暗中亮三段色 c0 c1 c2、一個對比色 ac。五組要有明顯差異但同一個主題。
4. 至少三層：天空／遠景、中景、前景或粒子；至少兩種動效（飄移、閃爍、往上捲動的視差、粒子、偶發事件等）。
   任何一點的明暗交替每秒 3 次以內。畫面要直式手機（約 9:20）和方形小卡都好看，主體別只擠在一角。
5. AGSL 限制：沒有貼圖、沒有陣列；沒有 while；for 只能寫成 `for (int i = 0; i < 常數; i++)` 且次數 ≤ 16；
   全用 float（整數字面值寫成 1.0）；不可宣告全域可變變數；`%` 改用 mod()。
6. 效能是硬性規定：整個手機螢幕每秒要算 60 次，太重會讓 GPU 逾時、整個啟動器被系統重啟。
   每個像素的運算量（sin／cos／length／sqrt 約 1，pow 2，hash 約 0.6，迴圈裡的乘上次數）要在 {budget} 以內，
   參考範例約 {example_cost}。粒子、星星、雨滴用「格子分桶」（每格算一個 hash 決定有沒有東西），不要用迴圈逐一檢查；
   迴圈只留給少數大物件，而且先用距離或範圍判斷，不在附近就跳過。
7. 第一行寫 `// name: <場景短名，英文大寫＋中文，例如 NEON RAIN 霓虹雨>`，第二行寫 `// prompt: {wish_line}`，
   第三行寫 `// mascot: <ufo|car|star|firefly|sentinel 選一個最搭的>`（小工具上會有這隻像素吉祥物陪著場景）。
   palette() 裡的顏色一律寫成 `hx(0xRRGGBB)`，時鐘和吉祥物會沿用同一套顏色。
8. 只輸出一個 ```agsl 程式碼區塊，裡面是完整的場景（palette、輔助函式、`half4 main(float2 p)`），區塊外不要有任何文字。不要用工具、不要讀寫檔案。

參考範例（內建的 VOID SPACE）：
```agsl
{example}
```
"""

FIX = """剛才的程式沒有通過檢查（還沒送上手機），問題是：
{err}

請修正後重新輸出完整的 ```agsl 程式碼區塊（同樣的規則，區塊外不要有文字）。原本的程式：
```agsl
{code}
```
"""


def ask_agent(prompt, cfg):
    agent, model = cfg["agent"], cfg.get("model")
    if shutil.which(agent) is None:
        raise RuntimeError(M("missingAgent", agent=agent.capitalize()))
    if agent == "codex":
        out = os.path.join(CACHE, "codex-last.txt")
        cmd = ["codex", "exec", "--skip-git-repo-check", "-o", out]
        if model:
            cmd += ["-m", model]
        r = subprocess.run(cmd + ["-"], input=prompt, capture_output=True, text=True, timeout=900, cwd=CACHE)
        text = open(out).read() if os.path.exists(out) else r.stdout
    else:
        cmd = ["claude", "-p", "--output-format", "text"]
        if model:
            cmd += ["--model", model]
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, timeout=900, cwd=CACHE)
        text = r.stdout
    if r.returncode != 0 and not text.strip():
        raise RuntimeError((r.stderr or "agent 失敗").strip()[-300:])
    m = re.findall(r"```(?:agsl|glsl|sksl|c|cpp)?\s*\n(.*?)```", text, re.S)
    code = max(m, key=len) if m else text
    if "main" not in code:
        raise RuntimeError("agent 沒有回傳 shader")
    return code.strip() + "\n"


def gen(wish):
    cfg = config()
    model = cfg.get("model") or cfg["agent"]
    m = re.match(r"claude-(\w+)-(\d+)-(\d+)$", model)
    who = f"{m.group(1).capitalize()} {m.group(2)}.{m.group(3)}" if m else model
    _job["job"] = "gen"
    times = read_json(os.path.join(CACHE, "gen-times.json"), [])
    eta = sorted(times)[len(times) // 2] if times else 360
    status("working", M("sketching", who=who, wish=wish), p=0.05, to=0.85, eta=eta, wish=wish)
    with open(os.path.join(SCENES, "10-void.agsl")) as f:
        example = f.read()
    hdr = header()
    _, example_cost = agslcheck.check(hdr, example)
    prompt = PROMPT.format(wish=wish, wish_line=wish.replace("\n", " "), header=hdr.replace("// ── 場景 ──\n", ""),
                           example=example, budget=agslcheck.BUDGET, example_cost=round(example_cost))
    sid = time.strftime("ai-%Y%m%d-%H%M%S")
    t0 = time.time()
    try:
        code, errs = "", []
        for attempt in range(3):
            code = ask_agent(prompt if attempt == 0 else FIX.format(err="\n".join(errs), code=code), cfg)
            if not re.search(r"^//\s*name:", code, re.M):
                code = f"// name: {wish[:16]}\n" + code
            if not re.search(r"^//\s*prompt:", code, re.M):
                code = code.replace("\n", f"\n// prompt: {wish}\n", 1)
            # 先在本機檢查，通過了才存進場景、送上手機
            status("working", M("checking"), p=0.88, wish=wish)
            errs, c = agslcheck.check(hdr, code)
            print(f"[{time.strftime('%T')}] 第 {attempt + 1} 次：{time.time() - t0:.0f}s，運算量 {c:.0f}，{errs or 'ok'}", flush=True)
            if not errs:
                with open(os.path.join(SCENES, sid + ".agsl"), "w") as f:
                    f.write(code)
                build_bundle()
                notify_sel(sid)
                try:
                    make_thumbs([sid])
                except BaseException:
                    pass
                write_json(os.path.join(CACHE, "gen-times.json"), (times + [int(time.time() - t0)])[-9:])
                status("done", M("done", name=split_name(meta(code, "name"))[pack(lang())["names"] != "en"], secs=fmt_secs(time.time() - t0)), p=1, wish=wish, id=sid)
                return
            status("working", M("retry", n=attempt + 1) + errs[0].splitlines()[0][:50], p=0.3 + 0.2 * attempt, to=0.85, eta=eta * 0.6, wish=wish)
        raise RuntimeError(M("failed3") + errs[0].splitlines()[0][:160])
    except Exception as e:
        status("error", str(e)[:300], wish=wish)
        sys.exit(1)


# ── 定格成桌布 ──

def fmt_secs(x):
    x = int(x)
    return M("mins", m=x // 60, s=x % 60) if x >= 60 else M("secs", s=x)


def theme_name():
    try:
        m = re.search(r'^\s*theme\s*=\s*"([^"]+)"', open(STYLE).read(), re.M)
        return m.group(1) if m else None
    except OSError:
        return None


def set_background(name):
    with open(STYLE) as f:
        text = f.read()
    line = f'background = "{name}"'
    if re.search(r"^\s*background\s*=", text, re.M):
        text = re.sub(r"^\s*background\s*=.*$", line, text, count=1, flags=re.M)
    elif re.search(r"^\s*theme\s*=.*$", text, re.M):
        text = re.sub(r"^(\s*theme\s*=.*)$", r"\1\n" + line, text, count=1, flags=re.M)
    else:
        text = text.rstrip("\n") + "\n" + line + "\n"
    with open(STYLE, "w") as f:
        f.write(text)


def wall_files():
    os.makedirs(GALLERY, exist_ok=True)
    files = [f for f in os.listdir(GALLERY) if f.lower().endswith((".png", ".jpg", ".jpeg", ".webp")) and not f.startswith(".")]
    return sorted(files, key=lambda f: os.path.getmtime(os.path.join(GALLERY, f)), reverse=True)


def active_wall():
    """style.toml 指向的 pixbg-<相簿檔名>，回傳相簿檔名。"""
    try:
        m = re.search(r'^\s*background\s*=\s*"pixbg-([^"]+)"', open(STYLE).read(), re.M)
        return m.group(1) if m and os.path.exists(os.path.join(GALLERY, m.group(1))) else None
    except OSError:
        return None


def list_walls():
    """相簿清單寫進 walls.json（新的在前），順便補齊縮圖；小工具的「桌布相簿」讀它。"""
    from PIL import Image
    os.makedirs(THUMBS, exist_ok=True)
    active = active_wall()
    out = []
    for f in wall_files():
        src = os.path.join(GALLERY, f)
        thumb = os.path.join(THUMBS, os.path.splitext(f)[0] + ".png")
        if not os.path.exists(thumb) or os.path.getmtime(thumb) < os.path.getmtime(src):
            try:
                im = Image.open(src).convert("RGB")
                im.thumbnail((216, 480), Image.NEAREST)
                im.save(thumb)
            except Exception:
                continue
        m = re.match(r"(\d{8})-(\d{6})-(.+)\.\w+$", f)
        label = f"{m.group(1)[4:6]}/{m.group(1)[6:]} {m.group(2)[:2]}:{m.group(2)[2:4]}" if m else os.path.splitext(f)[0][:14]
        out.append({"file": f, "thumb": thumb, "label": label, "active": f == active})
    write_json(WALLS, out)
    return out


def apply_wall(name):
    """把相簿裡的一張放進啟動器的桌布資料夾並設為背景。桌布資料夾只留這一張，相簿保留全部。"""
    theme = theme_name()
    if not theme:
        sys.exit("pixbg: style.toml 沒有 theme")
    src = os.path.join(GALLERY, name)
    if not os.path.exists(src):
        sys.exit(f"pixbg: 相簿裡沒有 {name}")
    folder = os.path.join(HOME, ".config/omarchy/backgrounds", theme)
    os.makedirs(folder, exist_ok=True)
    for old in glob.glob(os.path.join(folder, "pixbg-*")):
        os.remove(old)
    shutil.copyfile(src, os.path.join(folder, "pixbg-" + name))
    set_background("pixbg-" + name)
    list_walls()


def migrate_walls():
    """舊版直接存在桌布資料夾的 pixbg-*.png 搬進相簿。"""
    for old in glob.glob(os.path.join(HOME, ".config/omarchy/backgrounds/*/pixbg-*.png")):
        base = os.path.basename(old)[len("pixbg-"):]
        m = re.match(r"(.+)-(\d{9,})\.png$", base)
        if m:  # pixbg-<場景>-<unix 秒>.png → <日期>-<時間>-<場景>.png
            name = time.strftime("%Y%m%d-%H%M%S-", time.localtime(int(m.group(2)))) + m.group(1) + ".png"
            os.makedirs(GALLERY, exist_ok=True)
            if not os.path.exists(os.path.join(GALLERY, name)):
                shutil.copyfile(old, os.path.join(GALLERY, name))
                os.utime(os.path.join(GALLERY, name), (int(m.group(2)), int(m.group(2))))
            if re.search(r'background\s*=\s*"%s"' % re.escape(os.path.basename(old)), open(STYLE).read()):
                apply_wall(name)


def wall(sid=None):
    from PIL import Image
    sid = sid or current_id() or (read_json(BUNDLE, {}).get("scenes") or [{}])[0].get("id")
    if not sid:
        sys.exit("pixbg: 還沒有選場景")
    if not theme_name():
        sys.exit("pixbg: style.toml 沒有 theme")
    _job["job"] = "wall"
    status("working", M("wallPrep"), p=0.05)
    try:
        # 全螢幕預覽裡 shader 佔的範圍：第一次畫一張純洋紅的量出來，之後沿用
        saved = read_json(BOX, {})
        box = tuple(saved["box"]) if saved.get("box") else None
        if not box:
            status("working", M("wallMeasure"), p=0.1, to=0.4, eta=8)
            write_json(EXPORT, {"on": True, "probe": True})
            im = Image.open(render()).convert("RGB")
            W, H = im.size
            px = im.load()
            ys = [y for y in range(0, H, 2) if px[W // 2, y] == (255, 0, 255)]
            xs = [x for x in range(0, W, 2) if px[x, H // 2] == (255, 0, 255)]
            if not xs or not ys:
                raise RuntimeError("量不到畫面範圍")
            box = (min(xs), min(ys), max(xs) + 1, max(ys) + 1)
            write_json(BOX, {"box": box, "size": [W, H]})
        write_json(EXPORT, {"on": True, "id": sid})
        status("working", M("wallDraw"), p=0.45, to=0.85, eta=7)
        shot = render()
        status("working", M("wallCrop"), p=0.9)
        W, H = Image.open(shot).size
        im = Image.open(shot).convert("RGB").crop(box).resize((W, H), Image.NEAREST)
        os.makedirs(GALLERY, exist_ok=True)
        name = time.strftime("%Y%m%d-%H%M%S-") + sid + ".png"
        im.save(os.path.join(GALLERY, name))
        apply_wall(name)
        status("done", M("wallDone"), p=1)
    except Exception as e:
        status("error", (M("wallFail") + str(e))[:300])
        raise
    finally:
        write_json(EXPORT, {"on": False})


def main(argv):
    os.makedirs(CACHE, exist_ok=True)
    sfx.ensure(os.path.join(CACHE, "sfx"))
    if not os.path.exists(UI):
        build_ui()
    cmd = argv[0] if argv else "list"
    if cmd == "list":
        cur = current_id()
        for i, s in enumerate(scenes(), 1):
            print(f"{'*' if s['id'] == cur else ' '} {i:2} {s['id']:24} {s['name']}")
    elif cmd == "use":
        use(argv[1])
    elif cmd in ("next", "prev"):
        step(1 if cmd == "next" else -1)
    elif cmd == "bundle":
        ok, bad = build_bundle()
        build_ui()
        print(f"{len(ok)} 個場景打包好" + "".join(f"\n  ✗ {sc['id']}: {errs[0].splitlines()[0]}" for sc, errs in bad))
    elif cmd == "gen":
        wish = " ".join(argv[1:]).strip()
        if not wish:
            sys.exit("pixbg gen <一句話>")
        if "--fg" in argv or os.environ.get("PIXBG_FG"):
            gen(wish.replace("--fg", "").strip())
        else:
            # 小工具的 run() 不必等 agent：自己放到背景，進度寫進 status.json
            log = open(os.path.join(CACHE, "gen.log"), "a")
            subprocess.Popen([sys.executable, os.path.abspath(__file__), "gen", "--fg", wish],
                             stdout=log, stderr=log, start_new_session=True)
            _job.update(job="gen", started=int(time.time()))
            status("working", M("handoff"), p=0.02, wish=wish)
    elif cmd == "del":
        sid = argv[1] if len(argv) > 1 else current_id()
        if not sid or not sid.startswith("ai-"):
            sys.exit("pixbg: 只能刪 AI 生成的場景")
        ids = [x["id"] for x in read_json(BUNDLE, {}).get("scenes", [])]
        before = ids[ids.index(sid) - 1] if sid in ids and ids.index(sid) > 0 else (ids[0] if ids else None)
        os.remove(os.path.join(SCENES, sid + ".agsl"))
        build_bundle()
        if before and before != sid:
            notify_sel(before)
    elif cmd == "wall":
        wall(argv[1] if len(argv) > 1 else None)
    elif cmd == "lang":
        code = (argv[1] if len(argv) > 1 else "zh").strip()
        path = os.path.join(LANGS, code + ".json")
        try:
            d = json.load(open(path))
        except FileNotFoundError:
            sys.exit(f"pixbg: 沒有語言包 {path}")
        except ValueError as e:
            sys.exit(f"pixbg: {path} 不是合法的 JSON：{e}")
        missing = [k for k in pack("en")["T"] if k not in (d.get("T") or {})] + [k for k in pack("en")["msg"] if k not in (d.get("msg") or {})]
        with open(LANG, "w") as f:
            f.write(code)
        build_ui(code)
        try:
            subprocess.run(["owl-send", widget_file(), "set", "langCode", json.dumps(code)], capture_output=True, timeout=10)
        except Exception:
            pass
        print(f"語言：{d.get('name') or code}" + (f"（缺 {len(missing)} 個字串，暫用英文：{', '.join(missing[:12])}）" if missing else ""))
    elif cmd == "langs":
        cur = lang()
        for x in langs():
            print(("* " if x["code"] == cur else "  ") + f"{x['code']:8} {x['name']}")
    elif cmd == "preview":
        print(render())
    elif cmd == "thumbs":
        # pixbg thumbs [--all] [id ...]：補上場景卡片的縮圖（--all 全部重畫）
        ids = [a for a in argv[1:] if not a.startswith("--")] or None
        make_thumbs(ids, force="--all" in argv)
    elif cmd == "walls":
        migrate_walls()
        for w in list_walls():
            print(("* " if w["active"] else "  ") + w["file"])
    elif cmd == "setwall":
        apply_wall(argv[1])
        status("done", M("wallSwitched"), p=1)
    elif cmd == "rmwall":
        name = os.path.basename(argv[1])
        if name == active_wall():
            sys.exit("pixbg: 這張正在用，先換一張再刪")
        os.remove(os.path.join(GALLERY, name))
        list_walls()
    elif cmd == "agent":
        if len(argv) < 2 or argv[1] not in ("codex", "claude"):
            sys.exit("Usage: pixbg agent <codex|claude> [model]")
        cfg = read_json(CONFIG, {})
        cfg["agent"] = argv[1]
        cfg["model"] = argv[2] if len(argv) > 2 else ""
        write_json(CONFIG, cfg)
        build_ui()
        print(cfg)
    elif cmd == "check":
        # pixbg check [id ...]：本機檢查場景（不碰手機）
        ids = argv[1:] or [s["id"] for s in scenes()]
        bad = 0
        for sc in scenes():
            if sc["id"] in ids:
                errs, c = agslcheck.check(header(), open(sc["path"]).read())
                bad += bool(errs)
                print(f"{'✗' if errs else '✓'} {sc['id']:24} 運算量 {c:5.0f}/{agslcheck.BUDGET}  " + ("; ".join(e.splitlines()[0] for e in errs)))
        sys.exit(1 if bad else 0)
    else:
        print(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
