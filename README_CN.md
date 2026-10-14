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
sudo apt install ./rime-llm-translator_0.1.0~preview1_all.deb
rime-llm-translator setup
```

`setup` 依次要求 API URL、模型 ID、目标语言和 API Key。DeepSeek 可填：

- API base URL：`https://api.deepseek.com`
- Model：`deepseek-chat`
- Languages：`en:English,ja:Japanese`

配置保存在 `~/.config/rime-llm-translator/config.ini`；API Key 单独存于 `api_key` 文件（仅用户可读）。

安装器会把 Lua 过滤器放入 `~/.config/ibus/rime/lua/`，并备份、合并修改 `luna_pinyin.custom.yaml`，同时启动 systemd 用户服务。设置完成后注销、重新登录 Ubuntu，选择 Chinese (Rime) 并重新部署「朙月拼音」方案。

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
- 对其他输入方案、Wayland 的即时候选刷新，以及实机输入法交互仍需测试验证。

仓库原有 Ollama 版本仍保留在 `rime_ollama_translator.lua` 中，可供参考。原项目许可证以其 README 所述 MIT 为准。
