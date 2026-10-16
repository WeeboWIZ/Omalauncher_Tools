#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (C) 2026 WeeboWIZ. Part of Trip View; see LICENSE.
"""pixbg（也叫 tripview）：Trip View 的場景管理與 AI 生成，給 omalauncher 的 Trip View 小工具用。

  pixbg list                 列出場景（內建 + AI 生成）
  pixbg use <id|編號>         切換場景（小工具自己切換時不必呼叫）
  pixbg next | prev          下一個／上一個
  pixbg bundle               重新打包場景給小工具
  pixbg gen <一句話>          交給終端 agent（Codex 或 Claude，使用 CLI 預設模型）生成新場景
  pixbg edit <id> <想怎麼改>   請 agent 修改 AI 生成的場景（舊版留在 ~/.cache/pixbg/scene-history）
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
  pixbg agents               檢查兩個 agent 裝了沒、登入了沒
  pixbg cancel               停掉正在跑的生成

小工具讀 ~/.cache/pixbg/bundle.json（所有通過檢查的場景）、ui.json（語言）與 status.json（進度）。
切換場景是小工具自己的狀態，不經過這支程式，所以按下去馬上換；這裡改了目前場景時用 owl-send 通知它。
"""
import json, os, queue, re, shutil, signal, subprocess, sys, tempfile, threading, time, glob

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
AGENTS = os.path.join(CACHE, "agents.json")     # 兩個 agent CLI 裝了沒、登入了沒，小工具據此畫按鈕
MODELS = os.path.join(CACHE, "agent-models.json")   # 生成時 CLI 回報的模型（Claude 的預設模型跟著帳號，只能這樣知道）
CONFIG = os.path.join(HOME, ".config/pixbg/config.json")
WIDGETS = os.path.join(HOME, ".config/omalauncher/widgets")
STYLE = os.path.join(HOME, ".config/omalauncher/style/style.toml")
BOX = os.path.join(CACHE, "screen-box.json")
GALLERY = os.path.join(HOME, "Pictures/pixbg")  # 生成過的桌布都留在這裡，也可以自己丟圖進來
THUMBS = os.path.join(CACHE, "thumbs")
HISTORY = os.path.join(CACHE, "scene-history")      # 編輯前的舊版場景
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
    _last.clear()
    _last.update({"state": state, "msg": msg, "t": int(time.time()), "job": _job.get("job"),
                  "started": _job.get("started"), "p": p, "to": to if to is not None else p,
                  "eta": eta or 1, "since": int(time.time()), "pid": _job.get("pid", os.getpid()),
                  "beat": int(time.time()), **extra})
    write_json(STATUS, _last)


_last = {}


def beat():
    """心跳：進度不變，只更新 beat。小工具看 beat 判斷生成還活著，程式死掉時不會一直顯示忙碌。"""
    if _last.get("state") == "working" and time.time() - _last.get("beat", 0) >= 3:
        _last["beat"] = int(time.time())
        write_json(STATUS, _last)


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

{task}

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

{example_title}：
```agsl
{example}
```
"""

# 生成和編輯共用 PROMPT，只換「要做什麼」和最後附的程式
GEN_TASK = "使用者的一句話：「{wish}」"
EDIT_TASK = """這次是修改一個已經做好的場景，不是從頭畫。使用者當初的一句話：「{orig}」
現在使用者想這樣改：「{change}」
以最後附的「目前的場景」為基礎，只改使用者要求的部分，其他的構圖、動效、配色、名稱和吉祥物都保持原樣。"""

FIX = """剛才的程式沒有通過檢查（還沒送上手機），問題是：
{err}

請修正後重新輸出完整的 ```agsl 程式碼區塊（同樣的規則，區塊外不要有文字）。原本的程式：
```agsl
{code}
```
"""


NAMES = {"claude": "Claude", "codex": "Codex"}
LOGIN = {"claude": "claude auth login", "codex": "codex login"}
INSTALL = {"claude": "npm i -g @anthropic-ai/claude-code", "codex": "npm i -g @openai/codex"}
STALL = 240     # agent 這麼久沒有任何輸出，就當它卡住了
# agent 在這裡跑：上層沒有 CLAUDE.md、AGENTS.md，不會讀進使用者其他專案的說明，也比較快
AGENT_CWD = os.path.join(tempfile.gettempdir(), "pixbg-agent")


class AgentError(RuntimeError):
    """給使用者看的錯誤；fix 是在終端要打的那行指令（小工具上有複製鍵）。"""
    def __init__(self, msg, fix="", kind=""):
        super().__init__(msg)
        self.fix, self.kind = fix, kind     # kind：login、busy 時可以換另一個 agent 接手


def find_cli(name):
    """agent 的執行檔。小工具的 run() 不一定載入使用者的 shell 設定（mise、npm、bun 加的 PATH），所以也找常見的位置。"""
    hit = shutil.which(name)
    if hit:
        return hit
    for d in ("~/.local/bin", "~/.local/share/mise/shims", f"~/.local/share/mise/installs/{name}/latest/bin",
              f"~/.local/share/mise/installs/{name}/latest", "~/.npm-global/bin", "~/.bun/bin", "/usr/local/bin"):
        path = os.path.join(os.path.expanduser(d), name)
        if os.path.isfile(path) and os.access(path, os.X_OK):
            return path
    return None


def cli_env(exe):
    env = dict(os.environ)
    env["PATH"] = os.path.dirname(exe) + os.pathsep + env.get("PATH", "/usr/bin:/bin")
    return env


def probe(agent):
    """一兩秒內看一個 agent 能不能用：state 是 ready、login（沒登入）、missing（沒裝）或 error。"""
    out = {"id": agent, "name": NAMES[agent], "ok": False, "state": "missing", "version": "", "fix": INSTALL[agent]}
    exe = find_cli(agent)
    if not exe:
        return out
    env = cli_env(exe)
    try:
        v = subprocess.run([exe, "--version"], capture_output=True, text=True, timeout=15, env=env)
        m = re.search(r"\d+\.\d+\.\d+", v.stdout)
        out["version"] = m.group(0) if m else ""
        if agent == "claude":
            r = subprocess.run([exe, "auth", "status"], capture_output=True, text=True, timeout=15, env=env)
            try:
                ok = json.loads(r.stdout).get("loggedIn") is True
            except ValueError:
                ok = False
            ok = ok or bool(os.environ.get("ANTHROPIC_API_KEY"))
        else:
            r = subprocess.run([exe, "login", "status"], capture_output=True, text=True, timeout=15, env=env)
            said = (r.stdout + r.stderr).lower()
            ok = r.returncode == 0 and "logged in" in said and "not logged" not in said
    except (OSError, subprocess.TimeoutExpired):
        out.update(state="error", fix="")
        return out
    out.update(ok=ok, state="ready" if ok else "login", fix="" if ok else LOGIN[agent])
    model = agent_model(agent)
    out["model"] = model_label(model, agent) if model else ""
    return out


def probe_all():
    """兩個 agent 一起查（各自一兩秒），寫進 agents.json 給小工具。"""
    res = {}
    ts = [threading.Thread(target=lambda a=a: res.__setitem__(a, probe(a))) for a in NAMES]
    for t in ts:
        t.start()
    for t in ts:
        t.join()
    data = {"t": int(time.time()), "list": [res[a] for a in NAMES]}
    write_json(AGENTS, data)
    return data


def ready_agent(cfg):
    """生成前先確認選的 agent 能用。它不能用、另一個能用，就換過去（記住）；兩個都不能用，說清楚要在終端打什麼。"""
    info = {a["id"]: a for a in probe_all()["list"]}
    a = info[cfg["agent"]]
    if a["ok"]:
        return cfg, ""
    other = info["codex" if cfg["agent"] == "claude" else "claude"]
    if other["ok"]:
        saved = read_json(CONFIG, {})
        saved.update(agent=other["id"], model="")
        write_json(CONFIG, saved)
        build_ui()
        return {"agent": other["id"], "model": ""}, M("switched", a=a["name"], b=other["name"])
    if a["state"] == "missing":
        raise AgentError(M("missingAgent", agent=a["name"]), a["fix"])
    if a["state"] == "login":
        raise AgentError(M("needLogin", agent=a["name"]), a["fix"])
    raise AgentError(M("agentFailed", agent=a["name"]))


def explain(agent, raw):
    """把 agent 的錯誤換成使用者看得懂、知道下一步的話。"""
    low, name = raw.lower(), NAMES[agent]
    if re.search(r"not (logged|signed) in|please (log|sign) ?in|authenticat|unauthori[sz]ed|\b401\b|invalid api key|oauth|token (has )?expired", low):
        return AgentError(M("needLogin", agent=name), LOGIN[agent], "login")
    if re.search(r"rate.?limit|usage limit|\b429\b|quota|overloaded|\b529\b", low):
        when = re.search(r"try again (?:at|in) ([^.,\n]+)", raw, re.I)
        return AgentError(M("busyAgent", agent=name, when=M("tryAt", t=when.group(1).strip()) if when else ""), kind="busy")
    if re.search(r"enotfound|econnre|getaddrinfo|network|dns|socket hang up|connection (refused|reset)", low):
        return AgentError(M("offline", agent=name))
    lines = [x for x in raw.strip().splitlines() if x.strip()]
    return AgentError(M("agentFailed", agent=name) + (lines[-1][:160] if lines else ""))


def ask_agent(prompt, cfg, on=lambda kind, **kw: None):
    """把提示詞交給 agent，邊讀它的串流邊回報：on("connected", model=…)、on("thinking")、on("writing", text=…)、on("tick")。

    Claude 用 stream-json，一個字一個字收到，進度是真的；Codex 的 --json 只有步驟事件。
    兩個都關掉工具、不留對話紀錄。STALL 秒沒有任何輸出就停掉它，不用等到逾時。
    """
    agent, model = cfg["agent"], cfg.get("model")
    exe = find_cli(agent)
    if exe is None:
        raise AgentError(M("missingAgent", agent=NAMES[agent]), INSTALL[agent])
    if agent == "codex":
        cmd = [exe, "exec", "--json", "--skip-git-repo-check", "--ephemeral", "-s", "read-only"] + (["-m", model] if model else []) + ["-"]
    else:
        cmd = [exe, "-p", "--output-format", "stream-json", "--verbose", "--include-partial-messages",
               "--tools", "", "--no-session-persistence"] + (["--model", model] if model else [])
    os.makedirs(AGENT_CWD, exist_ok=True)
    # 自成一個行程群組：卡住或取消時連它開的子行程一起停掉
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                            text=True, cwd=AGENT_CWD, env=cli_env(exe), process_group=0)
    _agent["proc"] = proc
    lines, err = queue.Queue(), []

    def pump():
        for line in proc.stdout:
            lines.put(line)
        lines.put(None)
    threading.Thread(target=pump, daemon=True).start()
    threading.Thread(target=lambda: err.extend(proc.stderr), daemon=True).start()
    proc.stdin.write(prompt)
    proc.stdin.close()
    text, final, fail, last = "", None, "", time.time()
    while True:
        try:
            line = lines.get(timeout=2)
        except queue.Empty:
            if time.time() - last > STALL:
                kill_agent()
                raise AgentError(M("stalled", agent=NAMES[agent], s=STALL))
            on("tick")
            continue
        if line is None:
            break
        last = time.time()
        try:
            e = json.loads(line)
        except ValueError:
            continue
        t = e.get("type")
        if agent == "claude":
            if t == "system" and e.get("subtype") == "init":
                if e.get("model"):
                    write_json(MODELS, {**read_json(MODELS, {}), agent: e["model"]})
                on("connected", model=e.get("model"))
            elif t == "stream_event":
                d = (e.get("event") or {}).get("delta") or {}
                if d.get("type") == "text_delta":
                    text += d.get("text", "")
                    on("writing", text=text)
                elif d.get("type") == "thinking_delta":
                    on("thinking")
            elif t == "result":
                final = e.get("result") or ""
                if e.get("is_error"):
                    fail = final or str(e.get("subtype"))
        else:
            it = e.get("item") or {}
            if t == "thread.started":
                on("connected")
            elif t == "item.completed" and it.get("type") == "agent_message":
                final = it.get("text", "")
                on("writing", text=final)
            elif t in ("item.started", "item.completed"):
                on("thinking")
            elif t in ("turn.failed", "error"):
                fail = (e.get("error") or {}).get("message") or e.get("message") or t
            else:
                on("tick")
    proc.wait()
    out = final if final else text
    if (fail and agent == "claude") or not out.strip():
        raise explain(agent, fail + "\n" + "".join(err[-20:]))
    m = re.findall(r"```(?:agsl|glsl|sksl|c|cpp)?\s*\n(.*?)```", out, re.S)
    code = max(m, key=len) if m else out
    if "main" not in code:
        raise AgentError(M("noShader", agent=NAMES[agent]))
    return code.strip() + "\n"


_agent = {}


def kill_agent(*_):
    proc = _agent.pop("proc", None)
    if proc and proc.poll() is None:
        try:
            os.killpg(proc.pid, signal.SIGKILL)
        except OSError:
            pass


def model_label(model, agent):
    """給人看的模型名：claude-opus-5-5 → Opus 5.5、opus → Opus、gpt-6-astra → GPT-6-Astra（Codex 的模型清單）；都沒有就用 agent 名。"""
    model = re.sub(r"\[.*\]$", "", model or "")
    m = re.match(r"claude-([a-z]+)-(\d+)-(\d+)", model)
    if m:
        return f"{m.group(1).capitalize()} {m.group(2)}.{m.group(3)}"
    if model in ("opus", "sonnet", "haiku", "fable"):
        return model.capitalize()
    if model and agent == "codex":
        for x in read_json(os.path.join(HOME, ".codex/models_cache.json"), {}).get("models", []):
            if x.get("slug") == model and x.get("display_name"):
                return x["display_name"]
    return model or NAMES[agent]


def agent_model(agent):
    """這個 agent 下次會用的模型：pixbg agent 指定的 > CLI 自己的設定 > 上次生成時 CLI 回報的；都沒有就是空字串。"""
    cfg = read_json(CONFIG, {})
    if cfg.get("agent") == agent and cfg.get("model"):
        return cfg["model"]
    if agent == "codex":
        try:
            m = re.search(r'^model\s*=\s*"([^"]+)"', open(os.path.join(HOME, ".codex/config.toml")).read(), re.M)
            if m:
                return m.group(1)
        except OSError:
            pass
    else:
        set_ = os.environ.get("ANTHROPIC_MODEL") or read_json(os.path.join(HOME, ".claude/settings.json"), {}).get("model")
        if set_:
            return set_
    return read_json(MODELS, {}).get(agent, "")


def gen(wish, edit=None):
    """生成新場景；edit 是要修改的場景 id 時，請 agent 照 wish 改那個場景，通過檢查才覆蓋（舊版先備份）。"""
    _job["job"] = "edit" if edit else "gen"
    extra = {"edit": edit} if edit else {}
    # pixbg cancel 送 SIGTERM 給這個行程：先停掉 agent 那一組再離開
    signal.signal(signal.SIGTERM, lambda *_: (kill_agent(), os._exit(143)))
    status("working", M("connecting", agent=NAMES[config()["agent"]]), p=0.02, to=0.05, eta=8, wish=wish, **extra)
    try:
        cfg, note = ready_agent(config())
    except AgentError as e:
        status("error", str(e)[:300], wish=wish, fix=e.fix, **extra)
        sys.exit(1)
    agent = cfg["agent"]
    who = model_label(cfg.get("model") or agent_model(agent), agent)
    # 每個 agent 各記最近幾次花多久，估進度用（舊版是一個清單，當成 Claude 的）
    times = read_json(os.path.join(CACHE, "gen-times.json"), {})
    times = {"claude": times} if isinstance(times, list) else times
    mine = times.get(agent) or []
    eta = sorted(mine)[len(mine) // 2] if mine else (210 if agent == "claude" else 150)
    with open(os.path.join(SCENES, "10-void.agsl")) as f:
        example = f.read()
    hdr = header()
    _, example_cost = agslcheck.check(hdr, example)
    if edit:
        with open(os.path.join(SCENES, edit + ".agsl")) as f:
            base = f.read()
        orig = meta(base, "prompt") or meta(base, "name") or edit
        prompt = PROMPT.format(task=EDIT_TASK.format(orig=orig, change=wish), wish_line=orig.replace("\n", " "),
                               header=hdr.replace("// ── 場景 ──\n", ""), example_title="目前的場景（要修改的就是它）",
                               example=base, budget=agslcheck.BUDGET, example_cost=round(example_cost))
        expect = len(base) * 1.1    # 改過的程式大約和原本一樣長
        sid = edit
    else:
        prompt = PROMPT.format(task=GEN_TASK.format(wish=wish), wish_line=wish.replace("\n", " "), header=hdr.replace("// ── 場景 ──\n", ""),
                               example_title="參考範例（內建的 VOID SPACE）", example=example, budget=agslcheck.BUDGET,
                               example_cost=round(example_cost))
        expect = len(example) * 1.9     # 回傳的程式實測約是範例的兩倍長，用來估「寫了多少」
        sid = time.strftime("ai-%Y%m%d-%H%M%S")
    t0 = time.time()

    def reporter(lo, hi, retry=""):
        """把 agent 的串流換成進度：連上 → 構思（照 eta 慢慢推到六成，實測佔八成時間）→ 寫程式（照寫了多少字推完）。"""
        st = {"phase": "", "at": 0}
        lead = (note + " · " if note and not retry else "") + retry

        def on(kind, text="", model=None):
            nonlocal who
            now = time.time()
            if kind == "connected" and st["phase"] == "":
                who = model_label(model, agent) if model else who
                st["phase"] = "thinking"
                status("working", lead + M("thinking", who=who, wish=wish), p=lo + 0.04, to=lo + (hi - lo) * 0.6, eta=eta * 0.8, wish=wish, agent=agent, **extra)
            elif kind == "thinking" and st["phase"] == "" :
                on("connected")
            elif kind == "writing" and (st["phase"] != "writing" or now - st["at"] > 1):
                st.update(phase="writing", at=now)
                f = min(1.0, len(text) / expect)
                parts = re.findall(r"^\s*(?:half[34]|float[234]?|void)\s+(\w+)\s*\(", text, re.M)
                where = (parts[-1] + "()") if parts else ""
                p = lo + (hi - lo) * (0.6 + 0.4 * f)
                status("working", lead + M("writing", who=who, n=text.count("\n") + 1, part=where), p=p, to=min(hi, p + 0.03), eta=4, wish=wish, agent=agent, **extra)
            else:
                beat()
        return on

    try:
        code, errs = "", []
        for attempt in range(3):
            lo = [0.05, 0.45, 0.65][attempt]
            retry = M("retry", n=attempt) + errs[0].splitlines()[0][:50] + " · " if attempt else ""
            status("working", (note + " · " if note and not attempt else "") + retry + M("handoffTo", who=who),
                   p=lo, to=lo + 0.04, eta=10, wish=wish, agent=agent, **extra)
            try:
                code = ask_agent(prompt if attempt == 0 else FIX.format(err="\n".join(errs), code=code), cfg, reporter(lo, 0.86, retry))
            except AgentError as e:
                # 額度用完、登入過期：另一個 agent 能用就換它從頭接手（只換一次）
                other = "codex" if agent == "claude" else "claude"
                if e.kind not in ("login", "busy") or note.startswith("↪") or not probe(other)["ok"]:
                    raise
                note = "↪ " + M("switched", a=NAMES[agent], b=NAMES[other])
                cfg, agent, mine = {"agent": other, "model": ""}, other, times.get(other) or []
                who = model_label(agent_model(other), other)
                status("working", note, p=lo, to=lo + 0.04, eta=10, wish=wish, agent=agent, **extra)
                try:
                    code = ask_agent(prompt if attempt == 0 else FIX.format(err="\n".join(errs), code=code), cfg, reporter(lo, 0.86, retry))
                except AgentError as e2:
                    raise AgentError(f"{e} {e2}", e.fix or e2.fix)     # 兩個都不行：兩個原因都說
            if not re.search(r"^//\s*name:", code, re.M):
                code = f"// name: {(meta(base, 'name') if edit else '') or wish[:16]}\n" + code
            if not re.search(r"^//\s*prompt:", code, re.M):
                code = code.replace("\n", f"\n// prompt: {wish}\n", 1)
            # 先在本機檢查，通過了才存進場景、送上手機
            status("working", M("checking"), p=0.88, to=0.92, eta=5, wish=wish, agent=agent, **extra)
            errs, c = agslcheck.check(hdr, code)
            print(f"[{time.strftime('%T')}] {agent} 第 {attempt + 1} 次：{time.time() - t0:.0f}s，運算量 {c:.0f}，{errs or 'ok'}", flush=True)
            if not errs:
                if edit:
                    # 舊版先備份；prompt 留當初那句，每次的修改記成一行 // edit:
                    os.makedirs(HISTORY, exist_ok=True)
                    shutil.copyfile(os.path.join(SCENES, sid + ".agsl"), os.path.join(HISTORY, f"{sid}-{time.strftime('%Y%m%d-%H%M%S')}.agsl"))
                    code = re.sub(r"^//\s*(prompt|edit|name):.*\n", "", code, flags=re.M)
                    if meta(base, "mascot"):
                        code = re.sub(r"^//\s*mascot:.*\n", "", code, flags=re.M)
                        code = f"// mascot: {meta(base, 'mascot')}\n" + code
                    code = f"// name: {meta(base, 'name') or sid}\n" + code     # 編輯不換名字和吉祥物
                    notes = "".join(f"// edit: {x}\n" for x in re.findall(r"^//\s*edit:\s*(.+)$", base, re.M) + [wish.replace("\n", " ")])
                    code = re.sub(r"^(//\s*name:.*\n)", lambda m: m.group(1) + f"// prompt: {orig}\n" + notes, code, count=1, flags=re.M)
                with open(os.path.join(SCENES, sid + ".agsl"), "w") as f:
                    f.write(code)
                build_bundle()
                notify_sel(sid)
                status("working", M("thumbing"), p=0.95, to=0.99, eta=8, wish=wish, agent=agent, **extra)
                try:
                    make_thumbs([sid], force=bool(edit))
                except BaseException:
                    pass
                times[agent] = (mine + [int(time.time() - t0)])[-9:]
                write_json(os.path.join(CACHE, "gen-times.json"), times)
                status("done", M("edited" if edit else "done", name=split_name(meta(code, "name"))[pack(lang())["names"] != "en"], secs=fmt_secs(time.time() - t0)), p=1, wish=wish, id=sid, agent=agent, **extra)
                return
        raise AgentError(M("failed3") + errs[0].splitlines()[0][:160])
    except AgentError as e:
        status("error", str(e)[:300], wish=wish, fix=e.fix, agent=agent, **extra)
        sys.exit(1)
    except Exception as e:
        status("error", str(e)[:300], wish=wish, agent=agent, **extra)
        sys.exit(1)


def gen_running():
    """正在跑的生成的 pid（status.json 記的那個行程還活著才算）。"""
    st = read_json(STATUS, {})
    pid = st.get("pid")
    if st.get("state") != "working" or st.get("job") not in ("gen", "edit") or not pid:
        return None
    try:
        os.kill(pid, 0)
    except OSError:
        return None
    return pid


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
    elif cmd in ("gen", "edit"):
        # pixbg gen <一句話>；pixbg edit <id> <想怎麼改>
        args = [a for a in argv[1:] if a != "--fg"]
        edit = None
        if cmd == "edit":
            edit = args.pop(0) if args else ""
            if not edit.startswith("ai-") or not os.path.exists(os.path.join(SCENES, edit + ".agsl")):
                sys.exit("pixbg: 只能編輯 AI 生成的場景")
        wish = " ".join(args).strip()
        if not wish:
            sys.exit("pixbg gen <一句話> | pixbg edit <id> <想怎麼改>")
        if "--fg" in argv or os.environ.get("PIXBG_FG"):
            gen(wish, edit)
        elif gen_running():
            print(M("already"))
        else:
            # 小工具的 run() 不必等 agent：自己放到背景（自成一個行程群組，取消時整組停掉），進度寫進 status.json
            log = open(os.path.join(CACHE, "gen.log"), "a")
            child = subprocess.Popen([sys.executable, os.path.abspath(__file__), cmd, "--fg"] + ([edit] if edit else []) + [wish],
                                     stdout=log, stderr=log, start_new_session=True)
            _job.update(job=cmd, started=int(time.time()), pid=child.pid)
            status("working", M("handoff"), p=0.02, to=0.04, eta=5, wish=wish, **({"edit": edit} if edit else {}))
    elif cmd == "cancel":
        pid = gen_running()
        if pid:
            try:
                os.killpg(pid, signal.SIGTERM)
            except OSError:
                os.kill(pid, signal.SIGTERM)
            time.sleep(0.3)
            st = read_json(STATUS, {})
            _job.update(job=st.get("job"), started=st.get("started"))
            status("error", M("cancelled"), wish=st.get("wish", ""), **({"edit": st["edit"]} if st.get("edit") else {}))
        print("cancelled" if pid else "nothing running")
    elif cmd == "agents":
        for a in probe_all()["list"]:
            print(f"{'✓' if a['ok'] else '✗'} {a['id']:7} {a.get('model') or '-':14} CLI {a['version'] or '-':10} {a['state']}" + (f"   → {a['fix']}" if a["fix"] else ""))
    elif cmd == "del":
        # 只刪 Agent 生成的場景（連縮圖），刪掉的是目前的場景就換到它前一個
        sid = argv[1] if len(argv) > 1 else current_id()
        if not sid or not sid.startswith("ai-") or not os.path.exists(os.path.join(SCENES, sid + ".agsl")):
            sys.exit("pixbg: 只能刪 AI 生成的場景")
        sc = next((x for x in scenes() if x["id"] == sid), {"name": sid})
        ids = [x["id"] for x in read_json(BUNDLE, {}).get("scenes", [])]
        before = ids[ids.index(sid) - 1] if sid in ids and ids.index(sid) > 0 else (ids[0] if ids else None)
        os.remove(os.path.join(SCENES, sid + ".agsl"))
        if os.path.exists(thumb_path(sid)):
            os.remove(thumb_path(sid))
        build_bundle()
        if before and before != sid and current_id() == sid:
            notify_sel(before)
        _job["job"] = "del"
        status("done", M("deleted", name=split_name(sc["name"])[pack(lang())["names"] != "en"]), p=1)
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
        a = probe_all()["list"][list(NAMES).index(argv[1])]
        print(cfg, a["state"] + (f"  → {a['fix']}" if a["fix"] else ""))
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
