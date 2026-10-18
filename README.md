# Rime LLM Translator — offline MT + explicit AI correction

Ubuntu 24.04, IBus, Luna Pinyin. Package: `0.3.0~preview6`.

Normal typing uses offline Argos Translate. Only **Ctrl+Shift+Enter** requests an OpenAI-compatible AI revision of the Chinese candidate and available MT drafts. Results are labeled `MT` or `AI`; completed AI results supersede MT and are reused.

## Install

Download the latest successful [GitHub Actions artifact](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml), then:

```bash
sudo apt install ./rime-llm-translator_0.3.0~preview6_amd64.deb && \
  rime-llm-translator install-offline && \
  rime-llm-translator setup && \
  rime-llm-translator enable
```

Log out/in. Add **Chinese > Rime Translator** in Settings > Keyboard > Input Sources and select it. Select Luna Pinyin with Ctrl+grave if necessary. An AI key is optional for offline-only usage.

preview6 pins Argos 1.11.0 and official CPU-only torch 2.8.0, disables pip download caching, checks for at least 3 GiB free before installation and handles subprocess failures without a traceback. Except apt, run all commands as the desktop user.

If preview5 filled the disk with CUDA dependencies, purge its pip download cache before upgrading, then run `rime-llm-translator repair-offline`. This explicitly removes and rebuilds only the app's private `venv`; keys, configuration, Rime dictionaries and language models are retained. See the Chinese recovery commands for details. The MT service defaults to CPU with two intra-op threads.

The separate frontend refreshes late translation results through its own GLib/IBus main loop, without another physical key or OS key injection. The stock Rime engine is retained. Data is stored separately in `~/.config/ibus/rime-llm`; existing native user-frequency databases are not copied.

For preview1–4 upgrades, `rime-llm-translator restore-native` removes only old translator patches from the original Rime directory; redeploy that original input source afterwards. Existing provider settings and API keys are retained by `sync`.

## Behavior and limits

- MT begins with one Chinese character, with a 450ms debounce.
- Install zh→en, zt→en and en→ja models once online; subsequent MT is offline. Chinese→Japanese pivots through English.
- MT and AI run in separate services. Failed jobs retry with a 2–30 second backoff. Partial language results are retained. Each result cache holds at most 350 entries.
- Configure `source_language = auto`, `zh`, or `zt` in `~/.config/rime-llm-translator/config.ini`. Traditional Chinese users should prefer `zt`.
- The source limit is 1200 UTF-8 bytes. Other target languages need extra Argos model packages.
- `disable` stops new translations. Switch back to native Rime at any time.
- AI hotkeys transmit the selected source and available MT drafts to the configured provider. Ordinary MT does not upload text.

CI validates Python/Lua logic, real librime, the built package and real IBus lookup-table signals for late cached MT/AI results. Real downloaded models, API quality/latency and final GNOME/Wayland rendering require manual installation testing. See [中文说明](README_CN.md) and [manual acceptance checklist](docs/MANUAL_TEST.md).

The bundled frontend derives from GPLv3-or-later [ibus-rime 1.5.0](https://github.com/rime/ibus-rime/tree/d525f18b45123869af0055cc8402d459ebdbb9e3); its full modified source and license are included in `frontend/` and the deb package. The original Ollama prototype remains as a reference and is not installed.
