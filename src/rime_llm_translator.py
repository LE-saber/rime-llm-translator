#!/usr/bin/python3
"""Offline translation, explicit AI revision and Ubuntu per-user setup."""
import argparse
import configparser
import getpass
from io import StringIO
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from urllib import request, error
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parent) if
                (Path(__file__).resolve().parent / "rime_mt.py").is_file() else
                "/usr/share/rime-llm-translator")
import rime_mt

APP = "rime-llm-translator"
CONFIG_DIR = Path.home() / ".config" / APP
CACHE_DIR = Path.home() / ".cache" / APP
CONFIG_PATH = CONFIG_DIR / "config.ini"
KEY_PATH = CONFIG_DIR / "api_key"
LATEST_PATH = CACHE_DIR / "latest.req"
MT_RESULTS = CACHE_DIR / "results-mt"
AI_RESULTS = CACHE_DIR / "results-ai"
AI_REQUEST = CACHE_DIR / "ai.req"
DATA_DIR = Path.home() / ".local/share" / APP
VENV_DIR = DATA_DIR / "venv"
HOTKEY_SOURCE = Path("/usr/share/rime-llm-translator/rime_llm_ai_hotkey.lua")
PROCESSOR_KEY = "engine/processors/@before 0"
PROCESSOR_VALUE = "lua_processor@*rime_llm_ai_hotkey"
LUA_SOURCE = Path("/usr/share/rime-llm-translator/rime_llm_translator.lua")
RIME_DIR = Path.home() / ".config/ibus/rime-llm"
DEFAULT_LANGUAGES = "en:English,ja:Japanese"
DEFAULT_AI_HOTKEY = "Control+Shift+Return"
PATCH_KEY = "engine/filters/+"
LEGACY_PATCH_KEY = "engine/filters/@before 0"
PATCH_VALUE = "lua_filter@*rime_llm_translator"

def private_dir(path):
    path.mkdir(parents=True, exist_ok=True, mode=0o700)
    path.chmod(0o700)

def config_default():
    cfg = configparser.ConfigParser(interpolation=None)
    cfg["provider"] = {"base_url": "https://api.deepseek.com",
                       "model": "deepseek-chat"}
    cfg["translation"] = {"enabled": "true", "languages": DEFAULT_LANGUAGES,
                          "min_characters": "1", "debounce_ms": "450",
                          "offline_enabled": "true", "source_language": "auto",
                          "timeout_seconds": "10", "max_tokens": "4096",
                          "offline_timeout_seconds": "15", "offline_idle_seconds": "60",
                          "offline_revision": rime_mt.revision(),
                          "ai_hotkey": DEFAULT_AI_HOTKEY}
    cfg["panel"] = {"open_hotkey": "Alt+space", "send_hotkey": "Control+Return",
                    "preferred_language": "en", "auto_ai_send": "true", "preferences_revision": "12", "theme": "light",
                    "history_enabled": "true", "width": "900", "height": "420",
                    "buttons": "copy,paste,symbols,translate,settings"}
    return cfg

def load_config():
    cfg = config_default()
    if CONFIG_PATH.exists():
        saved = configparser.ConfigParser(interpolation=None)
        saved.read(CONFIG_PATH, encoding="utf-8")
        cfg.read_dict({section: dict(saved[section]) for section in saved.sections()})
        # preview10/11 wrote false as the default, without recording a user
        # choice. Migrate once; all subsequent explicit choices are preserved.
        if not saved.has_option("panel", "preferences_revision"):
            cfg["panel"]["auto_ai_send"] = "true"
    cfg["translation"]["offline_revision"] = rime_mt.revision()
    return cfg

def save_config(cfg):
    # Live shortcut readers must see either the old or the complete new config.
    contents = StringIO()
    cfg.write(contents)
    atomically_write(CONFIG_PATH, contents.getvalue())


def provider_ready(cfg):
    """Local readiness only; checking configuration must never call the API."""
    try:
        chat_url(cfg["provider"]["base_url"])
        return bool(cfg["provider"]["model"].strip() and KEY_PATH.read_text(encoding="utf-8").strip())
    except (OSError, ValueError):
        return False


def auto_ai_enabled(cfg):
    return cfg.getboolean("panel", "auto_ai_send") and provider_ready(cfg)

def parse_languages(raw):
    result = {}
    for item in raw.split(","):
        item = item.strip()
        match = re.fullmatch(r"([a-z]{2,3}(?:-[a-z]{2,4})?):([A-Za-z][A-Za-z -]{1,39})", item)
        if not match:
            raise ValueError("Invalid language. Use en:English,ja:Japanese")
        code, label = match.groups()
        if code in result:
            raise ValueError("Duplicate language: " + code)
        result[code] = label.strip()
    if not 1 <= len(result) <= 6:
        raise ValueError("Configure 1-6 target languages")
    return result

def normalize_hotkey(raw):
    if raw.strip().lower() in ("doublealt", "triplealt"):
        return "DoubleAlt" if raw.strip().lower() == "doublealt" else "TripleAlt"
    if re.fullmatch(r"(?:(?:Control|Alt|Shift|Super)\+)*Button(?:8|9)", raw.strip()):
        return raw.strip()
    parts = [part.strip() for part in raw.split("+")]
    aliases = {"ctrl": "Control", "control": "Control", "shift": "Shift",
               "alt": "Alt", "super": "Super"}
    modifiers = [aliases.get(part.lower()) for part in parts[:-1]]
    if (not modifiers or None in modifiers or len(set(modifiers)) != len(modifiers)
            or not set(modifiers).intersection({"Control", "Alt", "Super"})):
        raise ValueError("Use DoubleAlt or a combination with Control, Alt or Super; e.g. Control+Alt+j")
    key = parts[-1].lower()
    if key in ("enter", "return"):
        key = "Return"
    elif re.fullmatch(r"f(?:[1-9]|1[0-2])", key):
        key = key.upper()
    elif not (re.fullmatch(r"[a-z0-9]", key) or key == "space"):
        raise ValueError("AI shortcut key must be a letter, digit, F1-F12, Return or space")
    return "+".join([m for m in ("Control", "Alt", "Shift", "Super") if m in modifiers] + [key])


def hotkey(binding=None):
    cfg = load_config()
    value = normalize_hotkey(binding if binding is not None else cfg["translation"]["ai_hotkey"])
    if binding is not None:
        if os.geteuid() == 0:
            raise RuntimeError("Run hotkey as your normal Ubuntu user, without sudo")
        cfg["translation"]["ai_hotkey"] = value
        from rime_long_text import validate_shortcuts
        validate_shortcuts({"ai": value, "open": cfg["panel"]["open_hotkey"],
                            "send": cfg["panel"]["send_hotkey"]})
        save_config(cfg)
    print("AI shortcut:", value, "(panel only)" if "Button" in value else "")
    if binding is not None:
        print("Effective immediately with the current frontend and Lua plugin loaded; no service restart needed.")
        print("After upgrading: run sync and log out/in once to load the new frontend and plugin.")


def chat_url(base):
    base = base.rstrip("/")
    parsed = urlparse(base)
    if parsed.scheme != "https" and not (parsed.scheme == "http" and
       parsed.hostname in ("127.0.0.1", "localhost", "::1")):
        raise ValueError("API URL must be HTTPS (HTTP only permitted on localhost)")
    if not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("Invalid API URL")
    if base.endswith("/chat/completions"):
        return base
    return base + "/chat/completions"

def parse_answer(raw, codes):
    raw = raw.strip()
    if raw.startswith("```"):
        raw = re.sub(r"^```(?:json)?\s*|\s*```$", "", raw).strip()
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        left, right = raw.find("{"), raw.rfind("}")
        if left < 0 or right <= left:
            raise ValueError("Model did not return a JSON object")
        parsed = json.loads(raw[left:right+1])
    if not isinstance(parsed, dict):
        raise ValueError("Model output is not an object")
    result = {}
    for lang in codes:
        text = parsed.get(lang)
        if isinstance(text, str):
            text = text.strip()
            if text and len(text) <= 3000:
                result[lang] = text.replace("\r", " ").replace("\n", " ")
    if not result:
        raise ValueError("Model returned no requested languages")
    return result

def translate(text, cfg, api_key, opener=None, drafts=None):
    langs = parse_languages(cfg["translation"]["languages"])
    url = chat_url(cfg["provider"]["base_url"])
    model = cfg["provider"]["model"].strip()
    if not model:
        raise ValueError("Model identifier is empty")
    instruction = (
        "You are a careful human-quality translation reviser. Translate the Chinese text "
        "into these languages: " +
        ", ".join("%s (%s)" % (code, label) for code,label in langs.items()) +
        '. Return ONLY a compact JSON object mapping each language code to its '
        'translated string. Correct errors in the optional offline MT drafts if supplied; '
        'preserve meaning and register; do not add explanations.'
    )
    body = json.dumps({
        "model": model,
        "messages": [{"role": "system", "content": instruction},
                     {"role": "user", "content": json.dumps(
                         {"source": text, "offline_mt_drafts": drafts or {}},
                         ensure_ascii=False)}],
        "temperature": 0.2,
        "max_tokens": cfg.getint("translation", "max_tokens", fallback=4096),
        "stream": False
    }, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json", "User-Agent": APP + "/0.1"}
    if api_key:
        headers["Authorization"] = "Bearer " + api_key
    req = request.Request(url, data=body, headers=headers, method="POST")
    timeout = max(2, min(cfg.getfloat("translation", "timeout_seconds", fallback=10), 60))
    send = opener or request.urlopen
    try:
        with send(req, timeout=timeout) as response:
            payload = json.loads(response.read(1024 * 1024).decode("utf-8"))
    except error.HTTPError as exc:
        raise RuntimeError("API HTTP error %s" % exc.code) from exc
    choices = payload.get("choices") or []
    if not choices or not isinstance(choices[0], dict):
        raise ValueError("Missing API choices")
    content = choices[0].get("message", {}).get("content")
    if choices[0].get("finish_reason") == "length":
        raise ValueError("Model output exceeded token budget; translation was not sent")
    if not isinstance(content, str):
        raise ValueError("Missing API message content")
    return parse_answer(content, langs)

def atomically_write(path, contents):
    private_dir(path.parent)
    temp = path.with_name(path.name + ".tmp." + str(os.getpid()))
    with temp.open("w", encoding="utf-8") as fp:
        fp.write(contents)
    temp.chmod(0o600)
    os.replace(temp, path)

def decode_request(raw):
    rows = raw.splitlines()
    if len(rows) != 2 or not re.fullmatch(r"[0-9a-f]{16}", rows[0]):
        raise ValueError("Bad request identifier")
    if not re.fullmatch(r"[0-9a-f]{2,2400}", rows[1]) or len(rows[1]) % 2:
        raise ValueError("Bad request payload")
    text = bytes.fromhex(rows[1]).decode("utf-8")
    if not text.strip():
        raise ValueError("Empty text")
    return rows[0], text

def encode_results(translations):
    return "".join(lang + "\t" + value.encode("utf-8").hex() + "\n"
                   for lang,value in translations.items())

def read_results(path):
    result = {}
    if not path.exists():
        return result
    for line in path.read_text(encoding="utf-8").splitlines():
        fields = line.split("\t", 1)
        if len(fields) == 2:
            try:
                result[fields[0]] = bytes.fromhex(fields[1]).decode("utf-8")
            except (ValueError, UnicodeDecodeError):
                continue
    return {code: text for code, text in result.items() if text.strip()}

def trim_cache(keep=350):
    for folder in (MT_RESULTS, AI_RESULTS):
        entries = sorted(folder.glob("*.res"),
                         key=lambda x: x.stat().st_mtime, reverse=True)
        used = 0
        for index, path in enumerate(entries):
            used += path.stat().st_size
            if index >= keep or used > 10 * 1024 * 1024:
                path.unlink(missing_ok=True)

local_translate = rime_mt.local_translate


def install_offline_models():
    rime_mt.check_offline()
    print("Bundled native MT engine and models verified. No pip or downloads required.")


class Worker:
    """One independent queue per process; slow AI never blocks offline MT."""
    def __init__(self, mode):
        self.mode = mode
        self.request = AI_REQUEST if mode == "ai" else LATEST_PATH
        self.results = AI_RESULTS if mode == "ai" else MT_RESULTS
        self.marker = None
        self.done = False
        self.retry_at = 0
        self.failures = 0

    def poll(self):
        try:
            if not self.request.exists():
                return False
            st = self.request.stat()
            marker = (st.st_mtime_ns, st.st_size)
            if marker != self.marker:
                self.marker, self.done = marker, False
                self.retry_at, self.failures = 0, 0
            if self.done or time.monotonic() < self.retry_at:
                return False
            cfg = load_config()
            if not cfg.getboolean("translation", "enabled", fallback=False):
                return False
            if self.mode == "mt":
                if not cfg.getboolean("translation", "offline_enabled", fallback=True):
                    return False
                delay = max(.2, min(cfg.getint("translation", "debounce_ms") / 1000, 3))
                if time.time() - st.st_mtime < delay:
                    return False
            identifier, source = decode_request(self.request.read_text(encoding="utf-8"))
            output = self.results / (identifier + ".res")
            cached = read_results(output)
            languages = parse_languages(cfg["translation"]["languages"])
            missing = {code: name for code, name in languages.items() if code not in cached}
            if not missing:
                self.done = True
                return False
            cfg["translation"]["languages"] = ",".join(code + ":" + name
                                                         for code, name in missing.items())
            if self.mode == "ai":
                key = KEY_PATH.read_text(encoding="utf-8").strip() if KEY_PATH.exists() else ""
                if not key:
                    raise RuntimeError("AI hotkey requested but API key is missing")
                drafts = read_results(MT_RESULTS / (identifier + ".res"))
                translated = translate(source, cfg, key, drafts=drafts)
            else:
                def publish(partial):
                    cached.update(partial)
                    atomically_write(output, encode_results(cached))
                def current():
                    return self.request.read_text(encoding="utf-8").splitlines()[0] == identifier
                translated = local_translate(source, cfg, publish=publish,
                                             current=current, existing=cached)
            cached.update(translated)
            atomically_write(output, encode_results(cached))
            trim_cache()
            if any(code not in cached for code in languages):
                raise RuntimeError("Some target languages are unavailable")
            self.done = True
            self.failures = 0
            return True
        except Exception as exc:
            self.failures += 1
            delay = min(30, 2 ** min(self.failures, 5))
            self.retry_at = time.monotonic() + delay
            # Never log input, drafts, provider response bodies or API secrets.
            print(APP + ": " + self.mode + ": " + type(exc).__name__ +
                  "; retry in %ss" % delay, file=sys.stderr, flush=True)
            return False

def serve(mode="mt"):
    import fcntl
    os.umask(0o077)
    for path in (CACHE_DIR, MT_RESULTS, AI_RESULTS):
        private_dir(path)
    with (CACHE_DIR / (mode + ".lock")).open("w") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError(mode + " worker is already running")
        worker = Worker(mode)
        from rime_long_text import PanelWorker
        panel_worker = PanelWorker(mode, sys.modules[__name__])
        print(APP + ": " + mode + " worker running", flush=True)
        try:
            while True:
                if not panel_worker.poll():
                    worker.poll()
                if mode == "mt":
                    idle = max(5, min(load_config().getfloat("translation", "offline_idle_seconds"), 300))
                    rime_mt.NATIVE.reap_idle(idle)
                time.sleep(.15)
        except KeyboardInterrupt:
            return
        finally:
            rime_mt.NATIVE.close()

def _load_user_patch(rime_dir=None):
    import yaml
    directory = rime_dir or RIME_DIR
    private_dir(directory)
    target = directory / "luna_pinyin.custom.yaml"
    content = yaml.safe_load(target.read_text(encoding="utf-8")) if target.exists() else {}
    content = content or {}
    if not isinstance(content, dict):
        raise RuntimeError("Rime custom schema should contain a YAML mapping")
    patch = content.setdefault("patch", {})
    if not isinstance(patch, dict):
        raise RuntimeError("Rime patch section must be a mapping")
    return target, content, patch

def _save_user_patch(target, data):
    import yaml
    if target.exists():
        shutil.copy2(target, target.with_suffix(".yaml.bak"))
    atomically_write(target, yaml.safe_dump(data, allow_unicode=True, sort_keys=False))

def safe_schema_patch():
    """Explicitly append an optional filter; never prepend to native filters."""
    target, content, patch = _load_user_patch()
    legacy = patch.get(LEGACY_PATCH_KEY)
    if legacy and legacy != PATCH_VALUE:
        raise RuntimeError("Conflicting legacy Rime filter patch")
    patch.pop(LEGACY_PATCH_KEY, None)
    appended = patch.get(PATCH_KEY, [])
    if not isinstance(appended, list):
        raise RuntimeError("Existing Rime filter append patch is not a list")
    original = list(appended)
    if PATCH_VALUE not in appended:
        appended.append(PATCH_VALUE)
    patch[PATCH_KEY] = appended
    processor = patch.get(PROCESSOR_KEY)
    if processor and processor != PROCESSOR_VALUE:
        raise RuntimeError("Conflicting Lua processor keybinding")
    patch[PROCESSOR_KEY] = PROCESSOR_VALUE
    if appended != original or legacy == PATCH_VALUE or processor != PROCESSOR_VALUE:
        _save_user_patch(target, content)

def remove_schema_patch(rime_dir=None):
    """Remove only translator-owned schema changes, preserving user settings."""
    directory = rime_dir or RIME_DIR
    target = directory / "luna_pinyin.custom.yaml"
    if not target.exists():
        return
    _, content, patch = _load_user_patch(directory)
    changed = False
    if patch.get(LEGACY_PATCH_KEY) == PATCH_VALUE:
        patch.pop(LEGACY_PATCH_KEY)
        changed = True
    if patch.get(PROCESSOR_KEY) == PROCESSOR_VALUE:
        patch.pop(PROCESSOR_KEY)
        changed = True
    appended = patch.get(PATCH_KEY)
    if isinstance(appended, list) and PATCH_VALUE in appended:
        remaining = [x for x in appended if x != PATCH_VALUE]
        if remaining:
            patch[PATCH_KEY] = remaining
        else:
            patch.pop(PATCH_KEY)
        changed = True
    if changed:
        if not patch:
            content.pop("patch", None)
        _save_user_patch(target, content)

def enable():
    """Opt-in only, after offline integration tests pass."""
    install_user_files()
    safe_schema_patch()
    cfg = load_config()
    cfg["translation"]["enabled"] = "true"
    # The preview1–3 default suppressed one- and two-character translations.
    # Migrate only the old default so upgraded installations handle short text.
    if cfg["translation"].get("min_characters") == "3":
        cfg["translation"]["min_characters"] = "1"
        print("Migrated the old minimum length from 3 to 1 Chinese character.")
    if cfg["translation"].get("max_tokens") == "320":
        cfg["translation"]["max_tokens"] = "4096"
    save_config(cfg)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "enable", "--now",
                    "rime-llm-translator.service"], check=False)
    print("Offline MT and AI shortcut enabled for Rime Translator.")
    print("Log out/in. Add Chinese > Rime Translator in Settings > Keyboard > Input Sources.")
    print("Choose Luna Pinyin with Ctrl+grave if needed. Original Rime is unchanged.")

def disable():
    """Fail-safe revert without uninstalling Rime or deleting API key."""
    remove_schema_patch()
    cfg = load_config()
    cfg["translation"]["enabled"] = "false"
    save_config(cfg)
    print("AI filter removed from user config; user API key retained.")
    print("Switch to the original Rime input source to return to native input.")

def install_user_files():
    if os.geteuid() == 0:
        raise RuntimeError("Run as your normal Ubuntu user, without sudo")
    if not LUA_SOURCE.exists():
        raise RuntimeError("Install the .deb package first")
    private_dir(CACHE_DIR)
    private_dir(MT_RESULTS)
    private_dir(AI_RESULTS)
    private_dir(RIME_DIR / "lua")
    shutil.copy2(LUA_SOURCE, RIME_DIR / "lua/rime_llm_translator.lua")
    if HOTKEY_SOURCE.exists():
        shutil.copy2(HOTKEY_SOURCE, RIME_DIR / "lua/rime_llm_ai_hotkey.lua")
    import rime_shell
    rime_shell.install()
    # Do NOT patch a working input method during setup/sync.

def sync():
    """Noninteractive update: retain provider configuration and API key."""
    install_user_files()
    save_config(load_config())
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "restart",
                    "rime-llm-translator.service"], check=False)
    print("Updated Rime Translator plugin files; did not enable its filter.")
    print("Log out and in to reload Rime, or use its redeploy action.")

def setup(args):
    if os.geteuid() == 0:
        raise RuntimeError("Run setup as your normal Ubuntu user, without sudo")
    if not LUA_SOURCE.exists():
        raise RuntimeError("Install the .deb package first")
    cfg = load_config()
    def ask(label, default):
        value = input("%s [%s]: " % (label, default)).strip()
        return value or default
    print("Rime LLM Translator — first-time setup")
    cfg["provider"]["base_url"] = ask("OpenAI-compatible API base URL", cfg["provider"]["base_url"])
    chat_url(cfg["provider"]["base_url"])
    cfg["provider"]["model"] = ask("Model", cfg["provider"]["model"])
    cfg["translation"]["languages"] = ask("Target languages", cfg["translation"]["languages"])
    parse_languages(cfg["translation"]["languages"])
    cfg["translation"]["ai_hotkey"] = normalize_hotkey(ask("AI shortcut (e.g. DoubleAlt or Control+Alt+j)",
                                                         cfg["translation"]["ai_hotkey"]))
    save_config(cfg)
    key = getpass.getpass("API key (blank = keep current): ").strip()
    if key:
        atomically_write(KEY_PATH, key + "\n")
    install_user_files()
    try:
        subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
        subprocess.run(["systemctl", "--user", "enable", "--now",
                        "rime-llm-translator.service"], check=True)
        subprocess.run(["systemctl", "--user", "restart",
                        "rime-llm-translator.service"], check=True)
        print("Background service enabled.")
    except (OSError, subprocess.CalledProcessError):
        print("Could not enable user service. Run: systemctl --user enable --now rime-llm-translator.service")
    print("Setup complete. Enable the separate input source: rime-llm-translator enable")
    print("Rime Translator refreshes translation candidates automatically while focused.")

def doctor():
    import rime_shell
    print("GNOME floating-panel bridge:", rime_shell.status())
    print("Configuration:", CONFIG_PATH, CONFIG_PATH.is_file())
    print("API key:", "configured" if KEY_PATH.is_file() else "missing")
    print("Lua plugin:", (RIME_DIR / "lua/rime_llm_translator.lua").is_file())
    print("AI shortcut Lua:", (RIME_DIR / "lua/rime_llm_ai_hotkey.lua").is_file())
    print("Offline backend: Bergamot native INT8; revision:", rime_mt.revision())
    print("Legacy Argos venv remains:", VENV_DIR.exists())
    try:
        rime_mt.check_offline()
        print("Bundled models: checksums verified")
    except (RuntimeError, OSError, ValueError) as exc:
        print("Bundled models: unavailable:", exc)
    print("Rime Translator data:", RIME_DIR)
    print("IBus frontend:", Path("/usr/libexec/rime-llm-translator/ibus-engine-rime-llm").is_file())
    try:
        _, _, patch = _load_user_patch()
        print("Rime filter enabled:", PATCH_VALUE in patch.get(PATCH_KEY, []) or patch.get(LEGACY_PATCH_KEY) == PATCH_VALUE)
    except (ImportError, ValueError, RuntimeError, OSError) as exc:
        print("Rime filter status: unavailable:", exc)
    print("Worker path:", LUA_SOURCE.exists())
    if CONFIG_PATH.exists():
        cfg = load_config()
        print("Provider:", cfg["provider"]["base_url"], cfg["provider"]["model"])
        print("Languages:", cfg["translation"]["languages"])
        try:
            print("AI shortcut:", normalize_hotkey(cfg["translation"]["ai_hotkey"]))
        except ValueError as exc:
            print("AI shortcut: invalid:", exc)
    subprocess.run(["systemctl", "--user", "is-active", "rime-llm-translator.service", "rime-llm-ai.service"],
                   check=False)

def main():
    ap = argparse.ArgumentParser(description="Rime offline MT and hotkey-only AI")
    ap.add_argument("command", choices=["setup", "sync", "enable", "disable", "serve", "serve-ai",
                                        "doctor", "install-offline", "install-runtime", "repair-offline",
                                        "download-models", "restore-native", "cleanup-legacy", "hotkey",
                                        "panel", "settings"],
                    help="Action")
    ap.add_argument("binding", nargs="?", help="AI shortcut for hotkey, e.g. Control+Alt+j")
    ap.add_argument("--apply", action="store_true", help="Delete the paths shown by cleanup-legacy")
    ap.add_argument("--pip-cache", action="store_true", help="Include shared ~/.cache/pip downloads")
    ap.add_argument("--argos-models", action="store_true", help="Include shared old Chinese/English/Japanese Argos models")
    args = ap.parse_args()
    if args.binding is not None and args.command not in ("hotkey", "panel"):
        ap.error("A shortcut binding requires the hotkey command")
    if args.command != "cleanup-legacy" and (args.apply or args.pip_cache or args.argos_models):
        ap.error("Cleanup flags require cleanup-legacy")
    os.umask(0o077)
    try:
        if args.command in ("panel", "settings"):
            from rime_gui import run
            return run(args.command, args.binding)
        elif args.command == "setup":
            setup(args)
        elif args.command == "hotkey":
            hotkey(args.binding)
        elif args.command == "sync":
            sync()
        elif args.command == "enable":
            enable()
        elif args.command == "disable":
            disable()
        elif args.command == "serve":
            serve()
        elif args.command == "serve-ai":
            serve("ai")
        elif args.command in ("install-offline", "install-runtime", "download-models", "repair-offline"):
            install_offline_models()
            print("For old installation remnants, run cleanup-legacy to preview cleanup.")
        elif args.command == "cleanup-legacy":
            rime_mt.cleanup_legacy(args.apply, args.pip_cache, args.argos_models)
        elif args.command == "restore-native":
            remove_schema_patch(Path.home() / ".config/ibus/rime")
            print("Removed only preview1-4 translator patches from original Rime.")
            print("Redeploy original Rime and log out/in. API key and dictionaries retained.")
        else:
            doctor()
    except subprocess.CalledProcessError as exc:
        print("System command failed (exit %s). Check the error above; verify your user service "
              "session and package installation." % exc.returncode,
              file=sys.stderr)
        return 1
    except (KeyboardInterrupt, EOFError):
        print("Cancelled.", file=sys.stderr)
        return 130
    except (ValueError, RuntimeError, OSError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
