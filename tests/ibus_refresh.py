#!/usr/bin/python3
"""Real packaged IBus frontend: late MT/AI results must update without input.

Run only in a disposable HOME under dbus-run-session + xvfb-run.
Synthetic cache checks are followed by the real packaged MT worker.
No cloud calls or credentials are used.
"""
import os
from pathlib import Path
import subprocess
import time

import gi
gi.require_version("IBus", "1.0")
from gi.repository import GLib, IBus

home = Path.home()
cache = home / ".cache/rime-llm-translator"
rime = home / ".config/ibus/rime-llm"
config = home / ".config/rime-llm-translator/config.ini"
for folder in (cache / "results-mt", cache / "results-ai", rime / "lua", config.parent):
    folder.mkdir(parents=True, exist_ok=True)
config.write_text("[provider]\nbase_url=https://api.deepseek.com\nmodel=deepseek-chat\n"
                  "[translation]\nenabled=true\nlanguages=en:English,ja:Japanese\n"
                  "min_characters=1\nsource_language=auto\n", encoding="utf-8")
import shutil
for name in ("rime_llm_translator.lua", "rime_llm_ai_hotkey.lua"):
    shutil.copyfile("/usr/share/rime-llm-translator/" + name, rime / "lua" / name)
(rime / "default.custom.yaml").write_text(
    'patch:\n  schema_list:\n    - schema: luna_pinyin\n', encoding="utf-8")
(rime / "luna_pinyin.custom.yaml").write_text(
    'patch:\n  "menu/page_size": 9\n  "switches/@0/reset": 0\n'
    '  "engine/filters/+":\n    - "lua_filter@*rime_llm_translator"\n'
    '  "engine/processors/@before 0": "lua_processor@*rime_llm_ai_hotkey"\n',
    encoding="utf-8")

os.environ["IBUS_ADDRESS"] = "unix:path=" + str(home / "ibus.sock")
daemon = subprocess.Popen(["ibus-daemon", "--replace", "--panel=disable",
                           "--config=disable", "--address=" + os.environ["IBUS_ADDRESS"]])
loop = GLib.MainContext.default()
worker = None

def wait_for(predicate, label, seconds=20):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while loop.pending():
            loop.iteration(False)
        if predicate():
            print("PASS:", label, flush=True)
            return
        time.sleep(.02)
    raise AssertionError(label)

def pump(seconds=.4):
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        while loop.pending():
            loop.iteration(False)
        time.sleep(.02)

def write_result(mode, rid, english):
    target = cache / ("results-" + mode) / (rid + ".res")
    temporary = target.with_suffix(".tmp")
    temporary.write_text("en\t" + english.encode().hex() + "\n" +
                         "ja\t" + "こんにちは".encode().hex() + "\n", encoding="utf-8")
    temporary.replace(target)

try:
    IBus.init()
    bus = IBus.Bus.new()
    wait_for(bus.is_connected, "IBus connection")
    context = bus.create_input_context("rime-llm-package-test")
    context.set_capabilities(1 | 2 | 4 | 8)
    tables, commits, forwarded = [], [], []
    context.connect("update-lookup-table", lambda _, table, visible: tables.append(
        [table.get_candidate(i).get_text() for i in range(table.get_number_of_candidates())]
        if visible else []))
    context.connect("commit-text", lambda _, text: commits.append(text.get_text()))
    context.connect("update-preedit-text", lambda _, text, *args:
                    print("preedit:", text.get_text(), flush=True))
    context.connect("forward-key-event", lambda *args: forwarded.append(args[1:]))
    context.focus_in()
    context.set_engine("rime-llm")
    wait_for(lambda: context.get_engine() and context.get_engine().get_name() == "rime-llm",
             "packaged Rime Translator engine starts")
    for letter in "nihao":
        print("key:", letter, context.process_key_event(ord(letter), 0, 0), flush=True)
    pump()
    print("tables:", tables[-3:], "commits:", commits, "forwarded:", forwarded, flush=True)
    wait_for(lambda: tables and tables[-1] and tables[-1][0].startswith("你好"),
             "native Chinese candidate before any translations")
    assert not (cache / "ai.req").exists(), "normal typing requested AI"
    rid = (cache / "latest.req").read_text().splitlines()[0]
    write_result("mt", rid, "Offline hello")
    wait_for(lambda: tables and any("Offline hello" in c and "MT" in c for c in tables[-1]),
             "late MT cache publishes lookup-table update without another key")
    assert not commits and not forwarded, "refresh committed or forwarded a key"
    # Preserve a native candidate highlighted after the translated alternatives.
    context.process_key_event(0xff54, 0, 0)  # Down, highlight an MT result.
    context.process_key_event(0xff52, 0, 0)  # Up, return to native first candidate.
    assert context.process_key_event(0xff0d, 0, 5), "AI hotkey was not handled"
    wait_for(lambda: (cache / "ai.req").is_file(), "explicit AI request")
    assert (cache / "ai.req").read_text().splitlines()[0] == rid
    write_result("ai", rid, "AI hello")
    wait_for(lambda: tables and any("AI hello" in c and "AI" in c for c in tables[-1]),
             "late AI correction refreshes without another key")
    assert not any("Offline hello" in c for c in tables[-1]), "AI did not supersede MT"
    assert tables[-1][0].startswith("你好")
    assert not commits and not forwarded
    context.process_key_event(32, 0, 0)
    wait_for(lambda: commits == ["你好"], "space still commits original Chinese")
    context.reset()
    pump()
    before = len(commits)
    write_result("mt", rid, "Obsolete result")
    pump()
    assert len(commits) == before and not forwarded
    print("PASS: completed composition is not reopened by stale results", flush=True)
    # Full path: real Chinese composition -> Lua request -> native model worker
    # -> partial cache -> IBus table, with no extra key after typing.
    for letter in "ni":
        context.process_key_event(ord(letter), 0, 0)
    wait_for(lambda: tables and tables[-1] and tables[-1][0].startswith("你"),
             "single-character native candidate before model execution")
    worker = subprocess.Popen(["/usr/bin/rime-llm-translator", "serve"], start_new_session=True)
    wait_for(lambda: tables and any("MT" in c and "EN" in c for c in tables[-1]),
             "real model English reaches IBus without another key", seconds=30)
    wait_for(lambda: tables and any("MT" in c and "JA" in c for c in tables[-1]),
             "real model Japanese reaches IBus without another key", seconds=30)
    assert len(commits) == before and not forwarded
    # Ordinary MT must not generate another AI request.
    assert (cache / "ai.req").read_text().splitlines()[0] == rid
    context.reset()
finally:
    if worker:
        import signal
        try:
            os.killpg(worker.pid, signal.SIGTERM)
            worker.wait(timeout=5)
        except ProcessLookupError:
            pass
        except subprocess.TimeoutExpired:
            os.killpg(worker.pid, signal.SIGKILL)
            worker.wait()
    for log in Path("/tmp").glob("rime.ibus.llm.*"):
        if log.is_file() and log.suffix in (".INFO", ".WARNING", ".ERROR"):
            print(log.name, log.read_text(errors="replace")[-10000:], flush=True)
    daemon.terminate()
    try:
        daemon.wait(timeout=5)
    except subprocess.TimeoutExpired:
        daemon.kill()
