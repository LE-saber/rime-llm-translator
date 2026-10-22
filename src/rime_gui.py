"""On-demand GTK3 editor/settings; no web runtime and no network on typing."""
import json
import os
import subprocess
import sys
import time

# Force a distinguishable IBus client, also when GNOME defaults to Wayland IM.
os.environ["GTK_IM_MODULE"] = "ibus"
# Xwayland utility windows honor skip-taskbar/pager hints on GNOME 46 too.
# The original application may remain native Wayland; Shell owns submission.
if os.environ.get("WAYLAND_DISPLAY") and os.environ.get("DISPLAY"):
    os.environ["GDK_BACKEND"] = "x11"
import gi
gi.require_version("Gtk", "3.0")
gi.require_version("Gdk", "3.0")
gi.require_version("IBus", "1.0")
from gi.repository import Gdk, Gio, GLib, Gtk, Pango

import rime_llm_translator as core
from rime_long_text import Draft, History, MAX_BYTES, validate_shortcuts

BRIDGE = "im.rime.LLMTranslator.Bridge"
BRIDGE_PATH = "/im/rime/LLMTranslator/Bridge"
MODS = [(Gdk.ModifierType.CONTROL_MASK, "Control"),
        (Gdk.ModifierType.MOD1_MASK, "Alt"), (Gdk.ModifierType.SHIFT_MASK, "Shift"),
        (Gdk.ModifierType.SUPER_MASK, "Super")]
MODIFIER_KEYS = {"Alt_L", "Alt_R", "Control_L", "Control_R", "Shift_L", "Shift_R", "Super_L", "Super_R"}
BUTTONS = {"copy": "复制", "paste": "粘贴", "symbols": "符号",
           "translate": "AI 翻译", "settings": "设置"}
ICONS = {"copy": "edit-copy-symbolic", "paste": "edit-paste-symbolic",
         "symbols": "face-smile-symbolic", "translate": "tools-check-spelling-symbolic",
         "settings": "emblem-system-symbolic"}
DATA_PATH = core.CONFIG_DIR / "long-text.json"


def call_bridge(method, signature="()", values=()):
    connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
    return connection.call_sync(BRIDGE, BRIDGE_PATH, BRIDGE, method,
        GLib.Variant(signature, values), None, Gio.DBusCallFlags.NONE, 1500, None).unpack()[0]


def key_binding(event):
    name = Gdk.keyval_name(Gdk.keyval_to_lower(event.keyval)) or ""
    if name in MODIFIER_KEYS:
        return None
    return "+".join([label for mask, label in MODS if event.state & mask] + [name])


class TapMatcher:
    def __init__(self):
        self.reset()

    def reset(self):
        self.down, self.last, self.count = None, 0, 0

    def event(self, event, release=False):
        name = Gdk.keyval_name(event.keyval)
        if name not in ("Alt_L", "Alt_R") or event.state & (
                Gdk.ModifierType.CONTROL_MASK | Gdk.ModifierType.SHIFT_MASK | Gdk.ModifierType.SUPER_MASK):
            self.reset()
            return None
        now = time.monotonic()
        if not release:
            if self.down is not None:
                self.down = -1
                self.count = 0
            else:
                self.down = now
            return None
        if self.down is None or self.down < 0 or now - self.down > .4:
            self.reset()
            return None
        self.count = self.count + 1 if now - self.last <= .4 else 1
        self.last, self.down = now, None
        return {2: "DoubleAlt", 3: "TripleAlt"}.get(self.count)


class EditorWindow(Gtk.ApplicationWindow):
    def __init__(self, app):
        super().__init__(application=app, title="Rime Translator · 长文本")
        self.cfg = core.load_config()
        self.draft = Draft()
        self.token, self.queued, self.send_mode = None, False, None
        self.target_supported = True
        self.hidden_at, self.debounce = None, 0
        self.busy_started = None
        self.next_target_check = 0
        self.recalling = False
        self.taps = TapMatcher()
        try:
            data = json.loads(DATA_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            data = {}
        self.history = History(data.get("history", []))
        # Old versions restored a draft automatically. Preserve it as history,
        # while every new opening now starts with an empty editor.
        legacy_draft = data.get("draft", "")
        if self.cfg.getboolean("panel", "history_enabled") and isinstance(legacy_draft, str):
            self.history.add(legacy_draft)
        self.set_default_size(max(600, min(self.cfg.getint("panel", "width"), 1800)),
                              max(320, min(self.cfg.getint("panel", "height"), 1200)))
        self.set_size_request(600, 320)
        self.set_decorated(False)
        self.set_keep_above(True)
        self.set_skip_taskbar_hint(True)
        self.set_skip_pager_hint(True)
        self.set_type_hint(Gdk.WindowTypeHint.UTILITY)
        self.set_position(Gtk.WindowPosition.CENTER)
        self.connect("delete-event", self.close_panel)
        self.connect("focus-out-event", lambda *_: self.taps.reset())
        self.get_style_context().add_class("editor")
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=16)
        self.add(box)
        heading = Gtk.Box(spacing=12)
        drag = Gtk.EventBox()
        title = Gtk.Label(label="长文本翻译", xalign=0)
        title.get_style_context().add_class("panel-title")
        drag.add(title)
        drag.set_tooltip_text("拖动移动面板")
        drag.connect("button-press-event", self.move_panel)
        heading.pack_start(drag, True, True, 0)
        close = self.icon_button("window-close-symbolic", "关闭并保存到输入记录")
        close.connect("clicked", self.close_panel)
        heading.pack_end(close, False, False, 0)
        self.theme = self.icon_button("weather-clear-night-symbolic", "切换日间 / 夜间")
        self.theme.connect("clicked", self.toggle_theme)
        heading.pack_end(self.theme, False, False, 0)
        box.pack_start(heading, False, False, 0)
        self.target_label = Gtk.Label(label="从目标输入框打开后绑定发送位置", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.target_label.get_style_context().add_class("muted")
        box.pack_start(self.target_label, False, False, 0)
        self.paned = Gtk.Paned(orientation=Gtk.Orientation.HORIZONTAL)
        left = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_end=6)
        source_heading = Gtk.Box(spacing=8)
        source_heading.set_size_request(-1, 26)
        source_heading.pack_start(Gtk.Label(label="原文", xalign=0), True, True, 0)
        self.counter = Gtk.Label(label="0 字")
        self.counter.get_style_context().add_class("muted")
        source_heading.pack_end(self.counter, False, False, 0)
        left.pack_start(source_heading, False, False, 0)
        self.source = Gtk.TextView(wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=12,
                                   right_margin=12, top_margin=12, bottom_margin=12)
        self.source.get_style_context().add_class("source")
        self.buffer = self.source.get_buffer()
        self.buffer.connect("changed", self.changed)
        self.source.connect("preedit-changed", self.preedit_changed)
        self.composing = False
        left.pack_start(self.scrolled(self.source), True, True, 0)
        right = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=8, margin_start=6)
        preview_heading = Gtk.Box(spacing=8)
        preview_heading.set_size_request(-1, 26)
        preview_heading.pack_start(Gtk.Label(label="译文预览", xalign=0), True, True, 0)
        self.preview_mode = Gtk.Label(label="机翻")
        self.preview_mode.get_style_context().add_class("badge")
        preview_heading.pack_end(self.preview_mode, False, False, 0)
        right.pack_start(preview_heading, False, False, 0)
        self.languages = Gtk.ComboBoxText()
        self.languages.connect("changed", self.changed)
        self.languages.set_tooltip_text("选择预览和发送语言")
        self.preview = Gtk.TextView(editable=False, cursor_visible=False,
                                   wrap_mode=Gtk.WrapMode.WORD_CHAR, left_margin=10,
                                   right_margin=10, top_margin=12, bottom_margin=10)
        self.preview.get_style_context().add_class("preview")
        right.pack_start(self.scrolled(self.preview), True, True, 0)
        right.pack_start(self.languages, False, False, 0)
        self.paned.pack1(left, True, False)
        self.paned.pack2(right, False, False)
        self.paned.set_position(int(self.get_default_size()[0] * .73))
        box.pack_start(self.paned, True, True, 0)
        toolbar = Gtk.Box(spacing=8)
        actions = {"copy": self.copy_source, "paste": self.paste, "symbols": self.symbols,
                   "translate": self.ai, "settings": self.settings}
        self.buttons = {}
        for name, label in BUTTONS.items():
            button = self.icon_button(ICONS[name], label, label if name == "translate" else None)
            button.connect("clicked", actions[name])
            toolbar.pack_start(button, False, False, 0)
            self.buttons[name] = button
        self.auto_ai_toggle = Gtk.CheckButton(label="发送用 AI")
        self.auto_ai_toggle.set_tooltip_text("配置 API 后默认生效；只在发送时调用 AI，实时预览仍用机翻")
        self.auto_ai_toggle.connect("toggled", self.toggle_auto_ai)
        toolbar.pack_start(self.auto_ai_toggle, False, False, 6)
        self.send_button = Gtk.Button()
        send_content = Gtk.Box(spacing=8, halign=Gtk.Align.CENTER)
        self.send_icon = Gtk.Image.new_from_icon_name("mail-send-symbolic", Gtk.IconSize.BUTTON)
        self.send_spinner = Gtk.Spinner()
        self.send_spinner.set_no_show_all(True)
        self.send_label = Gtk.Label(label="发送译文")
        send_content.pack_start(self.send_icon, False, False, 0)
        send_content.pack_start(self.send_spinner, False, False, 0)
        send_content.pack_start(self.send_label, False, False, 0)
        self.send_button.add(send_content)
        self.send_button.get_style_context().add_class("send")
        self.send_button.connect("clicked", self.send)
        toolbar.pack_end(self.send_button, False, False, 0)
        box.pack_start(toolbar, False, False, 0)
        footer = Gtk.Box(spacing=8)
        self.message = Gtk.Label(label="输入原文开始预览 · 空白时按 ↑ 找回记录", xalign=0, ellipsize=Pango.EllipsizeMode.END)
        self.message.get_style_context().add_class("muted")
        footer.pack_start(self.message, True, True, 0)
        grip = Gtk.EventBox(halign=Gtk.Align.END)
        grip.add(Gtk.Label(label="◢"))
        grip.set_tooltip_text("拖动调整大小")
        grip.connect("button-press-event", self.resize_panel)
        footer.pack_end(grip, False, False, 0)
        box.pack_end(footer, False, False, 0)
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.mouse_shortcut)
        self.refresh_config()
        self.changed()
        self.persist_history()
        GLib.timeout_add(120, self.poll)

    @staticmethod
    def icon_button(icon, label, text=None):
        button = Gtk.Button()
        content = Gtk.Box(spacing=6, halign=Gtk.Align.CENTER)
        content.pack_start(Gtk.Image.new_from_icon_name(icon, Gtk.IconSize.BUTTON), False, False, 0)
        if text:
            content.pack_start(Gtk.Label(label=text), False, False, 0)
        button.add(content)
        button.set_tooltip_text(label)
        button.get_accessible().set_name(label)
        return button

    def move_panel(self, _, event):
        if event.button == 1:
            self.begin_move_drag(1, int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    def resize_panel(self, _, event):
        if event.button == 1:
            self.begin_resize_drag(Gdk.WindowEdge.SOUTH_EAST, 1,
                                   int(event.x_root), int(event.y_root), event.time)
            return True
        return False

    @staticmethod
    def scrolled(widget):
        scroll = Gtk.ScrolledWindow(hexpand=True, vexpand=True)
        scroll.set_policy(Gtk.PolicyType.AUTOMATIC, Gtk.PolicyType.AUTOMATIC)
        scroll.add(widget)
        return scroll

    def text(self):
        return self.buffer.get_text(self.buffer.get_start_iter(), self.buffer.get_end_iter(), True)

    def preedit_changed(self, widget, preedit):
        self.composing = bool(preedit)

    def show_message(self, text):
        self.message.set_text(text)
        self.message.set_tooltip_text(text)

    def update_send_state(self):
        waiting_ai = self.busy_started is not None and self.send_mode == "ai"
        self.send_spinner.set_visible(waiting_ai)
        self.send_icon.set_visible(not waiting_ai)
        if waiting_ai:
            self.send_spinner.start()
            self.send_label.set_text("AI 翻译 %.1f s" % (time.monotonic() - self.busy_started))
        else:
            self.send_spinner.stop()
            auto_ai = self.cfg.getboolean("panel", "auto_ai_send") and self.ai_configured
            self.send_label.set_text("AI 翻译并发送" if auto_ai else "发送译文")
        self.send_button.set_sensitive(self.target_supported and not waiting_ai and not self.queued)

    def toggle_auto_ai(self, *_):
        if getattr(self, "refreshing", False):
            return
        cfg = core.load_config()
        cfg["panel"]["auto_ai_send"] = str(self.auto_ai_toggle.get_active()).lower()
        core.save_config(cfg)
        self.cfg = cfg
        self.changed()

    def persist_history(self):
        core.atomically_write(DATA_PATH, json.dumps({"history": self.history.entries}, ensure_ascii=False))

    def target_expired(self):
        self.target_supported = False
        self.send_mode, self.busy_started = None, None
        self.cancel_job("ai")
        self.remember()
        self.target_label.set_text("目标已失效 · 请点中目标输入框后重新打开")
        self.show_message("发送已暂停，文本已留在记录中；回到目标输入框重新打开，按 ↑ 找回")
        self.update_send_state()

    def refresh_config(self, reset_language=False):
        self.cfg = core.load_config()
        selected = None if reset_language else self.languages.get_active_id()
        self.refreshing = True
        self.languages.remove_all()
        for code, label in core.parse_languages(self.cfg["translation"]["languages"]).items():
            self.languages.append(code, label)
        self.languages.set_active_id(selected or self.cfg["panel"]["preferred_language"])
        if not self.languages.get_active_id():
            self.languages.set_active(0)
        dark = self.cfg["panel"]["theme"] == "dark"
        background, surface, foreground, border, accent = (
            ("#282a36", "#343746", "#f2f2f2", "#505362", "#bd93f9") if dark else
            ("#f4f4f4", "#ffffff", "#252525", "#d9d9d9", "#454545"))
        muted = "#b1b3c4" if dark else "#646464"
        css = """
        * {font-family: "Noto Sans CJK SC", "Noto Sans CJK TC", sans-serif;}
        window, dialog, notebook, notebook header {background: BG; color: FG;}
        textview, textview text, entry, treeview {background: SF; color: FG;}
        button, combobox button {background: SF; color: FG; border: 1px solid BD;
                                border-radius: 7px; box-shadow: none; padding: 7px 10px; min-height: 18px;}
        button:hover {border-color: AC;} button:disabled {opacity: 0.65;}
        checkbutton check:checked {background: AC; color: SF; border-color: AC;}
        notebook tab:checked {background: SF; border-color: AC;} *:focus {outline-color: AC;}
        notebook header tabs tab:checked {box-shadow: none; border-bottom: 2px solid AC;}
        label, checkbutton {color: FG;} selection {background: AC; color: SF;}
        .panel-title {font-size: 15px; font-weight: 600;}
        .muted {color: MUTED; font-size: 11px;}
        .badge {background: SF; color: MUTED; border-radius: 5px; padding: 3px 7px; font-size: 11px;}
        .source {font-size: 17px;} .preview {font-size: 12px;}
        .send {background: AC; color: BG; text-shadow: none;}
        .send label, .send image, .send spinner {color: BG; text-shadow: none;}
        scrolledwindow {border: 1px solid BD; border-radius: 8px; background: SF;}
        paned separator {background: transparent; min-width: 4px;}
        """
        for key, value in (("MUTED", muted), ("BG", background), ("SF", surface), ("FG", foreground), ("BD", border), ("AC", accent)):
            css = css.replace(key, value)
        if hasattr(self, "css"):
            Gtk.StyleContext.remove_provider_for_screen(Gdk.Screen.get_default(), self.css)
        self.css = Gtk.CssProvider()
        self.css.load_from_data(css.encode())
        Gtk.StyleContext.add_provider_for_screen(Gdk.Screen.get_default(), self.css,
                                                  Gtk.STYLE_PROVIDER_PRIORITY_APPLICATION)
        enabled = self.cfg["panel"]["buttons"].split(",")
        for name, button in self.buttons.items():
            button.set_no_show_all(name not in enabled)
            button.set_visible(name in enabled)
        self.ai_configured = core.provider_ready(self.cfg)
        self.auto_ai_toggle.set_active(self.cfg.getboolean("panel", "auto_ai_send"))
        self.theme.get_child().get_children()[0].set_from_icon_name(
            "weather-clear-symbolic" if dark else "weather-clear-night-symbolic", Gtk.IconSize.BUTTON)
        self.refreshing = False
        self.update_send_state()

    def open(self, token):
        if self.queued:
            self.show_message("正在等待原输入框，完成或取消后再打开")
            return
        if self.text().strip():
            self.remember()
        self.token = token
        self.target_supported = True
        self.refresh_config(reset_language=True)
        try:
            raw = (core.CACHE_DIR / "panel-open").read_text(encoding="utf-8").split("\n", 1)
            if raw[0] == token and len(raw) == 2 and raw[1]:
                if self.cfg.getboolean("panel", "history_enabled"):
                    self.history.add(raw[1])
            if raw[0] == token:
                (core.CACHE_DIR / "panel-open").unlink(missing_ok=True)
            state = call_bridge("State", "(s)", (token,))
            self.target_supported = state == "editing"
            target = call_bridge("Target", "(s)", (token,))
            self.target_label.set_text("发送到：" + target)
            self.target_label.set_tooltip_text("最近选择的真实输入位置 · " + target + "；悬浮编辑区不会成为发送目标")
            self.show_message("GNOME 桌面桥接未启用：运行 sync 和 enable 后注销再登录"
                              if state == "unsupported" else "选词先进入原文；发送时自动返回原输入框")
        except (OSError, GLib.Error):
            self.show_message("未绑定输入框。请在 Rime Translator 输入框中用快捷键或菜单打开")
        self.history.index, self.history.bookmark = -1, ""
        self.buffer.set_text("")
        self.persist_history()
        self.hidden_at = None
        self.show_all()
        self.present()
        self.source.grab_focus()
        self.changed()
        if not self.target_supported:
            self.send_button.set_sensitive(False)
            self.show_message("请运行 rime-llm-translator sync && rime-llm-translator enable，注销再登录以启用桌面桥接")
        self.update_send_state()

    def changed(self, *_):
        if not hasattr(self, "languages") or getattr(self, "refreshing", False):
            return
        if not self.recalling:
            self.history.index = -1
        self.draft.edit(self.text(), self.languages.get_active_id() or "en")
        self.send_mode = None
        self.busy_started = None
        self.update_send_state()
        self.counter.set_text("%d 字" % len(self.text()))
        self.preview_mode.set_text("机翻")
        for mode in ("mt", "ai"):
            self.cancel_job(mode)
        if self.debounce:
            GLib.source_remove(self.debounce)
            self.debounce = 0
        self.preview.get_buffer().set_text("")
        if not self.text().strip():
            self.show_message("输入原文开始预览 · 空白时按 ↑ 找回记录")
            return
        if len(self.text().encode()) > MAX_BYTES:
            self.show_message("原文超过 32 KiB，请缩短或分次发送；不会截断发送")
            return
        self.debounce = GLib.timeout_add(max(200, self.cfg.getint("translation", "debounce_ms")), self.start_mt)
        self.show_message("机翻预览 · 修改后不会自动调用 AI")

    def cancel_job(self, mode):
        core.atomically_write(core.CACHE_DIR / ("panel-" + mode + ".req"), "{}")

    def start_mt(self):
        self.debounce = 0
        if self.get_visible() and self.draft.source.strip():
            self.request("mt")
        return False

    def request(self, mode):
        if not self.draft.source.strip() or len(self.draft.source.encode()) > MAX_BYTES:
            return
        already = mode in self.draft.jobs
        job = self.draft.job(mode)
        if not already:
            core.atomically_write(core.CACHE_DIR / ("panel-" + mode + ".req"),
                                  json.dumps(job, ensure_ascii=False))
        self.show_message(("AI 翻译中" if mode == "ai" else "机翻预览更新中") + " · 可继续编辑，旧结果会丢弃")

    def ai(self, *_):
        self.remember()
        if "ai" in self.draft.results:
            self.preview_mode.set_text("AI")
            self.preview.get_buffer().set_text(self.draft.results["ai"])
            self.show_message("AI 译文 · 本次结果已复用")
        else:
            self.request("ai")

    def send(self, *_):
        if self.queued or self.composing:
            self.show_message("请先完成拼音选词，再发送译文")
            return
        if not self.text().strip():
            self.show_message("请先输入原文，或按 ↑ 找回最近记录")
            return
        if len(self.text().encode()) > MAX_BYTES:
            self.show_message("原文超过 32 KiB，请缩短或分次发送；不会截断发送")
            return
        if self.send_mode is not None:
            return  # The button and recorded send shortcut share one intent.
        if not self.token:
            self.show_message("请从目标输入框打开长文本模式，再发送")
            return
        if not self.target_supported:
            self.show_message("此目标不支持安全直接发送，请在译文中右键复制")
            return
        try:
            if call_bridge("State", "(s)", (self.token,)) != "editing":
                self.target_expired()
                return
        except GLib.Error:
            self.show_message("输入法连接已失效，请重新打开长文本；原文已保留")
            return
        mode, text = self.draft.begin_send(core.auto_ai_enabled(self.cfg))
        self.send_mode = mode
        if text:
            self.queue(text)
        else:
            if mode == "ai":
                self.busy_started = time.monotonic()
            self.update_send_state()
            self.request(mode)

    def queue(self, text):
        if not self.draft.ready(self.send_mode):
            return
        try:
            call_bridge("Queue", "(ss)", (self.token, text))
        except GLib.Error:
            self.send_mode = None
            self.busy_started = None
            self.update_send_state()
            self.show_message("无法安全发送到原目标；原文保留。可在译文上右键复制，或从目标重新打开")
            return
        self.remember()
        self.queued = True
        self.hide()
        try:
            call_bridge("Restore", "(s)", (self.token,))
        except GLib.Error:
            pass  # Independent IBus contexts can still be focused manually.
        self.show_message("正在返回原输入框并发送译文")

    def poll(self):
        if self.busy_started is not None:
            self.update_send_state()
        if self.queued:
            try:
                state = call_bridge("State", "(s)", (self.token,))
            except GLib.Error:
                state = "failed"
            if state != "waiting":
                self.queued = False
                self.busy_started = None
                self.send_mode = None
                if state == "sent":
                    self.draft.sent()
                    self.buffer.set_text("")
                    self.persist_history()
                    self.hidden_at = time.monotonic()
                    self.show_message("译文已发送；下次恢复机翻预览")
                else:
                    self.show_all()
                    self.present()
                    self.show_message("发送已取消或超时，原文保留。请重新打开目标后发送")
                self.update_send_state()
            return True
        if self.token and self.get_visible() and self.target_supported and time.monotonic() >= self.next_target_check:
            self.next_target_check = time.monotonic() + .6
            try:
                state = call_bridge("State", "(s)", (self.token,))
            except GLib.Error:
                state = "failed"
            if state not in ("editing", "sent"):
                self.target_expired()
            elif state == "editing":
                try:
                    target = call_bridge("Target", "(s)", (self.token,))
                    self.target_label.set_text("发送到：" + target)
                    self.target_label.set_tooltip_text("最近选择的真实输入位置 · " + target + "；悬浮编辑区不会成为发送目标")
                except GLib.Error:
                    self.target_expired()
        for mode in ("mt", "ai"):
            job = self.draft.jobs.get(mode)
            if not job or job.get("done"):
                continue
            path = core.CACHE_DIR / ("panel-" + mode + ".res")
            try:
                result = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            if not self.draft.accept(mode, result):
                continue
            job["done"] = True
            if "error" in result:
                self.show_message(result.get("message", "翻译失败，原文保留"))
                self.draft.jobs.pop(mode, None)  # explicit retry is permitted
                if self.send_mode == mode:
                    self.send_mode = None
                    self.busy_started = None
                    self.update_send_state()
            else:
                if mode == "ai" or "ai" not in self.draft.results:
                    self.preview.get_buffer().set_text(result["text"])
                    self.preview_mode.set_text("AI" if mode == "ai" else "机翻")
                    if not (self.send_mode == "ai" and mode == "mt"):
                        self.show_message(("AI 译文" if mode == "ai" else "机翻预览") + " · " + self.draft.language.upper())
                if self.send_mode == mode and self.draft.ready(mode):
                    self.queue(result["text"])
        if self.hidden_at and time.monotonic() - self.hidden_at > 120:
            self.get_application().quit()
            return False
        return True

    def remember(self):
        if self.cfg.getboolean("panel", "history_enabled"):
            self.history.add(self.text())
        cfg = core.load_config()
        width, height = self.get_size()
        cfg["panel"]["width"], cfg["panel"]["height"] = str(width), str(height)
        core.save_config(cfg)
        self.persist_history()

    def close_panel(self, *_):
        self.remember()
        self.send_mode = None
        self.busy_started = None
        for mode in ("mt", "ai"):
            self.cancel_job(mode)
        if self.token:
            try:
                call_bridge("Cancel", "(s)", (self.token,))
            except GLib.Error:
                pass
        self.queued = False
        self.update_send_state()
        self.hide()
        self.hidden_at = time.monotonic()
        return True

    def copy_source(self, *_):
        Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD).set_text(self.text(), -1)

    def paste(self, *_):
        clipboard = Gtk.Clipboard.get(Gdk.SELECTION_CLIPBOARD)
        self.buffer.paste_clipboard(clipboard, None, True)

    def symbols(self, *_):
        popup = Gtk.Popover.new(self.buttons["symbols"])
        grid = Gtk.Grid(column_spacing=4, row_spacing=4, margin=10)
        for i, symbol in enumerate("，。？！；：、…—「」『』（）《》【】“”‘’·"):
            button = Gtk.Button(label=symbol)
            button.connect("clicked", lambda _, value=symbol: (self.buffer.insert_at_cursor(value), popup.hide()))
            grid.attach(button, i % 8, i // 8, 1, 1)
        popup.add(grid)
        popup.show_all()

    def toggle_theme(self, *_):
        cfg = core.load_config()
        cfg["panel"]["theme"] = "dark" if cfg["panel"]["theme"] != "dark" else "light"
        core.save_config(cfg)
        self.refresh_config()

    def settings(self, *_):
        self.remember()
        Settings(self).run_and_save()

    def action(self, binding):
        # CLI changes to bindings take effect in an already open panel too.
        cfg = core.load_config()
        if binding == cfg["translation"]["ai_hotkey"]:
            self.ai()
        elif binding == cfg["panel"]["send_hotkey"]:
            self.send()
        elif binding == cfg["panel"]["open_hotkey"]:
            self.close_panel()
        else:
            return False
        return True

    def do_key_press_event(self, event):
        gesture = self.taps.event(event)
        if gesture and self.action(gesture):
            return True
        binding = key_binding(event)
        if binding and self.action(binding):
            return True
        # Normal multiline cursor movement and composing candidates keep Up/Down.
        if self.get_focus() == self.source and not self.composing and event.state & 13 == 0:
            cursor = self.buffer.get_iter_at_mark(self.buffer.get_insert())
            has_selection = self.buffer.get_has_selection()
            up = event.keyval == Gdk.KEY_Up
            down = event.keyval == Gdk.KEY_Down
            boundary = (up and cursor.get_line() == 0) or (down and cursor.get_line() == self.buffer.get_line_count() - 1)
            if (up or down) and not has_selection and (boundary or self.history.index >= 0):
                recalled = self.history.move(-1 if up else 1, self.text())
                self.recalling = True
                self.buffer.set_text(recalled)
                self.recalling = False
                return True
        return Gtk.ApplicationWindow.do_key_press_event(self, event)

    def do_key_release_event(self, event):
        gesture = self.taps.event(event, True)
        if gesture and self.action(gesture):
            return True
        return Gtk.ApplicationWindow.do_key_release_event(self, event)

    def mouse_shortcut(self, _, event):
        if event.button >= 8:
            binding = "+".join([label for mask, label in MODS if event.state & mask] + ["Button" + str(event.button)])
            return self.action(binding)
        return False


class Settings(Gtk.Dialog):
    def __init__(self, editor):
        super().__init__(title="Rime Translator · 设置", transient_for=editor, modal=True)
        self.editor, self.cfg = editor, core.load_config()
        self.set_default_size(680, 530)
        self.add_buttons("取消", Gtk.ResponseType.CANCEL, "保存", Gtk.ResponseType.OK)
        self.notebook = Gtk.Notebook()
        self.get_content_area().pack_start(self.notebook, True, True, 0)
        self.entries, self.checks, self.bindings = {}, {}, {}
        translation = self.page("翻译")
        translation.pack_start(Gtk.Label(label="目标语言", xalign=0), False, False, 0)
        configured = core.parse_languages(self.cfg["translation"]["languages"])
        self.language_names = {"en": "English", "ja": "Japanese", "fr": "French", "ko": "Korean"}
        self.language_names.update(configured)
        self.language_checks = {}
        for code, label in self.language_names.items():
            check = Gtk.CheckButton(label=label + (" · 离线 / AI" if code in ("en", "ja") else " · 仅 AI"))
            check.set_active(code in configured)
            self.language_checks[code] = check
            check.connect("toggled", self.language_toggled)
            translation.pack_start(check, False, False, 0)
        translation.pack_start(Gtk.Label(label="优先预览语言", xalign=0), False, False, 0)
        self.preferred = Gtk.ComboBoxText()
        translation.pack_start(self.preferred, False, False, 0)
        self.language_toggled()
        self.preferred.set_active_id(self.cfg["panel"]["preferred_language"])
        self.check(translation, "发送自动 AI 翻译（只在发送时触发，不会随打字调用 AI）", "auto_ai_send")
        translation.pack_start(Gtk.Label(label="机翻实时预览：英语、日语。其他语言仅手动 AI；失败保留原文。", wrap=True, xalign=0), False, False, 0)
        provider = self.page("API / 模型")
        self.entry(provider, "OpenAI 兼容 API 地址", "base_url", self.cfg["provider"]["base_url"])
        self.entry(provider, "模型", "model", self.cfg["provider"]["model"])
        self.entry(provider, "API Key（留空保留原密钥）", "key", "", secret=True)
        self.entry(provider, "请求超时（秒，2–60）", "timeout_seconds", self.cfg["translation"]["timeout_seconds"])
        shortcuts = self.page("快捷键")
        for name, label, value in (("open", "打开 / 收起长文本", self.cfg["panel"]["open_hotkey"]),
                                    ("ai", "手动 AI 翻译", self.cfg["translation"]["ai_hotkey"]),
                                    ("send", "发送译文", self.cfg["panel"]["send_hotkey"])):
            self.bindings[name] = value
            row = Gtk.Box(spacing=8)
            row.pack_start(Gtk.Label(label=label, xalign=0), True, True, 0)
            button = Gtk.Button(label=value + " · 重新录制")
            button.connect("clicked", self.record, name)
            row.pack_end(button, False, False, 0)
            shortcuts.pack_start(row, False, False, 0)
        shortcuts.pack_start(Gtk.Label(label="点击录制后实际按键。支持组合键、双 / 三击 Alt、面板内鼠标侧键。\n打开快捷键依赖 IBus 收到按键；Alt+Space 可能被桌面窗口菜单占用，可改用 Ctrl+Alt+Space。\n鼠标侧键用于面板内 AI / 发送；IBus 不接收原应用鼠标事件，不能绑定为打开键。\n普通候选 AI 继续支持原 CLI 组合键 / 双击 Alt；面板支持更多录制手势。", wrap=True, xalign=0), False, False, 0)
        appearance = self.page("外观")
        self.dark = Gtk.CheckButton(label="夜间模式（Dracula 风格）")
        self.dark.set_active(self.cfg["panel"]["theme"] == "dark")
        appearance.pack_start(self.dark, False, False, 0)
        for name, label in BUTTONS.items():
            self.check(appearance, "显示“" + label + "”按钮", "button_" + name,
                       name in self.cfg["panel"]["buttons"].split(","))
        history = self.page("输入记录")
        self.check(history, "保存输入记录（仅本机，最多 50 条）", "history_enabled")
        history.pack_start(Gtk.Label(label="原文首行 ↑ / 末行 ↓ 回溯；关闭记录不会自动删除现有记录。", xalign=0, wrap=True), False, False, 0)
        clear = Gtk.Button(label="清空记录")
        clear.connect("clicked", self.clear_history)
        history.pack_start(clear, False, False, 0)
        self.history_box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=4)
        for text in editor.history.entries:
            button = Gtk.Button(label=text.replace("\n", " ")[:90])
            button.connect("clicked", self.restore, text)
            self.history_box.pack_start(button, False, False, 0)
        history.pack_start(editor.scrolled(self.history_box), True, True, 0)
        self.error = Gtk.Label(xalign=0, wrap=True)
        self.get_content_area().pack_end(self.error, False, False, 8)

    def page(self, title):
        box = Gtk.Box(orientation=Gtk.Orientation.VERTICAL, spacing=12, margin=18)
        self.notebook.append_page(box, Gtk.Label(label=title))
        return box

    def language_toggled(self, *_):
        if not hasattr(self, "preferred"):
            return
        previous = self.preferred.get_active_id()
        self.preferred.remove_all()
        for code, check in self.language_checks.items():
            if check.get_active():
                self.preferred.append(code, self.language_names[code])
        self.preferred.set_active_id(previous or "en")
        if not self.preferred.get_active_id():
            self.preferred.set_active(0)

    def entry(self, page, label, key, value, secret=False):
        page.pack_start(Gtk.Label(label=label, xalign=0), False, False, 0)
        entry = Gtk.Entry(text=value, visibility=not secret)
        if secret:
            entry.set_input_purpose(Gtk.InputPurpose.PASSWORD)
        page.pack_start(entry, False, False, 0)
        self.entries[key] = entry

    def check(self, page, label, key, value=None):
        check = Gtk.CheckButton(label=label)
        check.set_active(self.cfg.getboolean("panel", key) if value is None else value)
        self.checks[key] = check
        page.pack_start(check, False, False, 0)

    def clear_history(self, *_):
        self.editor.history = History()
        self.editor.persist_history()
        for child in self.history_box.get_children():
            child.destroy()

    def restore(self, _, text):
        self.editor.buffer.set_text(text)
        self.response(Gtk.ResponseType.CANCEL)

    def record(self, button, name):
        dialog = Recorder(self)
        value = dialog.capture()
        if value:
            self.bindings[name] = value
            button.set_label(value + " · 重新录制")

    def run_and_save(self):
        self.show_all()
        while self.run() == Gtk.ResponseType.OK:
            try:
                cfg = core.load_config()  # preserve CLI/unknown settings edited meanwhile
                value = lambda name: self.entries[name].get_text().strip()
                languages_raw = ",".join(code + ":" + self.language_names[code]
                                         for code, check in self.language_checks.items() if check.get_active())
                languages = core.parse_languages(languages_raw)
                core.chat_url(value("base_url"))
                if not value("model"):
                    raise ValueError("模型名称不能为空")
                timeout = float(value("timeout_seconds"))
                if not 2 <= timeout <= 60:
                    raise ValueError("超时应为 2–60 秒")
                if self.preferred.get_active_id() not in languages:
                    raise ValueError("优先语言必须包含在目标语言中")
                validate_shortcuts(self.bindings)
                # Opening must work from an IBus keyboard event, without global hooks.
                if "Button" in self.bindings["open"]:
                    raise ValueError("鼠标侧键只能绑定面板内 AI / 发送，打开键请录制键盘组合")
                for name in ("open", "ai", "send"):
                    binding = self.bindings[name]
                    if binding not in ("DoubleAlt", "TripleAlt") and "Button" not in binding:
                        core.normalize_hotkey(binding)
                cfg["translation"]["languages"] = languages_raw
                cfg["translation"]["timeout_seconds"] = value("timeout_seconds")
                cfg["translation"]["ai_hotkey"] = self.bindings["ai"]
                cfg["panel"]["open_hotkey"] = self.bindings["open"]
                cfg["panel"]["send_hotkey"] = self.bindings["send"]
                cfg["panel"]["preferred_language"] = self.preferred.get_active_id()
                cfg["panel"]["theme"] = "dark" if self.dark.get_active() else "light"
                for key in ("auto_ai_send", "history_enabled"):
                    cfg["panel"][key] = str(self.checks[key].get_active()).lower()
                cfg["panel"]["buttons"] = ",".join(name for name in BUTTONS if self.checks["button_" + name].get_active())
                cfg["provider"]["base_url"], cfg["provider"]["model"] = value("base_url"), value("model")
                if value("key"):
                    core.atomically_write(core.KEY_PATH, value("key") + "\n")
                core.save_config(cfg)
                self.editor.refresh_config(reset_language=True)
                self.editor.changed()
                self.editor.show_message("已保存；普通输入法无需重启。若 Alt+Space 被桌面占用，请重新录制打开键")
                break
            except (ValueError, OSError) as exc:
                self.error.set_text(str(exc))
        self.destroy()


class Recorder(Gtk.Dialog):
    def __init__(self, parent):
        super().__init__(title="录制快捷键", transient_for=parent, modal=True)
        self.set_default_size(420, 180)
        self.add_buttons("取消", Gtk.ResponseType.CANCEL, "使用此快捷键", Gtk.ResponseType.OK)
        self.set_response_sensitive(Gtk.ResponseType.OK, False)
        self.label = Gtk.Label(label="请实际按键，或在此窗口按鼠标侧键\n连续点按请在 400 毫秒内完成", margin=20)
        self.get_content_area().add(self.label)
        self.value, self.last_key, self.count, self.last_time, self.down = None, None, 0, 0, None
        self.add_events(Gdk.EventMask.BUTTON_PRESS_MASK)
        self.connect("button-press-event", self.mouse)

    def choose(self, value):
        self.value = value
        self.label.set_text(value)
        self.set_response_sensitive(Gtk.ResponseType.OK, True)

    def do_key_press_event(self, event):
        if event.keyval == Gdk.KEY_Escape:
            self.response(Gtk.ResponseType.CANCEL)
            return True
        name = Gdk.keyval_name(event.keyval)
        if name in ("Alt_L", "Alt_R"):
            self.down = time.monotonic() if self.down is None else -1
        else:
            self.down = None
            self.count = 0
            binding = key_binding(event)
            if binding and "+" in binding:
                self.choose(binding)
        return True

    def do_key_release_event(self, event):
        name, now = Gdk.keyval_name(event.keyval), time.monotonic()
        if name in ("Alt_L", "Alt_R") and self.down and self.down > 0 and now - self.down <= .4:
            self.count = self.count + 1 if self.last_key == name and now - self.last_time <= .4 else 1
            self.last_key, self.last_time = name, now
            if self.count in (2, 3):
                self.choose("DoubleAlt" if self.count == 2 else "TripleAlt")
        self.down = None
        return True

    def mouse(self, _, event):
        if event.button >= 8:
            self.choose("+".join([label for mask, label in MODS if event.state & mask] + ["Button" + str(event.button)]))
            return True
        return False

    def capture(self):
        self.show_all()
        result = self.value if self.run() == Gtk.ResponseType.OK else None
        self.destroy()
        return result


class Application(Gtk.Application):
    def __init__(self):
        super().__init__(application_id="im.rime.LLMTranslator.Panel", flags=Gio.ApplicationFlags.HANDLES_COMMAND_LINE)
        self.window = None

    def do_command_line(self, command_line):
        argv = command_line.get_arguments()
        if self.window is None:
            self.window = EditorWindow(self)
        if len(argv) >= 3 and argv[1] == "panel":
            self.window.open(argv[2])
        else:
            self.window.show_all()
            self.window.present()
            self.window.settings()
            if not self.window.token:
                self.window.close_panel()
        return 0


def run(command="settings", token=None):
    os.umask(0o077)
    GLib.set_prgname("rime-llm-panel")
    if command == "panel" and not token:
        try:
            call_bridge("Open")
            return 0
        except GLib.Error:
            print("请先选择 Rime Translator 并聚焦目标输入框，再使用长文本快捷键。", file=sys.stderr)
            return 1
    # Service start is a local session operation; failure is shown in the panel.
    subprocess.run(["systemctl", "--user", "start", "rime-llm-translator.service", "rime-llm-ai.service"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=False)
    return Application().run(["rime-llm-translator", command] + ([token] if token else []))
