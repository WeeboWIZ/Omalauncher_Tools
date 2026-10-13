# Terminal Voice & Dictation for Omalauncher

Read terminal output aloud and dictate text into Codex, Claude, or another command-line program on Android Omalauncher.

<details open>
<summary><strong>English · shown by default</strong></summary>

## Preview

These screenshots use example text. The English pair shows a Claude terminal connected through tmux. Tap an image to view it at full size.

| Terminal Voice | Dictation |
|:---:|:---:|
| [![English Terminal Voice widget](docs/codex-voice-en.png)](docs/codex-voice-en.png) | [![English Dictation widget](docs/dictation-en.png)](docs/dictation-en.png) |

## What it does

- **Codex chat mode:** follows the latest local Codex conversation, displays completed replies and can automatically read a summary aloud. Dictation is sent through Omalauncher's `codex queue` command.
- **Terminal mode:** reads the visible text of a dedicated tmux pane and sends dictated text to it when you tap **Send to target**. Start Codex, Claude, or another terminal program in that pane. Terminal playback is manual so changing prompts and progress messages are not read aloud repeatedly.
- Both home-screen widgets and the browser dictation page share one interface language: English (default), 中文, Español, Deutsch, Français, 日本語 or 한국어. A reply is read aloud in its own language with a matching voice. The reply or dictated text stays in its original language.
- The voice widget offers summary/full-screen playback, stop, refresh, source selection, and a detailed view. Online speech converts to playable WAV; offline speech uses espeak-ng.

## Install

Requires Omalauncher with Arch Linux, OWL 5 support, and a working audio output.

**From the widget store:** install **終端播報** (Terminal Voice) and **語音輸入** (Dictation), then tap **Set up** on either tile. Setup writes the programs to `~/.local` and installs edge-tts for online speech; it covers both widgets.

**From this repository:**

```sh
git clone https://github.com/WeeboWIZ/Omalauncher_Tools.git
cd Omalauncher_Tools
python install.py
```

You can also download the repository ZIP, extract it, and run `python install.py` there. The installer adds two home-screen widgets and installs Python, curl, util-linux, espeak-ng, libpulse, mpg123, tmux, and an isolated Python environment for edge-tts. Use `python install.py --skip-deps` only when these dependencies and the TTS environment already exist.

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

The repository contains no conversation logs, drafts, tokens, audio files, models, or virtual environments. Your Codex logs remain under `~/.codex/sessions/`; voice settings and output under `~/.config/omalauncher/voice.json` and `~/.cache/oma-voice/`; dictation text under `~/.cache/oma-speak/` and browser local storage. Terminal mode reads only the dedicated `oma-voice` tmux session. Online TTS sends the text being spoken to Microsoft Edge TTS. Browser speech recognition may use the browser provider's online service. Select offline speech to use local espeak-ng. The dictation page listens only on `127.0.0.1:18763` and checks an origin and random token before saving text.

Run `python -m unittest discover -s tests -v` to check the package. `python tools/build_store.py` rebuilds the store folders under `store/`; see `docs/STORE_PLAN.md`. You can preview a widget after installation with `owl-check ~/.config/omalauncher/widgets/46-speak.owl`.

</details>

<details>
<summary><strong>中文 · 點擊展開</strong></summary>

## 工具畫面

截圖使用示例文字。中文組展示 Codex 會話模式；英文組展示透過 tmux 連接 Claude。點圖片可查看原尺寸。

| 終端播報 | 語音輸入 |
|:---:|:---:|
| [![中文終端播報工具](docs/codex-voice.png)](docs/codex-voice.png) | [![中文語音輸入工具](docs/dictation.png)](docs/dictation.png) |

## 功能

- **Codex 會話模式：** 跟隨本機最近活動的 Codex 對話，顯示已完成回覆，可自動播報摘要。語音輸入經 Omalauncher 的 `codex queue` 送入對話。
- **終端模式：** 讀取指定 tmux 窗格的可見文字；點「送到目前目標」後將聽寫文字送入該窗格。可以在裡面運行 Codex、Claude 或其他命令列程式。終端畫面採手動播報，避免進度訊息重複朗讀。
- 兩個首頁工具及瀏覽器聽寫頁共用中英文介面切換；回覆和聽寫內容保留原語言。
- 播報工具可播放摘要或全文、停止、同步、選擇來源及查看詳情。線上語音會轉成可播放的 WAV；離線語音使用 espeak-ng。

## 安裝

需要 Omalauncher 的 Arch Linux、OWL 5 支援和可用的音訊輸出。

**從小工具商店安裝：** 安裝「終端播報」與「語音輸入」，在任一個小工具上按「安裝」。安裝會把程式寫入 `~/.local` 並下載 edge-tts 線上語音，一次完成兩個小工具。

**從本倉庫安裝：**

```sh
git clone https://github.com/WeeboWIZ/Omalauncher_Tools.git
cd Omalauncher_Tools
python install.py
```

也可下載倉庫 ZIP 並解壓，在目錄內執行 `python install.py`。安裝程式會加入兩個首頁工具，並安裝 Python、curl、util-linux、espeak-ng、libpulse、mpg123、tmux 和 edge-tts 的獨立 Python 環境。只有依賴和語音環境都已具備時才使用 `python install.py --skip-deps`。

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

倉庫不包含對話紀錄、草稿、Token、音檔、模型或虛擬環境。Codex 記錄位於 `~/.codex/sessions/`；播報設定和快取位於 `~/.config/omalauncher/voice.json`、`~/.cache/oma-voice/`；聽寫文字位於 `~/.cache/oma-speak/` 和瀏覽器本機儲存。終端模式只讀取指定的 `oma-voice` tmux 工作階段。線上語音會把朗讀文字傳給 Microsoft Edge TTS；瀏覽器語音辨識也可能使用供應商的線上服務。選擇離線語音則使用本機 espeak-ng。聽寫頁只監聽 `127.0.0.1:18763`，保存時檢查來源與隨機 Token。

執行 `python -m unittest discover -s tests -v` 可檢查分享包；`python tools/build_store.py` 重新產生 `store/` 下的商店版本，流程見 `docs/STORE_PLAN.md`。安裝後以 `owl-check ~/.config/omalauncher/widgets/46-speak.owl` 預覽首頁和詳情頁。

</details>
