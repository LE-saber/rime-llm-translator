# Ubuntu 24.04 手动验收（preview7）

目标：Ubuntu 24.04、IBus、朙月拼音。使用新增的 **Rime Translator** 输入源。
原生 Rime 输入源不能主动刷新后台结果，不能用于验收自动刷新。

## 安装

1. 下载对应 GitHub Actions 的 artifact，解压 `.deb` 和 `SHA256SUMS`。
2. 在 `.deb` 所在目录（artifact 的 `dist/`）运行 `sha256sum --check SHA256SUMS`。
3. `sudo apt install ./rime-llm-translator_0.3.0~preview8_amd64.deb`。
4. 使用桌面普通用户运行 `rime-llm-translator install-offline`，应只校验包内模型，不运行 pip 或联网下载。若 preview5 已空间耗尽，按 [清理方案](UPGRADE_CLEANUP.md) 先处理共享 pip 下载缓存。
5. 新用户运行 `rime-llm-translator setup`，配置语言、可选 AI 地址及密钥；只用机翻可留空。升级用户改运行 `sync`，保留已有配置与 Key。
6. `rime-llm-translator enable`。
7. 注销再登录，在设置 → 键盘 → 输入源 → 中文中添加 **Rime Translator**。
8. 切换到此输入源；必要时按 Ctrl+反引号选择朙月拼音。

preview1–4 升级用户可先运行 `rime-llm-translator restore-native`，重新部署原生 Rime，
清除旧版本对原生方案的插件补丁。新输入源使用独立目录，不复制旧用户词频数据库。
原生 Rime 的词库、设置和 API 密钥不会被删除。

## 验收项目

| 操作 | 预期 |
|---|---|
| 执行 install-offline | 校验原生引擎和内置模型，无 pip、无 PyTorch、无额外模型下载 |
| 执行 cleanup-legacy | 只显示残留路径和大小，不删除文件 |
| 新后端可用后运行 cleanup-legacy --apply | 删除旧私有 venv/临时目录，密钥、设置、词库和共享缓存仍保留 |
| 可选清理共享资源 | 按清理文档分别核对 --pip-cache/--argos-models，其他 Argos 应用仍需使用时保留模型 |
| 输入 `nihao` 后完全停止按键 | 中文候选立即出现；模型完成后自动出现 `🌐 MT · EN/JA`，无需补按键 |
| 输入一个中文字，例如 `ni` | 同样可以离线翻译 |
| 输入一段较长中文，包含多句话 | 能得到译文，输入本身不卡住；源文本上限 1200 UTF-8 字节 |
| 断网后输入新中文 | MT 正常运行；首次模型载入可能较慢 |
| 快速连续输入、删除和重新输入 | 待处理请求不堆积；不会显示旧输入的迟到译文 |
| 等待双语翻译 | 英文可先出现，日文稍后补齐，中文按键不等待推理 |
| 翻译后空闲超过 60 秒 | `pgrep -af /usr/libexec/rime-llm-translator/rime-mt` 不再显示计算子进程；下次输入可重新启动 |
| 记录实际资源 | 同时观察中文交互、CPU、RSS，和 artifact 的资源报告比较；报告不是虚拟机速度承诺 |
| 普通输入后观察日志 | AI worker 不发 API 请求；不读取云端密钥用于机翻 |
| 在中文候选上按 AI 快捷键（默认 Ctrl+Shift+Enter） | 不提交中文，排队一次 AI 修正，完成后自动显示 `✦ AI · EN/JA` |
| `rime-llm-translator hotkey 'Control+Alt+j'` 后保持输入法开启 | 查看命令 `hotkey` 与 `doctor` 显示新组合，按新组合请求 AI，无需重启；原 Ctrl+Shift+Enter 不再请求 AI |
| 改键后输入繁体「謝謝」，以及普通空格选词、Esc 取消 | 繁体候选和中文上屏正常，未按新快捷键不请求 AI |
| `rime-llm-translator hotkey 'j'` 或未知按键名 | 拒绝保存，原有效快捷键和其他配置不变 |
| 对已经完成修正的相同文本再按快捷键 | 使用缓存，不产生新请求 |
| AI 请求等待期间输入另一段中文 | 新的 MT 继续处理，不等待 AI 网络超时 |
| 候选出现前按 Esc 或切换应用 | 不提交文本、不重新打开已取消候选，不更新失焦应用 |
| 在中文候选之间移动高亮后等待译文 | 尽量保留同一候选高亮，不提交文字 |
| 停止后台服务，再输入中文 | 原生中文候选仍正常，已缓存译文仍可显示 |
| `rime-llm-translator disable` 后重新进入输入源 | 普通中文输入可用，不再产生翻译请求 |
| 切回原生 Rime 输入源 | 原生中文输入独立可用 |

日语通过中文→英文→日语中转，翻译质量需要人工判断。
简繁机翻共用 OpenCC 归一化副本；检查繁体词句、否定、数字、时间及专名的基本意思。
`source_language` 可用 `auto`、`zh`、`zt`，云端始终收到中文原文。
修改源语言后不会沿用旧源语言的翻译缓存。

## 反馈信息

请记录：系统版本、Xorg/Wayland、发生问题的输入源、操作、预期与实际表现。
附以下命令输出，删除自己输入的敏感内容和凭据：

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service rime-llm-ai.service --no-pager
journalctl --user -u rime-llm-translator.service -u rime-llm-ai.service -n 60 --no-pager
```

自动检查涵盖模拟故障、真实 librime、真实 IBus 的候选更新信号、完整安装包和断网真实模型推理。
GitHub 单核下的冷/热延迟和内存记录在资源报告；虚拟机体验、草稿质量、远端 API 和 GNOME/Wayland 绘制由本清单人工验收。
