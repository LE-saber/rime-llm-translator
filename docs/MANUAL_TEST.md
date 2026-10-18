# Ubuntu 24.04 手动验收（preview5）

目标：Ubuntu 24.04、IBus、朙月拼音。使用新增的 **Rime Translator** 输入源。
原生 Rime 输入源不能主动刷新后台结果，不能用于验收自动刷新。

## 安装

1. 下载对应 GitHub Actions 的 artifact，解压 `.deb` 和 `SHA256SUMS`。
2. 在解压目录运行 `sha256sum --check SHA256SUMS`。若文件路径含 `dist/`，在其上一级目录运行。
3. `sudo apt install ./rime-llm-translator_0.3.0~preview5_amd64.deb`。
4. 使用桌面普通用户运行 `rime-llm-translator install-offline`（一次性联网下载依赖及三个模型）。
5. `rime-llm-translator setup`：配置语言、可选 AI 地址及密钥；只用离线机翻时密钥留空。
6. `rime-llm-translator enable`。
7. 注销再登录，在设置 → 键盘 → 输入源 → 中文中添加 **Rime Translator**。
8. 切换到此输入源；必要时按 Ctrl+反引号选择朙月拼音。

preview1–4 升级用户可先运行 `rime-llm-translator restore-native`，重新部署原生 Rime，
清除旧版本对原生方案的插件补丁。新输入源使用独立目录，不复制旧用户词频数据库。
原生 Rime 的词库、设置和 API 密钥不会被删除。

## 验收项目

| 操作 | 预期 |
|---|---|
| 输入 `nihao` 后完全停止按键 | 中文候选立即出现；模型完成后自动出现 `🌐 MT · EN/JA`，无需补按键 |
| 输入一个中文字，例如 `ni` | 同样可以离线翻译 |
| 输入一段较长中文，包含多句话 | 能得到译文，输入本身不卡住；源文本上限 1200 UTF-8 字节 |
| 断网后输入新中文 | MT 正常运行；首次模型载入可能较慢 |
| 普通输入后观察日志 | AI worker 不发 API 请求；不读取云端密钥用于机翻 |
| 在中文候选上按 Ctrl+Shift+Enter | 不提交中文，排队一次 AI 修正，完成后自动显示 `✦ AI · EN/JA` |
| 对已经完成修正的相同文本再按快捷键 | 使用缓存，不产生新请求 |
| AI 请求等待期间输入另一段中文 | 新的 MT 继续处理，不等待 AI 网络超时 |
| 候选出现前按 Esc 或切换应用 | 不提交文本、不重新打开已取消候选，不更新失焦应用 |
| 在中文候选之间移动高亮后等待译文 | 尽量保留同一候选高亮，不提交文字 |
| 停止后台服务，再输入中文 | 原生中文候选仍正常，已缓存译文仍可显示 |
| `rime-llm-translator disable` 后重新进入输入源 | 普通中文输入可用，不再产生翻译请求 |
| 切回原生 Rime 输入源 | 原生中文输入独立可用 |

日语通过中文→英文→日语中转，翻译质量需要人工判断。
繁体用户请在 `config.ini` 的 `[translation]` 设置 `source_language = zt`，再输入新内容。
修改源语言后不会沿用旧源语言的翻译缓存。

## 反馈信息

请记录：系统版本、Xorg/Wayland、发生问题的输入源、操作、预期与实际表现。
附以下命令输出，删除自己输入的敏感内容和凭据：

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service rime-llm-ai.service --no-pager
journalctl --user -u rime-llm-translator.service -u rime-llm-ai.service -n 60 --no-pager
```

自动检查涵盖模拟翻译、真实 librime、真实 IBus 的候选更新信号和安装包。
真实 Argos 模型性能、远端 API、GNOME/Wayland 最终候选绘制由本清单人工验收。
