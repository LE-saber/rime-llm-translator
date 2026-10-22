# 旧版本升级与残留清理

从 [正式 Release](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) 获取安装包后，在 Ubuntu 虚拟机中执行。APT 用 sudo，其余命令用桌面普通用户。本方案只处理 Ubuntu 桌面用户的旧安装数据。

## 磁盘已满时先腾出空间

preview5 可能留下数 GB 的 GPU 包下载缓存。若旧 Python 可用：

```bash
~/.local/share/rime-llm-translator/venv/bin/python -m pip cache info
~/.local/share/rime-llm-translator/venv/bin/python -m pip cache purge
df -h "$HOME"
```

pip 缓存可能也包含其他 Python 项目的下载/构建文件，清理后它们可能需要重新下载；已安装软件不被卸载。若旧 Python 不可执行，可用已安装的 `python3 -m pip cache purge`，或在文件管理器核对 `~/.cache/pip` 后清空其中内容。不要重新安装 Argos/PyTorch 来清理。

## 安装、验证新版本

```bash
sudo apt install ./rime-llm-translator_0.3.0_amd64.deb
rime-llm-translator sync && rime-llm-translator enable
rime-llm-translator install-offline
rime-llm-translator doctor
```

注销登录，选择 Rime Translator，确认断网可出现 MT 候选。新包包含模型，无 pip 安装。磁盘为包文件、解压后文件及 APT 升级预留空间，实际占用看该构建的 `RESOURCE_REPORT.md`。

## 默认清理项目私有残留

先只查看路径及逻辑文件大小：

```bash
rime-llm-translator cleanup-legacy
```

核对后执行：

```bash
rime-llm-translator cleanup-legacy --apply
```

默认仅选择 `~/.local/share/rime-llm-translator/venv` 及同一项目目录中的 `install-*` 临时文件。删除前校验新包资源、停止 MT 服务，检查所有目标及父目录没有符号链接跳转；原来运行的 MT 服务在完成后恢复，原来停用的保持停用。显示的是逻辑大小，实际释放空间受文件系统及硬链接影响。

## 可选：共享缓存和旧语言模型

如果不再使用其他 Argos 软件，可以检查：

```bash
rime-llm-translator cleanup-legacy --pip-cache --argos-models
```

- `--pip-cache` 增加共享的 `~/.cache/pip` 下载/构建缓存；不卸载已安装包。自定义到其他路径的 pip 缓存不自动处理。
- `--argos-models` 检查 `~/.local/share/argos-translate/packages/*/metadata.json`，仅选择中英、繁中英、英日方向模型。这些模型可能被其他 Argos 应用共用，仍需使用这些应用时请保留。其他方向模型不处理。

确认列出的共享资源不再需要后，使用相同选项加 `--apply`：

```bash
rime-llm-translator cleanup-legacy --pip-cache --argos-models --apply
```

重复执行跳过已删除的目录。工具不执行 `apt autoremove`，不卸载系统 Python、IBus、Rime，也不删除虚拟机快照、共享文件夹和宿主机文件。

## 始终保留的数据

- `~/.config/rime-llm-translator/config.ini` 与 `api_key`，以及本机输入记录 `long-text.json`。
- `~/.config/ibus/rime` 原生词库、词频和用户设置。
- `~/.config/ibus/rime-llm` 新入口词库与设置。
- 当前安装包提供的模型/程序，以及当前 MT/AI 缓存。

preview1–4 若改过原生 Rime，可另外运行 `rime-llm-translator restore-native` 后重新部署原生 Rime。该命令只移除本项目可识别的旧翻译器 schema 补丁，不删除词典。

最后检查：

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service rime-llm-ai.service
du -sh ~/.local/share/rime-llm-translator ~/.cache/pip ~/.local/share/argos-translate 2>/dev/null
df -h "$HOME"
```

Downloads 中旧 `.deb`、ZIP 可在核对新包已安装后手动删除。若要清理系统级所有包的 APT 下载缓存，可执行 `sudo apt clean`；已安装软件不受影响。
