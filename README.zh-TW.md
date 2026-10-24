# Rime LLM Translator

[English](README.md) · [简体中文](README_CN.md) · [繁體中文](https://github.com/LE-saber/rime-llm-translator/blob/main/README.zh-TW.md) · [日本語](https://github.com/LE-saber/rime-llm-translator/blob/main/README.ja.md)

[下載 v0.3.0](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) · [變更紀錄](CHANGELOG.md)

為 **Ubuntu 24.04 amd64、GNOME 46、IBus 與朙月拼音**提供中文輸入、輕量離線翻譯與可選雲端 AI。保留繁體中文輸入；Windows 與其他桌面環境不在本版支援範圍。

正常輸入即可取得英文/日文翻譯候選，也可在懸浮編輯器修訂長篇中文再送出譯文。原生 GTK3、C/IBus 及 CPU-only Bergamot INT8 共用一個離線推論程序。模型已隨包提供，不需 pip、GPU、本機編譯或首次執行下載。

## 畫面

可編輯的大型原文區、精簡語言預覽、圖示工具與可設定的 AI 送出：

![原生淺色懸浮編輯器](docs/images/long-text-light.png)

AI 處理時顯示轉圈與經過秒數：

![AI 翻譯進度](docs/images/ai-sending.png)

[深色編輯器](docs/images/long-text-dark.png) · [GUI 設定](docs/images/settings.png)。截圖由 GitHub Actions 的原生 GTK 測試程式以公開文字及本機模擬 API 產生，示範介面與互動。

## 安裝或升級

從 [Release](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) 下載 `.deb` 與 `SHA256SUMS` 到同一目錄：

```bash
sha256sum --check SHA256SUMS
sudo apt install ./rime-llm-translator_0.3.0_amd64.deb
```

新安裝：

```bash
rime-llm-translator setup && rime-llm-translator enable
```

從預覽版升級，保留 API Key 與偏好：

```bash
rime-llm-translator sync && rime-llm-translator enable
```

除 APT 外，請以桌面使用者執行命令。**登出後重新登入**，到設定 → 鍵盤 → 輸入來源新增中文 → Rime Translator；必要時以 Ctrl+grave 選擇朙月拼音。`sync` / `enable` 會安裝使用者層級 GNOME 橋接；若全域停用使用者擴充功能，先在 GNOME Extensions 啟用。`doctor` 應顯示懸浮面板橋接 active。

原本 Rime 保持獨立，本引擎使用 `~/.config/ibus/rime-llm`。離線英文/日文不需憑證。用 `rime-llm-translator settings` 或應用程式選單開啟設定。

## 使用方式

| 操作 | 行為 |
| --- | --- |
| 一般中文組字 | 原生中文候選加上 `🌐 MT · EN/JA`；稍後結果不需再按鍵就會刷新 |
| AI 快捷鍵，預設 Ctrl+Shift+Enter | 明確對所選中文候選呼叫 API 修訂，不自動提交 |
| 開啟編輯器，預設 Alt+Space | 空白、可縮放、置頂面板；所選中文保留於歷史 |
| 在面板編輯 | Rime 選字累積到原文區，離線預覽隨編輯更新 |
| 送出，預設 Ctrl+Enter | 將預覽語言送至最近選取的真實輸入欄位，成功後清空 |
| 原文為空時按 ↑ / ↓ | 取回本機歷史，含未送出就關閉的草稿 |

目標跟隨面板開啟期間最後選取的真實輸入欄位：從 A 開啟，選 B，再回面板即送至 B；同一視窗不同欄位亦適用。面板和設定欄位不會成為目標。GNOME 整合會還原並檢查目標；目標關閉/無效或提交失敗會保留原文。不使用全域貼上或模擬打字。

**即時預覽使用離線 MT。設定 API URL、模型及非空 Key 後，AI 送出預設啟用，可手動關閉。** 手動 AI 只影響目前文字/語言；編輯、換語言或送出成功後回到 MT 預覽。AI 失敗、逾時、過期或截斷輸出不會默默改送 MT。只有明確請求的 AI 操作會上傳文字。

可在 GUI 錄製快捷鍵，也支援 DoubleAlt / TripleAlt 及面板內滑鼠側鍵。Alt+Space 可能與 GNOME 視窗選單衝突，可改用 Ctrl+Alt+Space。開啟依賴 Rime Translator 收到鍵盤事件，不是全桌面快捷鍵。CLI 範例：

```bash
rime-llm-translator hotkey DoubleAlt
```

Double Alt 要求選取中文候選時，在 400 ms 內完整點按同一 Alt 兩次。桌面/虛擬機宿主可能攔截快捷鍵，詳見[長文行為與驗收](docs/LONG_TEXT.md)。

## 資源與限制

- 一個原生推論程序/執行緒，同時只載入一個模型方向；閒置 60 秒結束子程序。面板按需載入，無瀏覽器執行環境。
- 中文→英文 tiny 模型；日文經英文→日文 base-memory 中轉。OpenCC 只正規化 MT 副本，AI 收到原始中文。譯文僅為基礎草稿，姓名、數字及否定尤其需人工確認；上游 tiny 模型在登錄表未標示為 Release。
- CPU/虛擬機須提供 SSE4.1。一般候選上限 1,200 UTF-8 bytes；面板上限 32 KiB，按順序分塊翻譯。離線語言為英文/日文，其他設定語言需 AI。
- MT/AI 服務與快取分開，各 350 項 / 10 MiB。日誌不記原文、譯文與 Key。可選本機歷史最多 50 筆去重資料，可清除或停用。

Release 的 `RESOURCE_REPORT.md` 與 `mt-benchmark.json` 包含該構建的套件大小、磁碟、RSS、延遲與公開譯文樣本。系統依賴另計，runner 數據不代表虛擬機效能。

## 診斷、清理與開發

```bash
rime-llm-translator doctor
rime-llm-translator install-offline
rime-llm-translator cleanup-legacy
rime-llm-translator cleanup-legacy --apply
```

`install-offline` 驗證隨包資源；`cleanup-legacy` 先檢視，加入 `--apply` 才移除選定舊檔。清理保留 Key、設定、歷史及 Rime 字典，共用 pip 快取/Argos 模型需額外明確選項。見[升級清理](docs/UPGRADE_CLEANUP.md)、[人工驗收](docs/MANUAL_TEST.md)、[建置](docs/DEVELOPMENT.md)與[變更](CHANGELOG.md)。

GitHub Actions 定義 Ubuntu 24.04 套件安裝、單元測試、真實 Rime/IBus/GTK、GNOME 46 Wayland 焦點/提交、模擬 AI 失敗與斷網原生推論檢查，不使用 WSL。實際雲端品質和使用者應用/虛擬機仍需人工驗收。

## 原始碼與授權

前端衍生自 GPLv3-or-later 的 [ibus-rime 1.5.0](https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3)，原始碼與授權在 [frontend/](frontend/) 及安裝包。Mozilla 推論源碼、固定版本依賴和授權文字在 `/usr/share/doc/rime-llm-translator/inference-source.tar.xz`，附有包裝層原始碼及版本。Mozilla 模型採 MPL 2.0，雜湊/授權見 [models.lock.json](native/mt/models.lock.json)。第三方元件保留各自授權。根目錄的 Ollama Lua 原型只是未使用的上游參考，不是安裝後執行路徑。

此繁體中文與日文介紹為線上文件；既有 v0.3.0 安裝包僅隨附原先的英文/簡體中文文件，未因文件 PR 重新打包。
