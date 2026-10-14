# Rime LLM Translator — offline MT + explicit AI correction

Ubuntu 24.04, IBus Rime, Luna Pinyin. **Normal typing never calls the AI API.**

- **Offline machine translation** via [Argos Translate](https://github.com/argosopentech/argos-translate). Install the zh→en, zt→en and en→ja models once while online, then translate without network access.
- Native Chinese candidates are always shown first. Offline results are marked `🌐 MT · EN` / `🌐 MT · JA`.
- Press **Ctrl+Shift+Enter** while selecting a Chinese Rime candidate to queue a single OpenAI-compatible AI correction. Cached AI results supersede the corresponding MT output and are marked `✦ AI · EN` / `✦ AI · JA`.
- Automatic offline MT begins with one Chinese character; only the latest input after a configurable short debounce is processed.
- Important limit: the background worker does not directly notify a stationary Rime GUI candidate menu; a subsequent Rime composition refresh/key event may be needed to show new translations. No synchronous translation is run inside Rime.

## Ubuntu installation

Download the `preview4` .deb from [Actions](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml):

```bash
sudo apt install ./rime-llm-translator_0.2.0~preview4_all.deb

# One-time Internet use to install Argos in a private Python venv + download models
rime-llm-translator install-offline

# Configure provider, target languages, API key (first time only)
rime-llm-translator setup

# Existing users should use sync instead of setup to retain settings
rime-llm-translator sync

# Explicitly opt in: setup and sync never patch a working Rime input method
rime-llm-translator enable
```

Redeploy Luna Pinyin and log out/in. If the native Chinese candidates disappear, use `rime-llm-translator disable` and redeploy Rime. This preserves dictionaries and provider secrets.

Configure source language with `source_language = auto`, `zh`, or `zt` under `[translation]` in `~/.config/rime-llm-translator/config.ini`. Set `zt` if you primarily use Traditional Chinese. Configured targets default to `en:English,ja:Japanese`; other targets require Argos language packs installed separately.

## Safety, testing and limitations

CI uses real Ubuntu 24.04 librime + librime-plugin-lua to verify Chinese candidates remain intact, MT/AI cache selection, and the manual shortcut dispatch. Python tests cover mock Argos translation and patch rollback. Actual downloaded Argos packages, live API calls, GUI/Wayland candidate repaint and CPU throughput remain desktop validation tasks; this is a preview.

Do not enable AI on sensitive input: hotkey requests send the selected source text to the configured remote provider. Normal MT never sends text to any server.

See [中文说明](README_CN.md).
