# Omalauncher Tools

## DEV LOGS

Development logs, Markdown project notes and filtered Linux diagnostics, with English and Traditional Chinese settings. Log entries are stored in one file per month and browsed by day. Agent logging instructions are available under Settings.

See the [DEV LOGS README, installation guide and screenshots](dev-logs/README.md). Install it independently with `python dev-logs/install.py`; the root installer below continues to install Terminal Voice and Dictation.

![DEV LOGS home widget](dev-logs/docs/screenshots/dev-logs.png)

## Terminal Voice & Dictation for Omalauncher

Read terminal output aloud and dictate text into Codex, Claude, or another command-line program on Android Omalauncher.

<details open>
<summary><strong>English · shown by default</strong></summary>

## Preview

These screenshots use fixed English example text and the launcher's actual rendering. Both tiles are shown at their default size of 3×4 cells. Each PNG is below 300 KB. See the [English screenshot review](docs/screenshots/README.md) for details. Tap an image to view it at full size.

| Terminal Voice | Dictation |
|:---:|:---:|
| [![English Terminal Voice widget](docs/screenshots/terminal-voice.png)](docs/screenshots/terminal-voice.png) | [![English Dictation widget](docs/screenshots/dictation.png)](docs/screenshots/dictation.png) |

## What it does

- **Codex chat mode:** follows the latest local Codex conversation, displays completed replies and can automatically read a summary aloud. Dictation is sent through Omalauncher's `codex queue` command.
- **Terminal mode:** reads the visible text of a dedicated tmux pane and sends dictated text to it when you tap **Send to target**. Start Codex, Claude, or another terminal program in that pane. Terminal playback is manual so changing prompts and progress messages are not read aloud repeatedly.
- Both home-screen widgets and the browser dictation page share one interface language: English (default), 中文, Español, Deutsch, Français, 日本語 or 한국어. A reply is read aloud in its own language with a matching voice. The reply or dictated text stays in its original language.
- Change the interface language in either widget's **Details** screen or in the dictation page. The home tiles keep their controls focused on playback and dictation.
- The voice widget offers summary/full-screen playback, stop, refresh, source selection, and a detailed view. Online speech converts to playable WAV; offline Chinese and English use Matcha on ARM64 when installed, with espeak-ng as the fallback.

## Offline voice model and samples

The offline Chinese-English neural voice is **Matcha `matcha-icefall-zh-en`**, run locally with the sherpa-onnx 1.13.8 ARM64 runtime and the Vocos 16 kHz vocoder. On ARM64, run the installer or tap **Set up**/**Update** on either widget to download the runtime and model. The model weights are not stored in this repository. Other languages, and unsupported architectures, use espeak-ng offline. Online mode remains available through Microsoft Edge TTS.

- Model details and browser samples: [Matcha icefall zh-en](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/matcha-icefall-zh-en.html).
- Model download: [sherpa-onnx TTS model release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models); Vocos vocoder: [vocoder release](https://github.com/k2-fsa/sherpa-onnx/releases/tag/vocoder-models).
- Listen to samples generated with this model: [Chinese sample](docs/audio/matcha-chinese.wav) · [English sample](docs/audio/matcha-english.wav).

## Install

Requires Omalauncher with Arch Linux, OWL 5 support, and a working audio output.

**From the widget store:** install **終端播報** (Terminal Voice) and **語音輸入** (Dictation), then tap **Set up** on either tile. Setup writes the programs to `~/.local` and installs edge-tts for online speech; it covers both widgets.

**From this repository:**

```sh
git clone https://github.com/WeeboWIZ/Omalauncher_Tools.git
cd Omalauncher_Tools
python install.py
```

You can also download the repository ZIP, extract it, and run `python install.py` there. The installer adds two home-screen widgets and installs Python, curl, util-linux, espeak-ng, libpulse, mpg123, tmux, and an isolated Python environment for edge-tts. On ARM64, it also downloads Matcha and its Vocos vocoder. Use `python install.py --skip-deps` only when these dependencies and the TTS environment already exist.

## Use with Codex or Claude

The default source is **Codex chat**, preserving existing users' behavior. Open **Details** on the voice widget to select **Terminal / Claude** when you want terminal access. In the terminal window you already use, run:

```sh
tmux new -A -s oma-voice
```

Then start `claude`, `codex`, or any other CLI inside that tmux session. The voice widget's **Play** button reads the current pane. The Dictation widget's **Send to target** button submits saved text to that pane with Enter. The voice widget includes a button that copies the tmux command. You can leave the tmux session with `Ctrl+B`, then `D`; return with the same command. A terminal window opened outside this tmux session cannot be captured or typed into by this tool.

For Codex chat mode, open or resume a local Codex chat and tap **Sync**. Completed replies update automatically. Sync never replays an old answer. The voice service pauses after 10 minutes with the tile off screen and no Codex activity, and resumes when the tile is back; **Idle pause** in the voice settings changes the time or turns the pause off. This mode needs Omalauncher's `codex queue` for sending; if your Codex build lacks it, copy the dictated text and paste it yourself.

Dictation uses browser speech recognition. Choose a speech language, tap Start, stop, edit, and save. Then tap **Send to target** on the home screen. The browser must grant microphone permission; Chrome is recommended.

## Update and data

Download or pull the latest version and rerun `python install.py`. It preserves personal settings and draft text and backs up replaced program files under `~/.local/share/oma-voice/install-backups/`. Restart Linux if an older voice service is still running. The widgets hold their background programs: after importing or updating only the `.owl` files, tap **Set up** or **Update** on the tile.

The repository contains no conversation logs, drafts, tokens, model weights, or virtual environments; the WAV files above are public demo samples. Your Codex logs remain under `~/.codex/sessions/`; voice settings and output under `~/.config/omalauncher/voice.json` and `~/.cache/oma-voice/`; dictation text under `~/.cache/oma-speak/` and browser local storage. Terminal mode reads only the dedicated `oma-voice` tmux session. Online TTS sends the text being spoken to Microsoft Edge TTS. Browser speech recognition may use the browser provider's online service. Select offline speech for local Matcha Chinese or English when installed, with espeak-ng as fallback. The dictation page listens only on `127.0.0.1:18763` and checks an origin and random token before saving text.

Run `python -m unittest discover -s tests -v` to check the package. `python tools/build_store.py` rebuilds the store folders under `store/`; see `docs/STORE_PLAN.md`. You can preview a widget after installation with `owl-check ~/.config/omalauncher/widgets/46-speak.owl`.

</details>

<details>
<summary><strong>中文 · 點擊展開</strong></summary>

## 工具畫面

截圖採用英文示例文字，展示透過 tmux 連接 Claude；介面仍支援繁體中文。點圖片可查看原尺寸。

| 終端播報 | 語音輸入 |
|:---:|:---:|
| [![終端播報工具](docs/screenshots/terminal-voice.png)](docs/screenshots/terminal-voice.png) | [![語音輸入工具](docs/screenshots/dictation.png)](docs/screenshots/dictation.png) |

## 功能

- **Codex 會話模式：** 跟隨本機最近活動的 Codex 對話，顯示已完成回覆，可自動播報摘要。語音輸入經 Omalauncher 的 `codex queue` 送入對話。
- **終端模式：** 讀取指定 tmux 窗格的可見文字；點「送到目前目標」後將聽寫文字送入該窗格。可以在裡面運行 Codex、Claude 或其他命令列程式。終端畫面採手動播報，避免進度訊息重複朗讀。
- 兩個首頁工具及瀏覽器聽寫頁共用中英文介面切換；回覆和聽寫內容保留原語言。
- 播報工具可播放摘要或全文、停止、同步、選擇來源及查看詳情。線上語音會轉成可播放的 WAV；ARM64 上的中英文離線播報在 Matcha 已安裝時使用 Matcha，否則使用 espeak-ng。

## 離線語音模型與試聽

離線中英雙語神經語音使用 **Matcha `matcha-icefall-zh-en`**，透過 sherpa-onnx 1.13.8 ARM64 執行環境在本機運行，並搭配 Vocos 16 kHz 聲碼器。ARM64 裝置執行安裝程式，或在任一小工具點「安裝／更新」，即可下載執行環境和模型；模型權重不放在此倉庫。其他語言及不支援的架構會使用 espeak-ng。線上語音仍可選 Microsoft Edge TTS。

- 模型介紹與網頁試聽：[Matcha icefall zh-en](https://k2-fsa.github.io/sherpa/onnx/tts/all/Chinese-English/matcha-icefall-zh-en.html)。
- 模型下載：[sherpa-onnx TTS 模型發佈頁](https://github.com/k2-fsa/sherpa-onnx/releases/tag/tts-models)；Vocos 聲碼器：[發佈頁](https://github.com/k2-fsa/sherpa-onnx/releases/tag/vocoder-models)。
- 本機模型生成的語音樣片：[中文試聽](docs/audio/matcha-chinese.wav) · [English sample](docs/audio/matcha-english.wav)。

## 安裝

需要 Omalauncher 的 Arch Linux、OWL 5 支援和可用的音訊輸出。

**從小工具商店安裝：** 安裝「終端播報」與「語音輸入」，在任一個小工具上按「安裝」。安裝會把程式寫入 `~/.local` 並下載 edge-tts 線上語音，一次完成兩個小工具。

**從本倉庫安裝：**

```sh
git clone https://github.com/WeeboWIZ/Omalauncher_Tools.git
cd Omalauncher_Tools
python install.py
```

也可下載倉庫 ZIP 並解壓，在目錄內執行 `python install.py`。安裝程式會加入兩個首頁工具，並安裝 Python、curl、util-linux、espeak-ng、libpulse、mpg123、tmux 和 edge-tts 的獨立 Python 環境。ARM64 裝置也會下載 Matcha 和 Vocos 聲碼器。只有依賴和語音環境都已具備時才使用 `python install.py --skip-deps`。

## 使用 Codex 或 Claude

預設是 **Codex 會話**，延續已安裝使用者的行為。想操作終端時，在播報工具的「詳情」選 **終端 / Claude**，然後在你原本使用的終端視窗輸入：

```sh
tmux new -A -s oma-voice
```

進入後在該 tmux 工作階段啟動 `claude`、`codex` 或其他命令列程式。「播放」會朗讀目前窗格畫面；語音輸入首頁的「送到目前目標」會把保存的文字送到該窗格並按 Enter。播報工具提供「複製終端連接命令」按鈕。按 `Ctrl+B`，再按 `D` 可暫時離開，重新輸入相同命令即可返回。沒有進入這個 tmux 工作階段的普通終端視窗，工具無法直接讀取或輸入。

使用 Codex 會話模式時，開啟或恢復本機對話，按「同步」。正式回覆完成後自動更新；同步不會重播歷史回覆。小工具不在畫面上、Codex 也沒有動靜超過 10 分鐘，播報服務會暫停，回到畫面時自動恢復；可在播報設定的「閒置暫停」改時間或設為無限制。送入對話需 Omalauncher 的 `codex queue`；若使用的 Codex 沒有該命令，可複製聽寫文字再手動貼上。

語音輸入使用瀏覽器語音辨識。選好語音語言，開始、停止、修改並保存，最後回首頁按「送到目前目標」。瀏覽器需授予麥克風權限，建議使用 Chrome。

## 更新與資料

下載最新版本並重新執行 `python install.py`。安裝會保留個人設定與草稿，並把舊程式備份到 `~/.local/share/oma-voice/install-backups/`。若舊播報服務仍在運行，重啟 Linux 載入新程式。小工具內含背景程式：只匯入或更新 `.owl` 檔時，在小工具上按「安裝」或「更新」即可。

倉庫不包含對話紀錄、草稿、Token、模型權重或虛擬環境；前述 WAV 是公開語音樣片。Codex 記錄位於 `~/.codex/sessions/`；播報設定和快取位於 `~/.config/omalauncher/voice.json`、`~/.cache/oma-voice/`；聽寫文字位於 `~/.cache/oma-speak/` 和瀏覽器本機儲存。終端模式只讀取指定的 `oma-voice` tmux 工作階段。線上語音會把朗讀文字傳給 Microsoft Edge TTS；瀏覽器語音辨識也可能使用供應商的線上服務。ARM64 選擇離線語音時，中英文使用本機 Matcha（若已安裝），其他情況使用 espeak-ng。聽寫頁只監聽 `127.0.0.1:18763`，保存時檢查來源與隨機 Token。

執行 `python -m unittest discover -s tests -v` 可檢查分享包；`python tools/build_store.py` 重新產生 `store/` 下的商店版本，流程見 `docs/STORE_PLAN.md`。安裝後以 `owl-check ~/.config/omalauncher/widgets/46-speak.owl` 預覽首頁和詳情頁。

</details>
