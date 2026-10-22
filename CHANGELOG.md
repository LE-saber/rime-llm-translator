# 更新记录 / Changelog

## v0.3.0 — 2026-10-22

首个 GitHub 正式安装包版本，整合 0.3.0 preview 系列；目标为 Ubuntu 24.04 amd64 / GNOME 46 / IBus。正式版本号不代表支持其他桌面或无需人工检查译文。

- 用原生 Bergamot INT8 和包内模型替代旧 Argos / Python 私有环境；离线英日草稿、单线程、空闲回收，无首次模型下载。
- 独立 Rime Translator 输入源自动刷新翻译候选，保留普通中文、繁体和原生 Rime。
- 原生 GTK 长文本悬浮框：置顶、拖动缩放、灰白 / Dracula 主题、图标工具、大原文和小预览。
- 每次打开为空白，未发送内容保存本机记录，↑ / ↓ 回溯，发送成功清空。
- GNOME 46 桥接跟随最近有效外部文本框，支持同窗口控件切换，排除编辑器 / 设置框，提交前恢复并验证目标。
- 配置 API 后默认 AI 发送，可手动关闭；显示转圈与秒数。实时预览保持机翻，失败不偷偷发送机翻。
- GUI 管理 API / 模型、语言、主题、历史、按钮与录制快捷键；支持双 / 三击 Alt 和面板内鼠标侧键。
- 提供旧环境清理、诊断、升级说明、真实界面截图和构建资源报告。
- GitHub CI 覆盖真实 Rime / IBus / GTK、GNOME 46 Wayland、模拟 API、断网模型与包安装；实际云端质量和用户应用仍需人工验收。

English: the first packaged GitHub release combines lightweight bundled offline MT, an on-demand native floating editor, latest-real-field delivery, local history, configurable shortcuts/settings and explicit cloud AI with visible progress. See [README](README.md) and [release notes](docs/releases/v0.3.0.md).
