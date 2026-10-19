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
subprocess.run(["rime-llm-translator", "hotkey", "Control+Shift+Return"], check=True)
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
    # Change the binding through the packaged CLI without restarting the engine.
    subprocess.run(["rime-llm-translator", "hotkey", "Control+Alt+j"], check=True)
    context.process_key_event(0xff0d, 0, 5)  # Old Control+Shift+Return.
    context.process_key_event(ord("j"), 0, 8)  # Missing Control.
    context.process_key_event(ord("J"), 0, 13)  # Extra Shift.
    context.process_key_event(ord("j"), 0, 12 | (1 << 30))  # Key release.
    assert not (cache / "ai.req").exists(), "old or nonmatching shortcut dispatched AI"
    assert context.process_key_event(ord("j"), 0, 12 | 2), "custom AI hotkey with CapsLock was not handled"
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
    # Traditional Chinese remains intact; shifted letter keysyms also match.
    for letter in "xiexie":
        context.process_key_event(ord(letter), 0, 0)
    wait_for(lambda: tables and tables[-1] and tables[-1][0].startswith("謝謝"),
             "Traditional Chinese still works after changing the shortcut")
    (cache / "ai.req").unlink()
    config.write_text(config.read_text().replace("ai_hotkey = Control+Alt+j", "ai_hotkey = invalid"))
    context.process_key_event(ord("j"), 0, 12)
    assert not (cache / "ai.req").exists(), "invalid config dispatched AI"
    subprocess.run(["rime-llm-translator", "hotkey", "Control+Shift+j"], check=True)
    assert context.process_key_event(ord("J"), 0, 5), "shifted letter shortcut was not handled"
    wait_for(lambda: (cache / "ai.req").is_file(), "new shortcut dispatches for Traditional Chinese")
    request_text = bytes.fromhex((cache / "ai.req").read_text().splitlines()[1]).decode()
    assert request_text.startswith("謝謝"), "AI did not retain Traditional Chinese source"
    assert len(commits) == before and not forwarded
    print("PASS: live shortcut changes, exact modifiers, invalid config and Traditional Chinese", flush=True)
    # Double Alt is a clean press/release pair twice, measured by the frontend's
    # monotonic clock. Delays below deliberately pump GLib rather than busy-wait.
    (cache / "ai.req").unlink()
    subprocess.run(["rime-llm-translator", "hotkey", "DoubleAlt"], check=True)
    def alt_tap(code=0xffe9):
        context.process_key_event(code, 0, 0)
        return context.process_key_event(code, 0, 8 | (1 << 30))
    def no_double_request(label):
        assert not (cache / "ai.req").exists(), label
        assert len(commits) == before and not forwarded, label + " changed input"
        pump(.45)
    alt_tap()
    no_double_request("single Alt must not request AI")
    alt_tap()
    no_double_request("two taps more than 400 ms apart must not request AI")
    context.process_key_event(0xffe9, 0, 0)
    pump(.45)
    context.process_key_event(0xffe9, 0, 8 | (1 << 30))
    alt_tap()
    no_double_request("a held Alt followed by one tap must not request AI")
    context.process_key_event(0xffe9, 0, 0)
    context.process_key_event(0xffe9, 0, 8)  # Repeated press before release.
    context.process_key_event(0xffe9, 0, 8 | (1 << 30))
    alt_tap()
    no_double_request("Alt autorepeat must not count as a tap")
    alt_tap()
    context.process_key_event(0xffe9, 0, 0)
    context.process_key_event(ord("j"), 0, 8)
    context.process_key_event(0xffe9, 0, 8 | (1 << 30))
    alt_tap()
    no_double_request("Alt+another key must cancel the tap sequence")
    alt_tap()
    alt_tap(0xffea)
    no_double_request("mixing left and right Alt must not count as double Alt")
    alt_tap()
    context.focus_out()
    pump(.05)
    context.focus_in()
    pump(.05)
    alt_tap()
    no_double_request("changing application focus must cancel the tap sequence")
    alt_tap()
    context.reset()
    for letter in "xiexie":
        context.process_key_event(ord(letter), 0, 0)
    alt_tap()
    no_double_request("a new composition must not inherit the previous Alt tap")
    alt_tap()
    assert alt_tap(), "double Alt was not handled"
    wait_for(lambda: (cache / "ai.req").is_file(), "double Alt explicitly requests AI")
    source = bytes.fromhex((cache / "ai.req").read_text().splitlines()[1]).decode()
    assert source.startswith("謝謝"), "double Alt changed the Traditional Chinese source"
    (cache / "ai.req").unlink()
    alt_tap()
    assert not (cache / "ai.req").exists(), "third tap must not trigger a second request"
    assert len(commits) == before and not forwarded
    print("PASS: double Alt, timeout, held/repeated keys, interrupted taps and focus/reset safety", flush=True)
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
