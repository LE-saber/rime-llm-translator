#!/usr/bin/python3
"""User-scoped OpenAI-compatible translation worker and Ubuntu installer.

No non-standard Python runtime modules. Optional PyYAML from python3-yaml is used
only for non-destructive Rime schema patching during setup.
"""
import argparse
import configparser
import getpass
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

APP = "rime-llm-translator"
CONFIG_DIR = Path.home() / ".config" / APP
CACHE_DIR = Path.home() / ".cache" / APP
CONFIG_PATH = CONFIG_DIR / "config.ini"
KEY_PATH = CONFIG_DIR / "api_key"
LATEST_PATH = CACHE_DIR / "latest.req"
RESULT_DIR = CACHE_DIR / "results"
MT_RESULTS = CACHE_DIR / "results-mt"
AI_RESULTS = CACHE_DIR / "results-ai"
AI_REQUEST = CACHE_DIR / "ai.req"
VENV_DIR = Path.home() / ".local/share/rime-llm-translator/venv"
VENV_PYTHON = VENV_DIR / "bin/python"
HOTKEY_SOURCE = Path("/usr/share/rime-llm-translator/rime_llm_ai_hotkey.lua")
PROCESSOR_KEY = "engine/processors/@before 0"
PROCESSOR_VALUE = "lua_processor@*rime_llm_ai_hotkey"
LUA_SOURCE = Path("/usr/share/rime-llm-translator/rime_llm_translator.lua")
RIME_DIR = Path.home() / ".config/ibus/rime"
DEFAULT_LANGUAGES = "en:English,ja:Japanese"
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
                          "timeout_seconds": "10", "max_tokens": "320"}
    return cfg

def load_config():
    cfg = config_default()
    if CONFIG_PATH.exists():
        cfg.read(CONFIG_PATH, encoding="utf-8")
    return cfg

def save_config(cfg):
    private_dir(CONFIG_DIR)
    with CONFIG_PATH.open("w", encoding="utf-8") as fp:
        cfg.write(fp)
    CONFIG_PATH.chmod(0o600)

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
        "max_tokens": cfg.getint("translation", "max_tokens", fallback=320),
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

def trim_cache(keep=350):
    entries = sorted(RESULT_DIR.glob("*.res"), key=lambda x: x.stat().st_mtime, reverse=True)
    for path in entries[keep:]:
        path.unlink(missing_ok=True)

def local_translate(text, cfg):
    """Offline Argos packages are loaded by the persistent user worker."""
    from argostranslate import translate as argos
    src = cfg.get("translation", "source_language", fallback="auto")
    if src == "auto":
        # Chinese traditional and simplified share many glyphs; users can
        # override auto explicitly to zh or zt for optimal accuracy.
        traditional = "體臺萬與為學門時後說會來國龍這嗎個們電車開"
        src = "zt" if any(ch in text for ch in traditional) else "zh"
    if src not in ("zh", "zt"):
        raise ValueError("Source language must be auto, zh or zt")
    codes = parse_languages(cfg["translation"]["languages"])
    result = {}
    for code in codes:
        value = argos.translate(text, src, code)
        if value and value.strip():
            result[code] = value.strip().replace("\r", " ").replace("\n", " ")
    if not result:
        raise RuntimeError("No offline Argos language models available")
    return result

def install_offline_models():
    """One-time internet installation. Translation itself remains offline."""
    if os.geteuid() == 0:
        raise RuntimeError("Run install-offline as your normal Ubuntu user")
    if not VENV_PYTHON.is_file():
        subprocess.run([sys.executable, "-m", "venv", str(VENV_DIR)], check=True)
    subprocess.run([str(VENV_PYTHON), "-m", "pip", "install",
                    "argostranslate>=1.9,<2"], check=True)
    subprocess.run([str(VENV_PYTHON), str(Path(__file__)), "download-models"],
                   check=True)
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
    subprocess.run(["systemctl", "--user", "restart",
                    "rime-llm-translator.service"], check=False)
    print("Offline Argos models installed. Disconnect network to test.")

def download_models():
    from argostranslate import package
    package.update_package_index()
    candidates = package.get_available_packages()
    for src, dst in (("zh", "en"), ("zt", "en"), ("en", "ja")):
        found = next((p for p in candidates if p.from_code == src and
                      p.to_code == dst), None)
        if found is None:
            raise RuntimeError("Missing Argos model: %s -> %s" % (src, dst))
        print("Installing offline language model:", src, "->", dst, flush=True)
        package.install_from_path(found.download())

def serve():
    # Ubuntu Python 3.12 forbids system-wide pip installs; use a private venv.
    # The service is launched via /usr/bin/python3 and re-execs into that venv.
    if VENV_PYTHON.is_file() and Path(sys.executable) != VENV_PYTHON:
        os.execv(str(VENV_PYTHON), [str(VENV_PYTHON), str(Path(__file__)), "serve"])
    os.umask(0o077)
    for path in (CACHE_DIR, MT_RESULTS, AI_RESULTS):
        private_dir(path)
    last = {"ai": None, "mt": None}
    print(APP + ": offline MT worker running; AI is hotkey-only", flush=True)
    while True:
        had_work = False
        for mode, req_path, dest_dir in (
            ("ai", AI_REQUEST, AI_RESULTS),
            ("mt", LATEST_PATH, MT_RESULTS)
        ):
            try:
                if not req_path.exists():
                    continue
                st = req_path.stat()
                cfg = load_config()
                if not cfg.getboolean("translation", "enabled", fallback=False):
                    continue
                if mode == "mt":
                    if not cfg.getboolean("translation", "offline_enabled", fallback=True):
                        continue
                    delay = max(.2, min(cfg.getint("translation", "debounce_ms",
                                                    fallback=450)/1000, 3))
                    if time.time() - st.st_mtime < delay:
                        continue
                marker = (st.st_mtime_ns, st.st_size)
                if marker == last[mode]:
                    continue
                last[mode] = marker
                identifier, source = decode_request(
                    req_path.read_text(encoding="utf-8"))
                output = dest_dir / (identifier + ".res")
                if output.exists():
                    continue
                if mode == "ai":
                    key = KEY_PATH.read_text(encoding="utf-8").strip() if KEY_PATH.exists() else ""
                    if not key:
                        raise RuntimeError("AI hotkey requested but API key is missing")
                    mt_draft = MT_RESULTS / (identifier + ".res")
                    drafts = {}
                    if mt_draft.exists():
                        for line in mt_draft.read_text(encoding="utf-8").splitlines():
                            fields = line.split(None, 1)
                            if len(fields) == 2 and re.fullmatch(r"[0-9a-f]+", fields[1]):
                                try:
                                    drafts[fields[0]] = bytes.fromhex(fields[1]).decode("utf-8")
                                except UnicodeDecodeError:
                                    pass
                    translations = translate(source, cfg, key, drafts=drafts)
                else:
                    translations = local_translate(source, cfg)
                atomically_write(output, encode_results(translations))
                had_work = True
            except KeyboardInterrupt:
                return
            except Exception as exc:
                # Avoid logging user text or secrets from translation requests.
                print(APP + ": " + mode + ": " + type(exc).__name__,
                      file=sys.stderr, flush=True)
        if not had_work:
            time.sleep(.15)

def _load_user_patch():
    import yaml
    private_dir(RIME_DIR)
    target = RIME_DIR / "luna_pinyin.custom.yaml"
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

def remove_schema_patch():
    """Remove only translator-owned schema changes, preserving user settings."""
    target = RIME_DIR / "luna_pinyin.custom.yaml"
    if not target.exists():
        return
    _, content, patch = _load_user_patch()
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
    save_config(cfg)
    print("Offline MT filter + Ctrl+Shift+Return AI hotkey enabled.")
    print("Redeploy Rime and log out/in for changes to take effect.")

def disable():
    """Fail-safe revert without uninstalling Rime or deleting API key."""
    remove_schema_patch()
    cfg = load_config()
    cfg["translation"]["enabled"] = "false"
    save_config(cfg)
    print("AI filter removed from user config; user API key retained.")
    print("Redeploy Rime and log out/in to clear compiled Rime schema.")

def install_user_files():
    if os.geteuid() == 0:
        raise RuntimeError("Run as your normal Ubuntu user, without sudo")
    if not LUA_SOURCE.exists():
        raise RuntimeError("Install the .deb package first")
    private_dir(CACHE_DIR)
    private_dir(RESULT_DIR)
    private_dir(RIME_DIR / "lua")
    shutil.copy2(LUA_SOURCE, RIME_DIR / "lua/rime_llm_translator.lua")
    if HOTKEY_SOURCE.exists():
        shutil.copy2(HOTKEY_SOURCE, RIME_DIR / "lua/rime_llm_ai_hotkey.lua")
    # Do NOT patch a working input method during setup/sync.

def sync():
    """Noninteractive update: retain provider configuration and API key."""
    install_user_files()
    subprocess.run(["systemctl", "--user", "restart",
                    "rime-llm-translator.service"], check=False)
    print("Updated plugin files; did not enable the Rime filter.")
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
    print("Setup complete. Rime is unchanged until you run: rime-llm-translator enable")
    print("Translation candidates appear after the asynchronous reply and next menu refresh.")

def doctor():
    print("Configuration:", CONFIG_PATH, CONFIG_PATH.is_file())
    print("API key:", "configured" if KEY_PATH.is_file() else "missing")
    print("Lua plugin:", (RIME_DIR / "lua/rime_llm_translator.lua").is_file())
    print("AI shortcut Lua:", (RIME_DIR / "lua/rime_llm_ai_hotkey.lua").is_file())
    print("Argos offline venv:", VENV_PYTHON.is_file())
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
    subprocess.run(["systemctl", "--user", "is-active", "rime-llm-translator.service"],
                   check=False)

def main():
    ap = argparse.ArgumentParser(description="Rime offline MT and hotkey-only AI")
    ap.add_argument("command", choices=["setup", "sync", "enable", "disable", "serve",
                                        "doctor", "install-offline", "download-models"],
                    help="Action")
    args = ap.parse_args()
    os.umask(0o077)
    try:
        if args.command == "setup":
            setup(args)
        elif args.command == "sync":
            sync()
        elif args.command == "enable":
            enable()
        elif args.command == "disable":
            disable()
        elif args.command == "serve":
            serve()
        elif args.command == "install-offline":
            install_offline_models()
        elif args.command == "download-models":
            download_models()
        else:
            doctor()
    except (ValueError, RuntimeError, OSError) as exc:
        print("Error:", exc, file=sys.stderr)
        return 1
    return 0

if __name__ == "__main__":
    sys.exit(main())
