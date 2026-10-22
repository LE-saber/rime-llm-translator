# Rime LLM Translator — lightweight offline MT + explicit AI

Ubuntu 24.04 amd64, IBus, Luna Pinyin. `0.3.0~preview12` uses native CPU-only Bergamot and bundled Mozilla INT8 models, with configurable AI shortcuts including double Alt. No pip, compilation or first-run model download on the user's machine.

Normal typing produces offline English/Japanese drafts. The AI shortcut (default **Ctrl+Shift+Enter**) explicitly sends the original Chinese and available drafts to the configured DeepSeek / OpenAI-compatible API for revision. An API key is optional. MT never uploads input or automatically falls back to cloud AI.

## Install

preview12 improves the native floating editor with icon controls, fresh empty drafts, unsent history recall, and a spinner with elapsed seconds during AI send. AI-on-send defaults on once the provider is configured and can be disabled. The destination follows the latest real text field selected while the panel is open; editing or focusing settings inside the panel never replaces it. A bundled GNOME 46 bridge restores and verifies that destination on Wayland. See [long-text behavior and acceptance](docs/LONG_TEXT.md). Run sync + enable and log out/in after upgrading.

Download a successful [GitHub Actions artifact](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml), then:

```bash
sudo apt install ./rime-llm-translator_0.3.0~preview12_amd64.deb
rime-llm-translator setup && rime-llm-translator enable
```

Existing users run `sync && enable` instead of `setup` to retain provider settings and keys. `install-offline` now verifies bundled resources. Except apt, run commands as the desktop user.

Log out/in. Add **Chinese > Rime Translator** in Settings > Keyboard > Input Sources. Stock Rime remains available. The new engine uses `~/.config/ibus/rime-llm` and refreshes late results through IBus without another key or OS key injection.

## Change the AI shortcut

```bash
rime-llm-translator hotkey 'Control+Alt+j'
rime-llm-translator hotkey
```

For double Alt (preview9 or newer):

```bash
rime-llm-translator hotkey DoubleAlt
```

Tap and release the same Alt key twice within 400 ms while a native Chinese candidate is selected. Left Alt is recommended: right Alt may be AltGr on some layouts. Holding/repeating Alt, another key, changing focus or resetting composition cancels the sequence. Pure Alt is reserved for this gesture while composing; Alt combinations still pass through, and outside a Chinese composition Alt is unchanged. The gesture uses the frontend's monotonic clock and never automatically commits text.

Choose a shortcut unused by your desktop, applications and VM host. The command only changes `[translation] ai_hotkey` in `~/.config/rime-llm-translator/config.ini`, retaining provider settings, API key and dictionaries. `setup` also asks for the shortcut; `doctor` displays it. Changes take effect immediately after the current frontend and plugin are loaded. When upgrading, run `sync && enable` and log out/in once first.

Use one or more of `Control` (`Ctrl`), `Alt`, `Shift`, `Super`, followed by a letter, digit, `F1`–`F12`, `Return` (`Enter`) or `space`. At least one of Control/Alt/Super is required. Example: `Control+Shift+F8`. The old shortcut stops requesting AI after a change. A desktop or VM host shortcut may intercept keys before they reach Rime; this tool cannot detect all such conflicts.

Use the shortcut while a Chinese candidate is selected and the composition remains open. It is handled inside Rime Translator, not registered as a global desktop shortcut. Ordinary Traditional Chinese input remains available.

## Behavior and resources

- One native computation process and inference thread, at most one logical CPU by default. Only one model direction is resident; changing direction releases the old model. 60 seconds idle exits the child and releases its memory.
- One Chinese character triggers MT after a 450 ms debounce. Only the latest pending input is retained. English publishes before Japanese finishes.
- OpenCC normalizes only the MT copy to simplified Chinese. Japanese pivots through English; AI keeps the original Chinese.
- Separate MT/AI services, timeouts and caches. Each cache has at most 350 entries and 10 MiB; model revisions invalidate old results.
- Input limit: 1200 UTF-8 bytes, with token-budget splitting. Offline targets: English and Japanese. Other languages can use explicit AI requests.
- CPU must expose SSE4.1. Native builds do not use `-march=native`.
- Model resources total about 60.8 decimal MB. Chinese-English uses tiny (not yet marked Release in the upstream registry); English-Japanese uses base-memory. This is a preview requiring manual draft-quality acceptance. See `RESOURCE_REPORT.md` for measured disk, latency and memory, and `mt-benchmark.json` for public sample translations. GitHub runner measurements are not VM performance guarantees.

## Cleanup

```bash
rime-llm-translator cleanup-legacy          # preview only
rime-llm-translator cleanup-legacy --apply  # delete private old venv/temp files
```

Keys, configuration and Rime dictionaries remain. Shared pip cache and old Argos models require explicit `--pip-cache` / `--argos-models` selection; symlink redirects are refused. See [upgrade and cleanup](docs/UPGRADE_CLEANUP.md) for disk-full recovery and shared-data implications.

Use `doctor` for diagnosis, `disable` to stop new translations, and switch to stock Rime at any time. For preview1–4, `restore-native` removes translator patches from the original Rime schema; redeploy afterwards.

See [中文说明](README_CN.md), [manual acceptance](docs/MANUAL_TEST.md) and [plan](docs/LIGHTWEIGHT_MT_PLAN.md). Builds/tests use GitHub Actions without WSL. Cloud quality and GNOME/Wayland behavior require user acceptance.

The frontend derives from GPLv3-or-later ibus-rime 1.5.0, with modified sources and license included in `frontend/` and the package. The Mozilla inference sources, dependency licenses and pinned submodules are included as `/usr/share/doc/rime-llm-translator/inference-source.tar.xz`; wrapper sources and revisions accompany it. Mozilla models are MPL 2.0; hashes are in `native/mt/models.lock.json`. The root Ollama prototype is retained as an unused upstream reference.
