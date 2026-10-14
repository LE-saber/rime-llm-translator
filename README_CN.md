# Rime LLM Translator — Ubuntu 24.04 中文安装指南

本仓库基于 [niyue/rime-ollama-translator](https://github.com/niyue/rime-ollama-translator) 的候选翻译设计，新开发支持 **IBus + Rime + 外部 OpenAI 兼容 API** 的安装版，**不依赖 Ollama**。

## 功能

- 输入拼音，保留原本中文候选，可从候选列表选择英、日等多语言译文上屏。
- DeepSeek / OpenAI / 其他兼容 Chat Completions 的 API。
- 中文候选识别、800 毫秒去抖、单用户后台翻译服务、翻译结果缓存。
- 自定义目标语言，例如 `en:English,ja:Japanese,fr:French,ko:Korean`。
- **注意**：远程翻译在后台进行，首次译文可能要等到**下一次候选菜单重新计算**才会显示；当前版本不能保证结果返回时立即主动刷新候选框。

## 下载与安装

进入仓库 [Actions](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml)，打开成功的 **Build Ubuntu installer** 构建，下载 Artifacts 中的 `rime-llm-translator-ubuntu24.04`，解压获得 `.deb`。

Ubuntu 24.04 下打开包含安装包的目录：

```bash
sudo apt install ./rime-llm-translator_0.1.0~preview3_all.deb
rime-llm-translator setup
```

**安全变更：setup 仅配置 API、安装用户插件文件、启动后台服务，不再自动把 Lua 过滤器插入正在工作的 Rime 方案。** 必须确认离线与真实 Rime 候选回归测试通过后，由用户主动执行 `rime-llm-translator enable` 才启用候选翻译。
`setup` 依次要求 API URL、模型 ID、目标语言和 API Key。DeepSeek 可填：

- API base URL：`https://api.deepseek.com`
- Model：`deepseek-chat`
- Languages：`en:English,ja:Japanese`

配置保存在 `~/.config/rime-llm-translator/config.ini`；API Key 单独存于 `api_key` 文件（仅用户可读）。

安装器会把 Lua 过滤器放入 `~/.config/ibus/rime/lua/`，默认不修改 Rime 方案。需要实际启用时运行：

```bash
rime-llm-translator enable
```

它会备份并追加一个可撤销的过滤器到 `luna_pinyin.custom.yaml` **末尾**，不再放在首位。注销、重新登录 Ubuntu 并重新部署「朙月拼音」方案。

如中文候选受影响，可随时运行：

```bash
rime-llm-translator disable
```

随后重新部署 Rime（可注销重新登录）。此操作只移除本插件添加的配置，不影响原生 Rime 词典与 API 密钥。

## 从旧预览版升级

下载新的 preview3 安装包后，在解压目录执行：

```bash
sudo apt install ./rime-llm-translator_0.1.0~preview3_all.deb
rime-llm-translator sync
```

`sync` 只更新 Lua 文件，不会修改原有 API Key 或自动启用输入法过滤器。若历史配置仍含旧过滤器，请先运行 `rime-llm-translator disable` 并重新部署；确认普通输入正常后再决定是否执行 `enable`。

## 检查和故障排查

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service
journalctl --user -u rime-llm-translator.service -n 30 --no-pager
```

如果中文输入正常但译文未出现：检查服务、API 模型、网络与密钥是否正确，输入完成后等待约 1 秒，再触发一次候选菜单更新。首次结果可能需要再次编辑并恢复相同拼音才能进入缓存后的候选列表。

配置修改后执行：

```bash
systemctl --user restart rime-llm-translator.service
```

要暂停远程翻译，把 `config.ini` 中 `enabled = true` 修改为 `enabled = false`。

## 隐私与兼容性

- 自动翻译会把候选中文发送到你配置的模型供应商，请勿用于密码、密钥等敏感输入。
- GitHub Actions 不需要也不保存你的 API Key。
- 目标是 Ubuntu 24.04 + IBus + Rime + Lua 插件 + 朙月拼音。
- CI 新增独立用户目录下的 Ubuntu 24.04 **真实 librime + Lua 候选回归测试**。但 GUI/Wayland 即时菜单刷新仍需实机验证。
- 默认禁用 AI 候选过滤器，避免覆盖已能正常使用的中文输入。

仓库原有 Ollama 版本仍保留在 `rime_ollama_translator.lua` 中，可供参考。原项目许可证以其 README 所述 MIT 为准。
