# Rime LLM Translator — 离线机翻 + 按键 AI 修正

目标环境：**Ubuntu 24.04、IBus、朙月拼音（含繁体）**。当前安装包为 `0.3.0~preview5`，通过 GitHub Actions 构建，供手动安装验收。

普通输入使用 Argos Translate 离线翻译；只有 **Ctrl+Shift+Enter** 才请求 DeepSeek / OpenAI 兼容 API 修正。英日译文分别标记 `🌐 MT · EN/JA` 或 `✦ AI · EN/JA`，AI 缓存优先显示。单个中文字即可触发，默认防抖 450ms。

## 安装

从 [GitHub Actions](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml) 下载最新成功构建的 artifact，解压后：

```bash
sudo apt install ./rime-llm-translator_0.3.0~preview5_amd64.deb

# 以下命令以桌面普通用户运行，不加 sudo
rime-llm-translator install-offline
rime-llm-translator setup
rime-llm-translator enable
```

首次离线引擎安装需要联网下载 Python 依赖和简中→英、繁中→英、英→日三个模型，可能花费较长时间和存储空间。只用 MT 时，setup 的 API Key 可以留空。已配置 API 的用户用 `sync` 保留设置，然后 `enable`。

**注销再登录**，在设置 → 键盘 → 输入源 → 中文中添加 **Rime Translator**，切换到该输入源。必要时用 Ctrl+反引号选择朙月拼音。

preview5 新增独立 IBus 前端：在前端主循环检测当前文本的缓存变化，重新计算并发布候选表，停止输入后也能显示新译文。不向系统注入按键。原生 Rime 入口继续保留，仍可切回使用。新入口的用户数据在 `~/.config/ibus/rime-llm`，不会与原生 Rime 同时打开同一词频数据库，也不会复制旧词频。

preview1–4 用户如果启用过旧插件，可以运行 `rime-llm-translator restore-native`，再重新部署原生 Rime，撤销旧版本对 `~/.config/ibus/rime` 的插件补丁。此操作不删词典和 API Key。

## 配置

配置文件：`~/.config/rime-llm-translator/config.ini`。

```ini
[provider]
base_url = https://api.deepseek.com
model = deepseek-chat

[translation]
enabled = true
offline_enabled = true
languages = en:English,ja:Japanese
source_language = auto
min_characters = 1
debounce_ms = 450
timeout_seconds = 10
max_tokens = 4096
```

繁体朙月拼音用户建议设置 `source_language = zt`；简体可用 `zh`。`auto` 是简单字形启发式，不能识别所有共用字。更改源语言会使用不同缓存。

其他目标语言需另行安装 Argos 模型。默认中译日经过英语中转，质量需要人工判断。源文本上限 1200 UTF-8 字节（约 400 个纯中文字），不能用于无限长文档翻译。

MT 和 AI 使用两个独立进程；AI 网络超时不会阻塞 MT。失败请求按 2–30 秒退避重试；已有的部分语言结果会保留。两类缓存各保留最近 350 项。模型未安装时，中文输入仍可使用。

## 停用与诊断

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service rime-llm-ai.service
journalctl --user -u rime-llm-translator.service -u rime-llm-ai.service -n 60 --no-pager

# 停止翻译；随时可以切回原生 Rime
rime-llm-translator disable
systemctl --user disable --now rime-llm-translator.service
```

普通 MT 不上传输入文本。显式 AI 快捷键会发送当前中文候选及已有机翻草稿到配置的模型。密钥单独保存在用户目录，后台错误日志不输出输入正文、草稿或密钥。

## 验收和构建

参见 [手动验收清单](docs/MANUAL_TEST.md)。真实模型推理、实际 API、GNOME/Wayland 最终绘制仍需手动安装验收。

GitHub Actions 在 Ubuntu 24.04 执行 Python/Lua 测试、真实 librime 候选测试、原生 IBus 前端编译、deb 安装，以及“写入迟到的 MT/AI 缓存后，无额外按键仍发出候选更新”的 IBus 集成测试。artifact 包含 deb、SHA256SUMS 和验收文档。

原生前端基于 [ibus-rime 1.5.0](https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3)，按 GPLv3 或更新版本分发，完整修改源码及许可证见 [frontend](frontend/README.md)，安装包中也附带源码。根目录的 Ollama Lua 文件仅保留上游原型，当前安装包不使用 Ollama。
