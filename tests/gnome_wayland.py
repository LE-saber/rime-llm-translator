"""Real GNOME 46 nested Wayland regression: original target + floating panel.

Shell unsafe Eval is enabled ONLY in this disposable CI desktop. The shipped
extension never enables or uses Eval. No credentials, model or cloud required.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time

import gi
gi.require_version("Gio", "2.0")
from gi.repository import Gio, GLib

root = Path(__file__).resolve().parents[1]
home = Path.home()
uuid = "rime-llm-translator@le-saber"
ext = home / ".local/share/gnome-shell/extensions" / uuid
ext.mkdir(parents=True)
for name in ("extension.js", "metadata.json"):
    shutil.copyfile(root / "gnome-extension" / name, ext / name)
Gio.Settings.new("org.gnome.shell").set_strv("enabled-extensions", [uuid])
Gio.Settings.new("org.gnome.desktop.input-sources").set_value("sources", GLib.Variant("a(ss)", [("ibus", "rime-llm")]))
Gio.Settings.new("org.gnome.desktop.interface").set_boolean("enable-animations", False)
Gio.Settings.sync()
data = home / ".config/ibus/rime-llm"
(data / "lua").mkdir(parents=True)
for name in ("rime_llm_translator.lua", "rime_llm_ai_hotkey.lua"):
    shutil.copyfile(root / "lua" / name, data / "lua" / name)
(data / "default.custom.yaml").write_text('patch:\n  schema_list:\n    - schema: luna_pinyin\n')

loop = GLib.MainContext.default()
connection = Gio.bus_get_sync(Gio.BusType.SESSION, None)
processes = []


def pump():
    while loop.pending():
        loop.iteration(False)
    time.sleep(.03)


def wait(predicate, label, seconds=30):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        pump()
        try:
            if predicate():
                print("PASS:", label, flush=True)
                return
        except GLib.Error:
            pass
    try:
        print("Desktop diagnostic:", shell("({focus: global.display.focus_window?.get_title(), overview: global.rimeTestMain?.overview.visible, textFocus: Boolean(global.rimeTestMain?.inputMethod.currentFocus), windows: global.get_window_actors().map(a => [a.meta_window.get_title(), a.meta_window.get_gtk_application_id()])})"), flush=True)
        if "gui" in globals():
            print("IBus diagnostic:", gui.call_bridge("Focus"), flush=True)
            if app.window:
                print("Panel diagnostic:", app.window.message.get_text(), flush=True)
    except Exception as exc:
        print("Diagnostic unavailable:", exc, flush=True)
    raise AssertionError(label)


def call(name, path, interface, method, signature="()", args=()):
    return connection.call_sync(name, path, interface, method, GLib.Variant(signature, args),
                                None, Gio.DBusCallFlags.NONE, 2000, None).unpack()


def shell(script):
    ok, result = call("org.gnome.Shell", "/org/gnome/Shell", "org.gnome.Shell", "Eval", "(s)", (script,))
    if not ok:
        raise AssertionError("Shell Eval: " + result)
    return json.loads(result) if result else None


def target_text():
    return call("im.rime.WaylandTestTarget", "/im/rime/WaylandTestTarget",
                "im.rime.WaylandTestTarget", "Text")[0]


try:
    log = (root / "dist/gnome-wayland.log").open("w")
    daemon = subprocess.Popen(["ibus-daemon", "--replace", "--xim", "--panel=disable", "--config=disable"], stdout=log, stderr=log)
    processes.append(daemon)
    nested = subprocess.Popen(["gnome-shell", "--nested", "--wayland", "--unsafe-mode"], stdout=log, stderr=log)
    processes.append(nested)
    wait(lambda: call("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus",
                     "NameHasOwner", "(s)", ("im.rime.LLMTranslator.Shell",))[0], "GNOME 46 extension loaded", 60)
    shell("import('resource:///org/gnome/shell/ui/main.js').then(m => global.rimeTestMain = m); import('gi://GLib').then(m => global.rimeTestGLib = m.default); true")
    wait(lambda: shell("Boolean(global.rimeTestMain && global.rimeTestGLib)"), "test-only Shell inspection ready")
    display = next(p.name for p in Path(os.environ["XDG_RUNTIME_DIR"]).glob("wayland-*") if not p.name.endswith(".lock"))
    shell("global.rimeTestMain.overview.hide(); true")
    target_env = dict(os.environ, GDK_BACKEND="wayland", GTK_IM_MODULE="wayland", WAYLAND_DISPLAY=display)
    target = subprocess.Popen(["/usr/bin/python3", str(root / "tests/wayland_target.py")], env=target_env, stdout=log, stderr=log)
    processes.append(target)
    wait(lambda: shell("global.get_window_actors().some(a => a.meta_window.get_gtk_application_id() === 'im.rime.WaylandTestTarget')"), "native Wayland target mapped")
    shell("global.get_window_actors().find(a => a.meta_window.get_gtk_application_id() === 'im.rime.WaylandTestTarget').meta_window.activate(global.get_current_time()); true")
    wait(lambda: shell("global.display.focus_window?.get_gtk_application_id() === 'im.rime.WaylandTestTarget' && global.rimeTestMain.inputMethod.currentFocus !== null"), "target text field focused")
    # The editor intentionally uses Xwayland utility hints to avoid taskbar and
    # Alt-Tab entries. Get the nested shell's own X server, not outer Xvfb.
    os.environ["DISPLAY"] = shell("global.rimeTestGLib.getenv('DISPLAY')")
    os.environ["WAYLAND_DISPLAY"] = display
    sys.path.insert(0, "/usr/share/rime-llm-translator")
    import rime_gui as gui
    cfg = gui.core.config_default()
    gui.core.save_config(cfg)
    app = gui.Application()
    assert app.register(None)
    wait(lambda: "focused=1 client=gnome-shell" in gui.call_bridge("Focus"), "real shared Wayland IBus context", 45)
    token = gui.call_bridge("Open")
    wait(lambda: app.window is not None and app.window.token == token, "editor opened from target")
    editor = app.window
    assert editor.target_supported and editor.send_button.get_sensitive(), editor.message.get_text()
    # A different session-bus sender cannot use or replace the frontend lease.
    assert call("im.rime.LLMTranslator.Shell", "/im/rime/LLMTranslator/Shell",
                "im.rime.LLMTranslator.Shell", "Begin", "(s)", (token,)) == (False,)
    assert call("im.rime.LLMTranslator.Shell", "/im/rime/LLMTranslator/Shell",
                "im.rime.LLMTranslator.Shell", "Submit", "(ss)", (token, "unauthorized")) == ("cancelled",)
    assert target_text() == ""
    wait(lambda: shell("global.get_window_actors().some(a => a.meta_window.get_title() === 'Rime Translator · 长文本' && a.meta_window.above && a.meta_window.skip_taskbar)"), "floating panel is above and excluded from taskbar")
    assert not editor.get_decorated()
    editor.buffer.set_text("你好，世界")
    if editor.debounce:
        GLib.source_remove(editor.debounce)
        editor.debounce = 0
    # Translation content is supplied deterministically; native model inference
    # and cloud state transitions have their own real IBus/GTK integration test.
    editor.draft.results["mt"] = "Hello, world!"
    editor.send()
    wait(lambda: not editor.queued, "send completes after automatic focus restoration")
    assert target_text() == "Hello, world!", target_text()
    assert gui.call_bridge("State", "(s)", (token,)) == "sent"
    print("PASS: real Wayland target received exactly the translation, once", flush=True)
    # Repeating Restore must not duplicate a completed send.
    gui.call_bridge("Restore", "(s)", (token,))
    for _ in range(10):
        pump()
    assert target_text() == "Hello, world!"
    token = gui.call_bridge("Open")
    wait(lambda: editor.token == token, "session for unrelated-window isolation")
    call("im.rime.WaylandTestTarget", "/im/rime/WaylandTestTarget", "im.rime.WaylandTestTarget", "Other")
    wait(lambda: shell("global.get_window_actors().some(a => a.meta_window.get_title() === 'Unrelated text target')"), "another real input window mapped")
    shell("global.get_window_actors().find(a => a.meta_window.get_title() === 'Unrelated text target').meta_window.activate(global.get_current_time()); true")
    wait(lambda: shell("global.display.focus_window?.get_title() === 'Unrelated text target'"), "unrelated window focused")
    shell("global.get_window_actors().find(a => a.meta_window.get_title() === 'Wayland translation target').meta_window.activate(global.get_current_time()); true")
    wait(lambda: shell("global.display.focus_window?.get_title() === 'Wayland translation target'"), "return to old window does not renew lease")
    editor.buffer.set_text("不要误发")
    editor.draft.results["mt"] = "Never redirect"
    editor.send()
    wait(lambda: not editor.queued, "switching windows invalidates send")
    assert target_text() == "Hello, world!"
    assert gui.call_bridge("State", "(s)", (token,)) != "sent"
    print("PASS: unrelated window invalidates lease even with shared IBus ID", flush=True)
    shell("global.get_window_actors().find(a => a.meta_window.get_title() === 'Wayland translation target').meta_window.activate(global.get_current_time()); true")
    wait(lambda: "focused=1 client=gnome-shell" in gui.call_bridge("Focus"), "original target focused for closed-window test")
    # Closing the original target invalidates the compositor lease. The draft
    # must be retained and no text may be redirected into the editor/another app.
    token = gui.call_bridge("Open")
    wait(lambda: editor.token == token, "second editing session")
    target.terminate()
    target.wait(timeout=5)
    editor.buffer.set_text("保留草稿")
    editor.draft.results["mt"] = "Never redirect this"
    editor.send()
    wait(lambda: not editor.queued, "closed target cancels submission", 12)
    assert gui.call_bridge("State", "(s)", (token,)) != "sent"
    assert editor.text() == "保留草稿"
    print("PASS: closed Wayland target preserves draft and cancels send", flush=True)
    editor.close_panel()
    app.quit()
finally:
    for process in reversed(processes):
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
    if "log" in globals():
        log.close()
        print((root / "dist/gnome-wayland.log").read_text()[-18000:], flush=True)
