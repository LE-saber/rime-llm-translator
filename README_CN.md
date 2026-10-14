# Rime LLM Translator — 离线机翻 + 按键 AI 修正

适用：Ubuntu 24.04、IBus-Rime、朙月拼音（含繁体）。本项目依赖 [Argos Translate](https://github.com/argosopentech/argos-translate) 提供离线机器翻译，**用户按下快捷键时才调用 DeepSeek / OpenAI 兼容 API**，不使用 Ollama。

## 候选行为

- 默认允许 **一个中文字**起触发本地翻译；后台约 450ms 防抖，快速输入时只翻译最新稳定候选，无云端 Token 消耗。
- 中文原生候选始终先显示。缓存命中后自动追加外语候选，注释 `🌐 MT · EN` / `🌐 MT · JA`。
- **Ctrl+Shift+Enter**：在 Rime 仍有当前中文候选时发出一次 AI 修正请求。结果缓存后替代对应的机器翻译候选，注释 `✦ AI · EN` / `✦ AI · JA`。
- 网络断开，MT 仍可翻译（模型需事先下载）。AI 快捷键离线时无法调用远程服务，普通输入和 MT 不受影响。
- **限制**：后台写入新结果不会直接通知正在静止显示的候选框。缓存结果在下一次 Rime 菜单重算/按键时可见；实时刷新不保证在完全停止输入后自动触发。译文生成不是逐字符同步阻塞输入。
- Argos 的 **简体中文→英语、繁体中文→英语、英语→日语**为官方提供的可下载语言包；中文→日语经英文中转，译质不如专门中日模型。初次部署需要网络下载语言模型，日后可断网使用。

## 安装（不接管现有 Rime）

从 [Actions](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml) 下载 `preview4` 的 Ubuntu .deb，解压后：

```bash
sudo apt install ./rime-llm-translator_0.2.0~preview4_all.deb

# 首次下载 Python 离线引擎与三套语言模型；可能花费一些时间/空间
rime-llm-translator install-offline

# 如已保存 API Key 和语言设置，只更新用户 Lua 文件
rime-llm-translator sync
rime-llm-translator doctor
```

新用户请先运行 `rime-llm-translator setup` 配置目标语言（例如 `en:English,ja:Japanese`）、AI API 地址/模型及密钥，或直接编辑 `~/.config/rime-llm-translator/config.ini`。只有在按快捷键时 AI API 才被请求。已设置 API 的旧用户不需要重复填入密钥。

**所有安装与同步命令默认不修改活动中的 Rime 输入法。** 在确认原生 Rime 正常后，明确选择启用：

```bash
systemctl --user daemon-reload
systemctl --user enable --now rime-llm-translator.service
rime-llm-translator enable
```

重新部署朙月拼音并注销登录，使 Lua 过滤器和快捷键处理器生效。新增 `engine/filters/+` 过滤器与位于前端的 `engine/processors/@before 0` 按键监听器，非匹配按键放行。

### 卸载插件/恢复原生输入

```bash
rime-llm-translator disable
systemctl --user disable --now rime-llm-translator.service
```

重新部署 Rime 让已编译的方案清除插件引用，必要时注销登录；只撤销本项目的 Lua 过滤器/Processor 配置，不删 API Key。不要直接卸载 ibus-rime。

## 语言选择与离线配置

`config.ini` 中：

```ini
[translation]
enabled = true
offline_enabled = true
languages = en:English,ja:Japanese
min_characters = 1
debounce_ms = 450
source_language = auto
```

`source_language` 可填 `auto`、`zh`（简体）或 `zt`（繁体）。自动识别无法区分所有简繁共用字，**使用繁体朙月拼音的用户建议明确改为 `zt`**。目标语言扩展前必须安装对应 Argos 离线模型包；当前 `install-offline` 自动安装的只有中英、繁英和英日。其他目标语言可通过 argospm 自行安装。

后台服务自动切换到专用 `~/.local/share/rime-llm-translator/venv` Python 环境，不依赖系统 pip，避免 Ubuntu 24.04 的 PEP 668 限制。

## 隐私和资源消耗

- **普通机翻**不上传输入文本；API Key 只在显式 AI 请求时读取。
- 同一中文文本的机器翻译与 AI 结果分别缓存；重复触发已完成的 AI 请求不产生额外 API Token。
- 输入法候选可包含敏感内容；如果主动触发 AI，当前中文候选会被发送到所配置的云模型。
- 本地 Argos 运行依赖 CPU 和内存；不同语言包会占用额外存储，首次载入较慢，虚拟机应预留足够资源。
- 真实 librime 测试覆盖中文候选、缓存机器翻译、显式热键请求和缓存 AI 覆盖。**Ubuntu 图形候选即时重绘、真实 Argos 模型下载/推理质量和实际云端 API 尚需实机验证**。不建议在关键输入环境中直接试用未验证版本。

## 检查

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service
journalctl --user -u rime-llm-translator.service -n 30 --no-pager
```
