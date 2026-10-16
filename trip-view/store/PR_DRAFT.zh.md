新增 weebowiz/trip-view：像素動畫場景，還能請 agent 畫新的

## 摘要
- **場景：** 五個手工像素動畫（霓虹拉麵、特攝片場、虛空、螢光森林、代碼雨），各有五組配色、一隻像素寵物，像素時鐘和 8-bit 音效可選。2×2 到整頁都能放。
- **全螢幕頁：** 場景滿版；有附縮圖的場景卡片、配色、速度。**隱藏介面**只剩場景，點一下叫回來。
- **Agent：** 用一句話描述心情，Codex 或 Claude 寫出新場景。按鈕下顯示 CLI 有沒有裝、有沒有登入，以及使用的模型；不能用時給一行可複製的終端指令。進度即時（Claude 逐行、Codex 逐步），可取消；agent 四分鐘沒回應就停止；一個未登入或額度用完時，另一個接手。
- **管理：** 生成的場景名稱下有一行小字，點開有**編輯**（agent 只改你說的部分，舊版保留）和**刪除**（寫明場景名並要再確認）。
- **桌布：** 把任何一刻定格成啟動器背景，每張都留在 `~/Pictures/pixbg`。
- 只有英文；**Language → Custom** 給一段提示詞，可新增任何語言。

## 給審查者
- **Set up** 把 `widget.owl` 裡的 Python 程式、場景和英文語言包寫到 `~/.local/share/pixbg`，並在 `~/.local/bin` 加上 `pixbg`／`tripview`。不下載任何東西。更新時保留生成的場景和設定，被取代的檔案先備份。
- 每個 shader（內建或生成）送上手機前都通過離線檢查：glslangValidator、AGSL 規則、每像素 GPU 預算。生成失敗會交回 agent 修正，最多三次。
- Agent 執行時不開工具（`claude --tools ""`、`codex -s read-only`）、不留對話紀錄、在自己的暫存資料夾、用使用者自己的帳號。`claude`、`codex` 為選用，不在 `requires`；內建場景兩者都不需要。
- **設為桌布**把圖複製到主題的背景資料夾（`~/.config/omarchy/backgrounds/<主題>/`，只替換它自己先前放的 `pixbg-*`），並設定啟動器 `style.toml` 的 `background` 一行。
- 審查提示「uses eval」：是 AGSL 檢查器用正規表示式擋掉 shader 裡的 `eval` 字樣，沒有執行任何 eval。
- `widget.owl` 161 KB；安裝指令 114 KB，在 Linux 參數長度上限內；`preview.png` 47 KB。

## 驗證
- `owl.jar review` 通過。19 個單元測試涵蓋：暫存家目錄裡的安裝、用假 Claude／Codex 跑串流、錯誤訊息、卡住偵測、場景編輯、shader 檢查。
- Claude Code 和 Codex 各實際生成一次，通過檢查並出現在手機上；實際用 agent 編輯生成的場景，效果符合描述。
- 手機上檢查過：帶模型名稱的 agent 按鈕、修復指令面板、管理／編輯／刪除確認、隱藏模式、小卡。
