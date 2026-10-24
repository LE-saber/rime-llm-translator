# Rime LLM Translator

[English](README.md) · [简体中文](README_CN.md) · [繁體中文](https://github.com/LE-saber/rime-llm-translator/blob/main/README.zh-TW.md) · [日本語](https://github.com/LE-saber/rime-llm-translator/blob/main/README.ja.md) · [Download v0.3.0](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) · [Changelog](CHANGELOG.md)

Chinese input, lightweight offline translation and optional cloud AI for **Ubuntu 24.04 amd64, GNOME 46, IBus and Luna Pinyin**. Traditional Chinese remains available. Windows and other desktops are outside this release's supported scope.

Type normally for English/Japanese translation candidates, or revise longer Chinese text in a floating editor before sending its translation. Native GTK3, C/IBus and CPU-only Bergamot INT8 share one offline worker. Models are bundled: no pip, GPU, local compilation or first-run model downloads.

## Screenshots

Large editable source, compact language preview, icon tools and configurable AI-on-send:

![Native floating editor, light theme](docs/images/long-text-light.png)

Dracula-style dark theme; AI sends show a spinner and elapsed seconds:

![AI translation in progress](docs/images/ai-sending.png)

[Dark editor](docs/images/long-text-dark.png) · [GUI settings](docs/images/settings.png). These are native GTK screenshots from GitHub Actions using public test text and a local mock AI provider, illustrating the UI and interactions.

## Install or upgrade

Download the `.deb` and `SHA256SUMS` from [Releases](https://github.com/LE-saber/rime-llm-translator/releases/tag/v0.3.0) into the same directory:

```bash
sha256sum --check SHA256SUMS
sudo apt install ./rime-llm-translator_0.3.0_amd64.deb
```

New installation:

```bash
rime-llm-translator setup && rime-llm-translator enable
```

Upgrade from a preview, retaining API keys and preferences:

```bash
rime-llm-translator sync && rime-llm-translator enable
```

Run commands as your desktop user except for APT. **Log out and back in**, then add **Chinese → Rime Translator** in Settings → Keyboard → Input Sources. Select Luna Pinyin with Ctrl+grave if necessary. `sync` / `enable` install the per-user GNOME bridge; if user extensions are globally disabled, enable them in GNOME Extensions. `doctor` should report the floating-panel bridge as active.

Stock Rime remains independent; this engine uses `~/.config/ibus/rime-llm`. Credentials are optional for offline English/Japanese. Open GUI settings with `rime-llm-translator settings` or the application launcher entry.

## Using it

| Action | Behavior |
|---|---|
| Normal Chinese composition | Native Chinese plus `🌐 MT · EN/JA` candidates; late results refresh without another key |
| AI shortcut, default Ctrl+Shift+Enter | Explicit API revision of the selected Chinese candidate; no automatic commit |
| Open editor, default Alt+Space | Empty, resizable, always-above panel; selected Chinese is kept in history |
| Edit in the panel | Rime selections accumulate in the editable source; offline preview follows edits |
| Send, default Ctrl+Enter | Send the preview language to the latest selected real text field, then clear on success |
| Empty source + ↑ / ↓ | Recall recent local text, including drafts closed without sending |

The destination follows the latest real text field selected while the panel is open: start in A, select B, return to the panel, then send to B. This also works between fields in one window. The panel and its settings fields never become destinations. GNOME integration restores and verifies the target; a closed/invalid target or failed submission preserves the source. No global paste or simulated typing is used.

**Live preview uses offline MT. AI-on-send defaults on once an API URL, model and nonempty key are configured; you can turn it off.** Manual AI affects only the current text/language. Edits, language changes and successful sends return to MT preview. AI failure, timeout or stale/truncated output never silently sends MT instead. Only requested AI operations upload text to the configured provider.

Record shortcuts in GUI settings; DoubleAlt / TripleAlt and in-panel mouse side buttons are supported. Alt+Space may conflict with GNOME's window menu: record an unused opening chord such as Ctrl+Alt+Space. Opening depends on keyboard events reaching Rime Translator, not a global desktop shortcut. CLI example:

```bash
rime-llm-translator hotkey DoubleAlt
```

Double Alt requires two complete taps of the same Alt within 400 ms while a Chinese candidate is selected. Desktop/VM host shortcuts can intercept events. See [long-text behavior and acceptance](docs/LONG_TEXT.md).

## Resources and limits

- One native inference process/thread; one model direction resident at a time; the child exits after 60 seconds idle. The panel loads on demand, with no browser runtime.
- Chinese→English tiny model; Japanese pivots through English→Japanese base-memory. OpenCC normalizes only the MT copy; AI receives the original Chinese. These are basic drafts requiring human review, especially names, numbers and negation. The upstream tiny model is not marked Release in its registry.
- CPU must expose SSE4.1 to the VM. Ordinary candidates accept 1,200 UTF-8 bytes; the panel accepts 32 KiB and translates ordered chunks. Offline languages: English/Japanese; other configured languages require AI.
- MT/AI have separate services and bounded caches (350 entries / 10 MiB each). Logs omit text, translations and keys. Optional local history stores up to 50 deduplicated entries and can be cleared/disabled.

Download `RESOURCE_REPORT.md` and `mt-benchmark.json` from the Release for actual package size, measured disk/RSS/latency and public sample translations. System dependencies are additional; runner measurements do not predict your VM's speed.

## Help, cleanup and development

```bash
rime-llm-translator doctor
rime-llm-translator install-offline        # verify bundled resources
rime-llm-translator cleanup-legacy         # inspect old private venv/temp files
rime-llm-translator cleanup-legacy --apply # remove selected legacy files
```

Cleanup retains keys, settings, history and Rime dictionaries. Shared pip cache / Argos models require explicit options. See [upgrade and cleanup](docs/UPGRADE_CLEANUP.md), [manual acceptance](docs/MANUAL_TEST.md), [build instructions](docs/DEVELOPMENT.md) and [changes](CHANGELOG.md).

GitHub Actions tests Ubuntu 24.04 package installation, unit tests, real Rime/IBus/GTK, real GNOME 46 Wayland focus/submission, mock AI failures and network-disabled native model benchmarks. No WSL is used. Actual cloud quality and the user's applications/VM still need manual acceptance.

## Source and licenses

The frontend derives from GPLv3-or-later [ibus-rime 1.5.0](https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3); its source/license are in [frontend/](frontend/) and the package. Mozilla inference sources, pinned dependencies and license texts are bundled in `/usr/share/doc/rime-llm-translator/inference-source.tar.xz`; wrapper sources and revisions accompany them. Mozilla models are MPL 2.0, with hashes/licenses recorded in [models.lock.json](native/mt/models.lock.json). Third-party components retain their own licenses. The root Ollama Lua prototype is an unused upstream reference, not the installed runtime.
