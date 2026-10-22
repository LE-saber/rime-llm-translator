#!/usr/bin/python3
"""Packaged GTK + real IBus/Rime + shared native worker + local mock cloud.

No credentials or external cloud requests. Run in disposable HOME/dbus/Xvfb.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, "/usr/share/rime-llm-translator")
import rime_gui as gui
from gi.repository import GLib, IBus, Gdk, Gtk

home = Path.home()
core = gui.core
for folder in (core.CONFIG_DIR, core.CACHE_DIR, core.MT_RESULTS, core.AI_RESULTS, core.RIME_DIR / "lua"):
    core.private_dir(folder)
for name in ("rime_llm_translator.lua", "rime_llm_ai_hotkey.lua"):
    shutil.copyfile("/usr/share/rime-llm-translator/" + name, core.RIME_DIR / "lua" / name)
(core.RIME_DIR / "default.custom.yaml").write_text('patch:\n  schema_list:\n    - schema: luna_pinyin\n')
(core.RIME_DIR / "luna_pinyin.custom.yaml").write_text(
    'patch:\n  "switches/@0/reset": 0\n  "engine/filters/+":\n'
    '    - "lua_filter@*rime_llm_translator"\n'
    '  "engine/processors/@before 0": "lua_processor@*rime_llm_ai_hotkey"\n')

cloud = {"calls": 0, "delay": 0, "fail": False}
class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        request = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        cloud["calls"] += 1
        time.sleep(cloud["delay"])
        if cloud["fail"]:
            self.send_error(503)
            return
        source = json.loads(request["messages"][1]["content"])["source"]
        body = json.dumps({"choices": [{"finish_reason": "stop", "message": {
            "content": json.dumps({"en": "AI: " + source, "ja": "AI JA: " + source})}}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)
    def log_message(self, *_):
        pass

server = HTTPServer(("127.0.0.1", 0), Handler)
threading.Thread(target=server.serve_forever, daemon=True).start()
cfg = core.config_default()
cfg["provider"]["base_url"] = "http://127.0.0.1:" + str(server.server_port)
cfg["translation"]["ai_hotkey"] = "DoubleAlt"
cfg["panel"]["open_hotkey"] = "Control+Alt+F9"
core.save_config(cfg)
core.atomically_write(core.KEY_PATH, "local-test-only")
os.environ["IBUS_ADDRESS"] = "unix:path=" + str(home / "ibus.sock")
os.environ["RIME_LLM_TEST_DIAGNOSTICS"] = "1"
GLib.set_prgname("rime-llm-panel")
daemon = subprocess.Popen(["ibus-daemon", "--replace", "--panel=disable", "--config=disable",
                           "--address=" + os.environ["IBUS_ADDRESS"]])
workers = []
loop = GLib.MainContext.default()

def pump(seconds=.25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        while loop.pending():
            loop.iteration(False)
        time.sleep(.01)

def wait(predicate, label, seconds=25):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        pump(.03)
        if predicate():
            print("PASS:", label, flush=True)
            return
    raise AssertionError(label)

def focus(context):
    context.focus_in()
    context.set_engine("rime-llm")
    wait(lambda: context.get_engine() and context.get_engine().get_name() == "rime-llm", "focused context")
    pump()

def buffer_text(widget):
    buffer = widget.get_buffer()
    return buffer.get_text(buffer.get_start_iter(), buffer.get_end_iter(), True)

try:
    IBus.init()
    bus = IBus.Bus.new()
    wait(bus.is_connected, "IBus")
    app = gui.Application()
    assert app.register(None)
    target = bus.create_input_context("rime-panel-target-test")
    target.set_capabilities(1 | 2 | 4 | 8)
    target_commits = []
    target.connect("commit-text", lambda _, text: target_commits.append(text.get_text()))
    focus(target)
    for key in "xiexie":
        target.process_key_event(ord(key), 0, 0)
    print("Bridge before open:", gui.call_bridge("Focus"), flush=True)
    assert target.process_key_event(0xffc6, 0, 12), "open chord not handled"
    wait(lambda: app.window is not None and app.window.token, "native GTK editor opened by IBus chord")
    editor = app.window
    assert editor.text().startswith("謝謝"), editor.text()
    assert target_commits == [], "Chinese source leaked into target"
    print("PASS: Traditional Rime composition transferred privately into editable draft", flush=True)
    editor_context = bus.create_input_context("gtk3-im:rime-llm-panel")
    editor_context.set_capabilities(1 | 2 | 4 | 8)
    editor_context.connect("commit-text", lambda _, text: editor.buffer.insert_at_cursor(text.get_text()))
    target.focus_out()
    focus(editor_context)
    for key in "nihao":
        editor_context.process_key_event(ord(key), 0, 0)
    editor_context.process_key_event(32, 0, 0)
    wait(lambda: "你好" in editor.text(), "Rime selections accumulate in editable GTK text buffer")
    assert target_commits == []
    assert not core.AI_REQUEST.exists(), "editor candidate requested AI"
    recorder = gui.Recorder(editor)
    def event(key, state=0):
        return SimpleNamespace(keyval=key, state=state)
    recorder.do_key_press_event(event(Gdk.KEY_Alt_L, 4))
    recorder.do_key_press_event(event(Gdk.KEY_space, 12))
    assert recorder.value == "Control+Alt+space", recorder.value
    for _ in range(2):
        recorder.do_key_press_event(event(Gdk.KEY_Alt_L))
        recorder.do_key_release_event(event(Gdk.KEY_Alt_L, 8))
    assert recorder.value == "DoubleAlt", recorder.value
    recorder.mouse(recorder, SimpleNamespace(button=8, state=4))
    assert recorder.value == "Control+Button8"
    recorder.destroy()
    print("PASS: native keyboard and side-button recording", flush=True)
    workers = [subprocess.Popen(["rime-llm-translator", mode]) for mode in ("serve", "serve-ai")]
    editor.buffer.set_text("你好，谢谢。\n我们明天见。")
    wait(lambda: "mt" in editor.draft.results, "real packaged MT translates multiline draft", 55)
    assert "\n" in editor.draft.results["mt"]
    assert cloud["calls"] == 0, "typing requested cloud"
    screenshot = Gdk.pixbuf_get_from_window(editor.get_window(), 0, 0, *editor.get_size())
    screenshot.savev("dist/native-long-text.png", "png", [], [])
    editor.ai()
    wait(lambda: "ai" in editor.draft.results, "explicit AI uses real HTTP code with local mock")
    calls = cloud["calls"]
    ai_result = editor.draft.results["ai"]
    editor.toggle_theme()
    assert editor.draft.results["ai"] == ai_result and cloud["calls"] == calls
    editor.buffer.insert_at_cursor("这是修改。")
    wait(lambda: "mt" in editor.draft.results, "editing resets to real MT")
    assert cloud["calls"] == calls and "ai" not in editor.draft.results
    print("PASS: no sticky AI after edit; cloud count unchanged", flush=True)
    # Send using matching auto-AI, reusing a request still in flight.
    cloud["delay"] = .3
    editor.cfg["panel"]["auto_ai_send"] = "true"
    editor.ai()
    editor.send()
    wait(lambda: editor.queued, "AI send waits before queuing")
    assert cloud["calls"] == calls + 2  # two paragraphs, no duplicate job
    editor_context.focus_out()
    focus(target)
    wait(lambda: target_commits and not editor.queued, "translation commits only after original target focuses")
    assert target_commits[0].startswith("AI:") and "ai" not in editor.draft.results
    # A different context must cancel and can never receive the pending translation.
    token = gui.call_bridge("Open")
    wait(lambda: editor.token == token and editor.get_visible(), "reopen keeps native draft")
    target.focus_out()
    focus(editor_context)
    editor.cfg["panel"]["auto_ai_send"] = "false"
    editor.buffer.set_text("再见。")
    wait(lambda: "mt" in editor.draft.results, "new source MT")
    editor.send()
    assert editor.queued
    other = bus.create_input_context("other-application")
    other.set_capabilities(1 | 2 | 4 | 8)
    other_commits = []
    other.connect("commit-text", lambda _, text: other_commits.append(text.get_text()))
    editor_context.focus_out()
    focus(other)
    wait(lambda: not editor.queued and editor.get_visible(), "unrelated focus cancels send and preserves editor")
    assert other_commits == [] and len(target_commits) == 1
    # Source edit during AI send cancels the pending submission, including stale HTTP.
    editor.cfg["panel"]["auto_ai_send"] = "true"
    editor.send()
    editor.buffer.set_text("改了，不能发送旧译文。")
    pump(1)
    assert not editor.queued and editor.send_mode is None
    # GUI settings can save safely without replacing a blank API key.
    dialog = gui.Settings(editor)
    dialog.show_all()
    pump()
    screenshot = Gdk.pixbuf_get_from_window(dialog.get_window(), 0, 0, *dialog.get_size())
    screenshot.savev("dist/native-settings.png", "png", [], [])
    GLib.idle_add(lambda: (dialog.response(Gtk.ResponseType.OK), False)[1])
    dialog.run_and_save()
    assert core.KEY_PATH.read_text().strip() == "local-test-only"
    assert core.CONFIG_PATH.stat().st_mode & 0o077 == 0
    if core.load_config()["panel"]["theme"] != "dark":
        editor.toggle_theme()
    pump()
    screenshot = Gdk.pixbuf_get_from_window(editor.get_window(), 0, 0, *editor.get_size())
    screenshot.savev("dist/native-dark.png", "png", [], [])
    editor.remember()
    assert json.loads(gui.DATA_PATH.read_text())["history"]
    assert gui.DATA_PATH.stat().st_mode & 0o077 == 0
    print("PASS: GUI settings, theme, key retention, private history and safe cancellation", flush=True)
    editor.close_panel()
finally:
    for worker in workers:
        worker.terminate()
        worker.wait(timeout=5)
    if "app" in globals():
        app.quit()
    daemon.terminate()
    daemon.wait(timeout=5)
    server.shutdown()
