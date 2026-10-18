# Rime LLM Translator — lightweight offline MT + explicit AI

Ubuntu 24.04 amd64, IBus, Luna Pinyin. `0.3.0~preview7` replaces Argos/PyTorch with native CPU-only Bergamot and bundled Mozilla INT8 models. No pip, compilation or first-run model download on the user's machine.

Normal typing produces offline English/Japanese drafts. **Ctrl+Shift+Enter** explicitly sends the original Chinese and available drafts to the configured DeepSeek / OpenAI-compatible API for revision. An API key is optional. MT never uploads input or automatically falls back to cloud AI.

## Install

Download a successful [GitHub Actions artifact](https://github.com/LE-saber/rime-llm-translator/actions/workflows/build.yml), then:

```bash
sudo apt install ./rime-llm-translator_0.3.0~preview7_amd64.deb
rime-llm-translator setup && rime-llm-translator enable
```

Existing users run `sync && enable` instead of `setup` to retain provider settings and keys. `install-offline` now verifies bundled resources. Except apt, run commands as the desktop user.

Log out/in. Add **Chinese > Rime Translator** in Settings > Keyboard > Input Sources. Stock Rime remains available. The new engine uses `~/.config/ibus/rime-llm` and refreshes late results through IBus without another key or OS key injection.

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
