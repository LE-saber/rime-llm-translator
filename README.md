# Rime LLM Translator — Ubuntu 24.04 Preview

[中文安装指南](README_CN.md) · [Upstream: niyue/rime-ollama-translator](https://github.com/niyue/rime-ollama-translator)

This repository preserves the original Ollama prototype and adds a **separate
implementation for IBus + Rime + external OpenAI-compatible APIs**.
No Ollama or local LLM is required.

## Features
- Preserve normal Chinese Pinyin candidates; add translated English, Japanese
  and custom-language options (choose translation to commit it).
- OpenAI-compatible Chat Completions endpoint including DeepSeek.
- Background systemd user worker with typing debounce; no network activity
  in the Rime Lua filter and no external Python dependencies at runtime.
- API key stored privately in a user-only file, never embedded in Lua or package.
- GitHub Actions builds a downloadable Ubuntu 24.04 Debian installer.

## Install
Download the `.deb` from **Actions → Build Ubuntu installer → Artifacts**.
Release tags `v*` also publish downloadable .deb assets.

```bash
sudo apt install ./rime-llm-translator_0.1.0~preview2_all.deb
rime-llm-translator setup
```

Enter the API URL, model, languages and key as prompted, log out/in and redeploy
the Luna Pinyin schema in IBus. Diagnose with:

```bash
rime-llm-translator doctor
systemctl --user status rime-llm-translator.service
```

## Upgrade from preview1

Install the new `.deb`, then run `rime-llm-translator sync` as your
normal desktop user. This copies the fixed Lua filter without asking for
the API key or overwriting provider settings. Log out and in to reload Rime.

## Configuration
Stored in `~/.config/rime-llm-translator/config.ini`:

```ini
[provider]
base_url = https://api.deepseek.com
model = deepseek-chat

[translation]
enabled = true
languages = en:English,ja:Japanese,fr:French
min_characters = 3
debounce_ms = 800
timeout_seconds = 10
max_tokens = 320
```

API key is stored at `~/.config/rime-llm-translator/api_key` (permissions 600).
Restart the user service after editing provider settings and redeploy Rime for
changes to candidate display settings.

## Preview limitations and privacy

The first translation result is asynchronous; Rime may not display it until
**the next composition/menu refresh**. No guarantee of spontaneous UI refresh.
Input Chinese text is transmitted to the configured external API service.
AI translations can be incorrect. Disable with `enabled = false`.

Only Luna Pinyin on Ubuntu 24.04 IBus Rime is targeted.
Other schemas, Fcitx5 and Rime display environments need verification.

## Development

```bash
python3 -m unittest discover -s tests -v
bash packaging/build-deb.sh
```

New code is an independent implementation inspired by the
[MIT-licensed upstream](https://github.com/niyue/rime-ollama-translator);
original README_CN and Lua prototype remain in git history.
