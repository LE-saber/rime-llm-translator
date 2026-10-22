# Rime LLM Translator — 轻量离线机翻 + 按键 AI 修正

目标环境：Ubuntu 24.04 amd64、IBus、朙月拼音（含繁体）。`0.3.0~preview12` 使用原生 Bergamot INT8，并支持自定义 AI 快捷键及双击 Alt。安装包内含中英和英日模型，用户机器不需要 pip 安装、编译或首次下载权重。

普通输入提供 `🌐 MT · EN/JA` 草稿；仅 AI 快捷键（默认 **Ctrl+Shift+Enter**）请求配置的 DeepSeek / OpenAI 兼容 API 修正。AI 读取中文原文和已有草稿，结果标为 `✦ AI · EN/JA` 并优先显示。API Key 可留空。

## 安装与升级

preview12 统一悬浮面板的图标、间距与主题；每次打开为空白，未发送文本可从记录找回，发送成功即清空。配置 API 后默认启用发送 AI，等待时显示转圈和秒数，可手动关闭。发送位置跟随最近选择的真实输入框，悬浮原文区和设置框都不会成为接收目标。详见 [长文本使用与验收](docs/LONG_TEXT.md)。升级后运行 sync / enable 并注销再登录。

下载最新成功的 [GitHub Actions artifact](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml)，解压后：

```bash
sudo apt install ./rime-llm-translator_0.3.0~preview12_amd64.deb
```

新用户运行：

```bash
rime-llm-translator setup && rime-llm-translator enable
```

已有版本运行，保留 API Key 和设置：

```bash
rime-llm-translator sync && rime-llm-translator enable
rime-llm-translator install-offline
systemctl --user restart rime-llm-translator.service rime-llm-ai.service
rime-llm-translator settings
```

`install-offline` 现在只校验包内资源。旧 `install-runtime`、`download-models`、`repair-offline` 命令也兼容为校验入口；清理使用单独命令。

除 APT 外，命令均以桌面普通用户运行。**注销再登录**，在设置 → 键盘 → 输入源 → 中文中添加 **Rime Translator** 并切换过去，必要时 Ctrl+反引号选择朙月拼音。

独立前端通过 GLib/IBus 主循环更新迟到的翻译候选，不需额外按键，不向系统注入按键。原生 Rime 入口保留；新入口数据在 `~/.config/ibus/rime-llm`，不会复制或同时打开原生词频数据库。

## 修改 AI 快捷键

以普通用户运行，例：改为 Ctrl+Alt+J：

```bash
rime-llm-translator hotkey 'Control+Alt+j'
rime-llm-translator hotkey
```

第一条修改，第二条查看。只更新配置中的 `ai_hotkey`，保留接口、模型、API Key 和词库；`setup` 也会询问快捷键，`doctor` 会显示当前值。

双击 Alt（需 preview9）：

```bash
rime-llm-translator hotkey DoubleAlt
```

选中未上屏的中文候选，在 400 毫秒内快速按下并松开同一个 Alt 两次，建议用左 Alt；部分键盘的右 Alt 是 AltGr。按住、自动连发、夹入其他键、切换窗口或取消输入都会打断手势。只有两次完整点按才请求 AI，不自动上屏。候选中文期间，Alt 单键保留给这个手势；Alt 组合键仍转交正常处理，没有中文候选时 Alt 照常使用。

升级后，先运行 `sync && enable` 并注销重新登录一次以加载新版前端及 Lua。此后改键立即生效，不必重启服务或重新部署，原快捷键不再触发 AI。使用时保持候选未上屏，选中中文候选后按新组合键或双击 Alt；繁体中文输入照常保留。

格式：`Control`（也可写 `Ctrl`）、`Alt`、`Shift`、`Super` 的组合加一个字母、数字、`F1`–`F12`、`Return`（也可写 `Enter`）或 `space`。必须包含 Control/Alt/Super 中至少一个。例如 `Control+Shift+F8`。请选择桌面、应用和虚拟机宿主未占用的组合；程序不能自动检测全部冲突。这是输入法内快捷键，无需在 Ubuntu 的全局快捷键设置中注册。

## 旧版本残留

完整方案见 [升级与清理](docs/UPGRADE_CLEANUP.md)。先查看，再执行：

```bash
rime-llm-translator cleanup-legacy
rime-llm-translator cleanup-legacy --apply
```

默认仅清理本项目私有 venv 和未完成安装的临时目录，保留密钥、配置和 Rime 词库。共享 pip 缓存及 Argos 模型需要额外参数。检测到符号链接跳转会拒绝删除。旧环境保留期间，其磁盘仍需另计。

## 工作方式与性能

- 原生 C++ 子进程单线程、单请求推理，默认最多一个逻辑核、较低 CPU 优先级；计算时该核仍可能显示 100% CPU。
- 一个中文字即可触发，默认防抖 450 ms。只保留最新待处理输入，跳过旧输入尚未开始的日文计算。
- OpenCC 仅将机翻副本归一化为简体，共用中英模型。日文复用英文结果中转，定位为基本草稿；云端 AI 保留中文原文。
- 英文完成即刷新候选，日文随后补齐。一次仅驻留一个模型方向，英日切换时释放旧模型；只配置英文时不加载英日模型。
- 登录不预加载权重；默认空闲 60 秒退出计算进程，回收内存。下一次请求需要冷启动。
- MT 和 AI 独立服务。MT 不上传文本，失败不自动请求 AI；AI 超时不阻塞 MT。日志不记录正文、草稿或密钥。
- 源文本上限 1200 UTF-8 字节；引擎按 token 预算分块，不支持无限长文档。离线仅提供英、日，其他目标语言可用显式 AI 请求。
- MT/AI 缓存各最多 350 项、10 MiB。缓存身份包含模型/引擎修订、归一化修订与源语言，不复用旧 Argos 结果。

两套模型压缩资源约 60.8 MB（十进制）。中英选用 tiny（官方 registry 尚未标为 Release），英日选用 base-memory，因此仍作为 preview 交付，基本草稿质量需手动验收。安装包、解压磁盘、真实模型冷/热延迟和内存见每次构建 artifact 的 `RESOURCE_REPORT.md`，公开样本译文见 `mt-benchmark.json`。GitHub runner 实测不能代替虚拟机验收。原生引擎要求虚拟机 CPU 暴露 SSE4.1，构建不使用 Actions 主机专属 `-march=native`。

## 配置

文件：`~/.config/rime-llm-translator/config.ini`。

```ini
[provider]
base_url = https://api.deepseek.com
model = deepseek-chat

[translation]
enabled = true
offline_enabled = true
languages = en:English,ja:Japanese
ai_hotkey = Control+Shift+Return
source_language = auto
min_characters = 1
debounce_ms = 450
offline_timeout_seconds = 15
offline_idle_seconds = 60
timeout_seconds = 10
max_tokens = 4096
```

`source_language` 接受 `auto`、`zh`、`zt`，均对机翻副本进行简繁归一化，不再依赖字形启发式选择模型。`offline_revision` 由 `sync`/`enable` 自动写入。只用英文可设 `languages = en:English`；低功耗模式可将防抖改为 600–800 ms。

## 诊断与停用

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service rime-llm-ai.service
journalctl --user -u rime-llm-translator.service -u rime-llm-ai.service -n 60 --no-pager
rime-llm-translator disable
systemctl --user disable --now rime-llm-translator.service
```

可随时切回原生 Rime。preview1–4 启用过旧插件的用户，可执行 `rime-llm-translator restore-native` 后重新部署原生 Rime，移除旧翻译器补丁，保留词典和密钥。

## 验收与来源

GitHub Actions 在 Ubuntu 24.04 检查 Python/Lua、真实 librime 候选、包安装、真实 IBus 迟到候选刷新及断网真实模型推理，并生成资源报告。GNOME/Wayland 绘制、虚拟机体验及草稿质量由用户按 [手动清单](docs/MANUAL_TEST.md) 验收；不使用 WSL。

前端基于 GPLv3-or-later [ibus-rime 1.5.0](https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3)，源码与许可在 `frontend/` 及包内。原生 Mozilla 引擎和模型锁定信息在 `native/mt/`；推理依赖完整源码及许可证随包置于 `/usr/share/doc/rime-llm-translator/inference-source.tar.xz`，并附本项目包装代码。Mozilla 模型按 MPL 2.0 分发，第三方依赖保留各自许可。根目录 Ollama Lua 是未参与安装运行的上游原型。
