# 开发与发布

## 范围与目录

正式目标为 Ubuntu 24.04 amd64 / GNOME 46。Windows 仅用于编辑源码，不在本机或 WSL 构建 Linux 安装包。

| 目录 | 职责 |
|---|---|
| `frontend/` | 独立 C / IBus 前端、Rime 集成与目标提交桥接 |
| `lua/` | 翻译候选过滤器与 AI 快捷键 |
| `src/` | CLI、服务、GTK 编辑器、历史和翻译调度 |
| `gnome-extension/` | GNOME 46 真实目标跟踪、恢复与验证 |
| `native/mt/` | 原生引擎包装、锁定版本 / 模型与低内存补丁 |
| `packaging/` | Debian 打包、用户服务和桌面入口 |
| `tests/` | 单测、桌面集成、断网模型和资源测量 |

## GitHub 构建

以 [.github/workflows/build.yml](../.github/workflows/build.yml) 为依赖和命令的权威来源。推送 `main`、`feat/**`、`fix/**` 或手动运行 workflow，检查完整 job 为成功后下载 `rime-llm-translator-ubuntu24.04` artifact。

流程包括语法检查、单元测试、真实 Rime 候选、包构建 / 安装、IBus 异步刷新、GTK 编辑器、嵌套 GNOME 46 Wayland 目标提交和断网模型资源报告。测试中的嵌套桌面只运行在 GitHub Ubuntu runner，不使用 WSL。

仅需构建包时，在已安装 workflow 所列构建依赖的 Ubuntu 24.04 amd64 上运行 `bash packaging/build-deb.sh`。它会按锁定信息获取上游推理源码与模型。用户安装成品无需这些构建依赖。

## 版本与发布

1. 更新根目录 `VERSION`、中英文 README、升级 / 验收文档、`CHANGELOG.md` 和 `docs/releases/vX.Y.Z.md`。
2. 运行完整 CI，将通过的修改合并到 `main`。
3. 对对应提交推送 `vX.Y.Z` 标签。CI 核对标签与 `VERSION`、Debian 包元数据一致，全部检查通过后创建 **draft Release**，附包、SHA256SUMS 和资源报告。
4. 核对标签提交、构建结论、安装包校验值及 Release 文案后，将 draft 发布。失败的 tag 构建不会自动公开 Release。

截图应来自实际 GTK 程序，使用公开测试内容，不含真实 API Key 或私人记录。`docs/images/` 可公开；用户本地原型不参与发布。资源报告中的 runner 型号、延迟和内存只适用于该构建测量。

## 手动验收与来源

按 [MANUAL_TEST.md](MANUAL_TEST.md) 与 [LONG_TEXT.md](LONG_TEXT.md) 在真实桌面应用验收。模拟 AI 能验证错误、超时与进度行为，不代表云端实际质量。锁定源码、模型校验值和第三方许可见 `native/mt/`、`frontend/` 及安装包 `/usr/share/doc/rime-llm-translator/`。
