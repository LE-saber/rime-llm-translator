# 原生长文本模式（v0.3.0）

Ubuntu 24.04 amd64，GNOME 46、IBus / 朙月拼音（含繁体）。使用系统 GTK3 和现有离线翻译进程，按需打开置顶悬浮面板。

## 升级与打开

```bash
sudo apt install ./rime-llm-translator_0.3.0_amd64.deb
rime-llm-translator sync && rime-llm-translator enable
```

**注销并重新登录一次**，让新的 IBus 前端和 GNOME 桥接一起加载。`rime-llm-translator doctor` 中 GNOME floating-panel bridge 应为 active。

先点击真正接收译文的输入框，切到 Rime Translator，再按打开快捷键（默认 Alt+Space）。若被 GNOME 窗口菜单占用，用 `rime-llm-translator settings` 录制其他组合，例如 Ctrl+Alt+Space。升级保留 API、模型、已有快捷键和 Rime 词库。

## 最近选择的真实输入框

打开时记录当前接收位置 A。在面板打开期间，点击 B 并把文本光标放入 B，再回面板编辑，发送会进入 B。没有改选时仍进入 A。面板顶端显示当前目标窗口；悬浮原文区以及本程序所有设置输入框都不会替换发送目标。仅切换到没有文本光标的普通窗口，不会把它设为新输入框。

真正接收文字的是最近一次有效的外部文本焦点。面板编辑光标只控制中文原文，不控制译文写入位置。发送时收起面板，恢复最近的真实输入框，并核对输入上下文后提交。开始提交后的目标失效、锁屏、密码 / PIN 输入或超时会取消提交，原文保留。

GNOME Wayland 通过随包的 `rime-llm-translator@le-saber` 扩展完成窗口恢复与提交；独立 IBus 上下文也会跟踪最近真实输入框。不会通过全局粘贴或模拟按键提交。关闭目标后需在有效输入框重新打开面板，可按 ↑ 找回原文。

Wayland 的 text-input 跟随键盘焦点，同一窗口内的多个控件可以复用输入对象，因此不能仅凭窗口 ID、光标坐标或 `currentFocus` 判断控件。桥接结合真实文本焦点事件、周围文本 / 光标位置更新以及窗口身份跟踪接收位置，排除本程序窗口，并在恢复后再次验证。应用必须正常支持其输入法协议，具体应用仍需手动验收。

接口依据：[Wayland text-input 协议](https://cgit.freedesktop.org/wayland/wayland-protocols/tree/unstable/text-input/text-input-unstable-v3.xml)、[GNOME 46 InputMethod](https://raw.githubusercontent.com/GNOME/gnome-shell/46.0/js/misc/inputMethod.js)、[Mutter 46 文本输入实现](https://raw.githubusercontent.com/GNOME/mutter/46.0/src/wayland/meta-wayland-text-input.c)。AT-SPI 提供 [EditableText.insert_text](https://gnome.pages.gitlab.gnome.org/at-spi2-core/libatspi/method.EditableText.insert_text.html) 等控件接口，但依赖应用公开相应能力，本版本不增加这条提交路径。

## 原文、记录与发送

- 每次打开都从空白原文开始。关闭时，即使未发送也会保存到输入记录；不会再次自动填回编辑区。旧版保存的草稿迁移到记录。打开时原输入法未提交的候选也只进入记录，不自动填入面板。
- 原文为空时按 ↑ 显示最近记录，继续 ↑ 向前浏览，↓ 返回较新的记录，直到恢复空白。回溯后可修改；普通多行编辑仍保留正常光标移动。
- 确认发送成功后立即清空原文和预览，以便下次输入。失败保留文字。关闭 / 发送 / 手动 AI 时保存记录；最多 50 条去重，仅本机存储，目录 0700、文件 0600。
- 输入记录和按钮显隐等在设置中管理。`~/.config/rime-llm-translator/long-text.json` 只保存记录，不再自动恢复编辑草稿。关闭“保存输入记录”后不再新增；已有记录需手动清空。

## 机翻预览与 AI 发送

实时预览始终使用现有离线机翻（英语 / 日语）。手动 AI 按钮 / 快捷键仅处理当前版本和语言；改字、切换语言和发送后恢复机翻，不会把后续输入自动送到云端。

**“发送用 AI”默认开启，填写有效 API 地址、模型及非空密钥后自动生效。** 尚未配置 API 时可使用离线发送；配置状态只在本地检查，不以后台联网探测密钥是否有效。面板和设置都能手动关闭，并保存选择。本次升级将旧版本默认关闭迁移为开启一次，之后用户的关闭选择会保留。

点击发送或按发送快捷键，若需要 AI，会在发送按钮显示转圈和 `AI 翻译 0.0 s`，秒数持续更新。有效的当前 AI 结果可以复用；等待时重复发送不会重复请求。AI 失败、超时、回复截断或编辑导致结果过期，都不会发送机翻或旧译文来代替。等待 AI 时修改原文会取消本次发送意图；目标在提交前可随最近真实输入焦点更新。

原文最多 **32 KiB UTF-8**，超限拒绝而不截断。翻译按段落 / 字节预算分块并保留顺序、换行和末尾；分块质量需人工检查。英语 / 日语以外的语言需 AI。

## 外观与设置

统一间距、边框和字号；原文大、预览小。复制、粘贴、符号、设置、主题和关闭使用图标，悬停可看文字提示，并保留无障碍名称。日间仅灰白；夜间为 Dracula 深灰与淡紫。发送按钮保留文字和状态。

拖动顶栏移动，右下角拖动缩放，关闭按钮保存记录并收起。面板始终置顶，不进入任务栏 / Alt-Tab；GNOME Wayland 下使用 Xwayland utility 提示，真实目标应用仍可使用原生 Wayland。候选栏跟随面板编辑光标，编辑器没有嵌入系统候选栏。

GUI 与 CLI 共用配置，支持语言、优先预览语言、API、模型、密钥、超时、主题、按钮显隐、历史和快捷键。直接录制组合键、双 / 三击 Alt 或面板内鼠标侧键。重复和双 / 三击 Alt 的前缀冲突会拒绝。鼠标侧键可用于面板内 AI / 发送；原应用中的打开键依赖 IBus 收到键盘事件。

## 验收

1. 普通繁体输入正常；每次打开长文本为空，关闭未发送内容后仍能用 ↑ 找回。连续 ↑ / ↓ 顺序正确。
2. 从 A 打开，在面板编辑后发送，译文进入 A 的原光标处。再从 A 打开，点 B 放入光标，回面板修改后发送，只有 B 收到译文。
3. 在同一窗口的两个输入框间切换，确认最新文本框接收；点击面板原文、API / 模型等设置框不会改变接收位置。
4. API 配置完成默认启用 AI 发送；点击发送能看到转圈与秒数，收到 AI 译文后原文清空。手动关闭并重开设置，关闭选择应保留。
5. 断网时机翻预览可用；AI 失败不发送机翻，原文保留。AI 等待时修改原文，不发送旧结果；重复发送不产生重复请求。
6. 检查日夜外观、图标提示、置顶、拖动缩放、Alt-Tab 排除、关闭目标及锁屏后的取消。实际云端质量和用户虚拟机 / 应用需人工验收。

GitHub Ubuntu 24.04 上运行单元测试、真实 Rime / IBus / GTK、GNOME 46 Wayland 目标切换、本地模拟 API、断网模型推理和资源检查；不使用 WSL。

## 清理

原有 `cleanup-legacy` 保留配置、密钥、词库和输入记录。只删除记录可在设置里清空，或退出面板后删除 `~/.config/rime-llm-translator/long-text.json`。不要删除整个 `.config/ibus`。

停用桥接：`gnome-extensions disable rime-llm-translator@le-saber`。卸载后如需清理用户副本，只删除 `~/.local/share/gnome-shell/extensions/rime-llm-translator@le-saber`，不影响其他扩展。
