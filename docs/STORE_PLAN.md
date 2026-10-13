# 上架 Omalauncher 商店：工作計劃

目標：產出可直接投稿到 [SimonSchubert/omarchy-widgets](https://github.com/SimonSchubert/omarchy-widgets) 的版本。
**送出（fork 推送、開 PR 或 issue）前必須先給倉庫擁有者確認。**

協作約定：多個 agent 共用本倉庫。提交只用倉庫的 git 使用者，不加任何 agent 署名。工作分支為 `store-release`。

## 商店的限制

- 每個 widget 一個資料夾 `widgets/weebowiz/<name>/`，只能放 `widget.owl`、`preview.png`、`README.md`、`previews/<theme>.webp`。
- `widget.owl` 上限 256 KB；`meta` 需要 `description`（10–200 字元）、`version`、`license`，`category` 須在固定清單內。
- 命令裡的變數只能以 `${sh(value)}` 帶入；不可含個人路徑或 token；更新必須提高 `version`。
- 背景程式不能另外附檔，所以要內嵌在 `widget.owl`，由使用者按「安裝」寫入 `~/.local`。

## 做法

`widgets/*.owl` 是範本，`tools/build_store.py` 把 `voice/`、`dictation/`、`bin/` 內嵌成安裝腳本後輸出到 `store/widgets/weebowiz/`。
`install.py` 用同一個函式產生 widget，所以 GitHub 安裝與商店安裝得到相同的 widget。

| 商店名稱 | 範本 | 輸出 |
|---|---|---|
| `terminal-voice` | `widgets/46-speak.owl` | `store/widgets/weebowiz/terminal-voice/` |
| `dictation` | `widgets/47-voice-input.owl` | `store/widgets/weebowiz/dictation/` |

兩個 widget 內嵌同一份程式與同一個版本標記（`~/.local/share/oma-voice/store-version`），任一個裝過，另一個就直接可用。

## 進度

- [x] 換行統一為 LF（`.gitattributes`），避免腳本在 Linux 因 CRLF 失敗
- [x] 範本改用 `~` 路徑，補齊 `requires`，加入安裝／更新畫面
- [x] `tools/build_store.py` 產生商店版，`install.py` 共用
- [x] 測試：商店輸出與原始碼同步、無個人路徑、大小在限制內
- [x] 用商店的 `tools/owl.jar review` 檢查
- [x] 在手機上實測：`owl-check`、內嵌安裝腳本、自然語音播放、語音輸入送出、麥克風
- [x] 用手機重繪的乾淨截圖更新 `preview.png`（保存在 `store/` 內，打包腳本不會覆蓋）
- [x] 擁有者確認後開 PR：https://github.com/SimonSchubert/omarchy-widgets/pull/82 （CI 通過，等待維護者審核）
- [x] 依維護者審核意見修改（3.2）：狀態檔只在變動時寫入；沒有會話或 tmux 時每 15 秒才檢查；閒置後暫停服務（預設 10 分鐘，可自訂或設為無限制）
- [x] 手機複驗 3.2：按鈕正常，熄屏後完成的工作仍會播報；已推到 PR 分支並回覆維護者
- [x] PR #82 已合併，兩個小工具以 3.2 上架
- [ ] 3.3（本機已完成，待擁有者手機測試並確認後開更新 PR）：
  - 商店顯示的名稱、說明、預覽圖改為英文；介面預設英文（3.3 之前安裝且沒選過語言的維持中文）
  - 介面七種語言：English、中文、Español、Deutsch、Français、日本語、한국어，全部內建，點語言按鈕切換
  - 回覆以它自己的語言朗讀（依文字判斷，判斷不出來用介面語言），線上與離線語音都對應
  - 西、德、法、日、韓文翻譯沒有母語者校對
- [ ] 之後：工作完成時的手機通知
- [ ] PR 合併後把 `store-release` 合併回 `main`

## 投稿時踩到的商店 CI 規則

- 檔案不能帶可執行權限（從 Windows 磁碟複製時會帶上，提交前 `chmod 644`）。
- 命令的第一個字必須是 Arch 套件提供的程式；自己安裝的 `oma-voice`、`speak` 會讓套件檢查中止，所以改由 `python`、`bash` 呼叫。
- 商店頁面直接顯示 `widget "名稱"`、`description` 和 `preview.png`，不會跟著介面語言切換，所以這三樣用英文。
- 在 proot 內 `id -u` 是 0，但行程屬於 App 的實際使用者，不要用 `pkill -u`。

## 播報服務何時運行

`ensure` 每次被呼叫都更新 `~/.cache/oma-voice/alive`。這個檔案和 Codex 會話記錄都超過「閒置暫停」時間沒有變動，服務就結束；正在播放時不結束。小工具回到畫面時 `ensure` 會重新啟動它。
設定存在 `voice.json` 的 `pause_minutes`（預設 10，0 表示無限制），可在播報設定裡切換或輸入 1–1440，或執行 `oma-voice pause <分鐘|off>`。
小工具用 `ensure` 的結束碼判斷服務是否離線，不再看 `checked_at`。

手機複驗 3.2 清單：
1. 小工具顯示「更新」，更新後播放、停止、同步、中英切換、語音輸入送出正常。
2. 交代 Codex 一件工作後熄屏，完成時仍自動播報（預設 10 分鐘，以及設為無限制各試一次）。
3. 詳情頁「閒置暫停」按鈕可切換 10 分鐘／無限制，輸入框送出自訂分鐘數後按鈕文字更新。
4. 設成 1 分鐘，離開小工具所在頁面 2 分鐘後 `pgrep -f 'oma_voice.py daemon'` 沒有結果；回到頁面 30 秒內服務恢復，且不顯示「服務離線」。
5. 沒有 Codex 會話時 `~/.cache/oma-voice/state.json` 的修改時間不再每秒變動。

## 語言

介面文字有三處，新增語言要三處都加：
- 小工具：`tools/ui_strings.py`（英文為鍵）。範本裡寫 `_("English text")`，打包時展開成各語言。
- 播報服務的狀態與錯誤：`voice/language.py` 的 `MESSAGES`（中文為鍵）。服務把目前語言的文字寫進 `state.json` 的 `status_ui`、`error_ui`。
- 聽寫網頁：`dictation/index.html` 的 `UI_STRINGS`，以及 `dictation/server.py` 的 `LANGUAGES`。

朗讀語音在 `voice/synthesize.py` 的 `SPEAKERS`，朗讀語言由 `voice/language.py` 的 `spoken()` 判斷。
商店檢查器把 `su` 加空白當成要求 root，翻譯裡不能出現（例如西班牙文的 su）。

## 改了程式之後

1. 修改 `voice/`、`dictation/`、`bin/` 或範本。
2. 提高 `tools/build_store.py` 的 `VERSION`。
3. 執行 `python tools/build_store.py`，再跑 `python -m unittest discover -s tests -v`。
4. 在商店倉庫內檢查：`java -jar tools/owl.jar review . widgets/weebowiz/<name>/widget.owl`。
