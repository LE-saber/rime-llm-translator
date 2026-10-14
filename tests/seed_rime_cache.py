#!/usr/bin/env python3
"""Seed isolated fake translation results for an offline Rime integration test."""
from pathlib import Path
import sys

home = Path(sys.argv[1])
cfg = home / ".config/rime-llm-translator/config.ini"
cfg.parent.mkdir(parents=True, exist_ok=True)
cfg.write_text(
    "[provider]\n"
    "base_url = https://api.deepseek.com\n"
    "model = deepseek-chat\n\n"
    "[translation]\n"
    "enabled = true\n"
    "languages = en:English,ja:Japanese\n"
    "min_characters = 2\n",
    encoding="utf-8"
)
original = "你好"
identity = original + "|en:English,ja:Japanese|deepseek-chat|https://api.deepseek.com"
a, b = 5381, 0
for byte in identity.encode("utf-8"):
    a = (a * 33 + byte) % (1 << 32)
    b = (b * 65599 + byte) % (1 << 32)
identifier = f"{a:08x}{b:08x}"
results = home / ".cache/rime-llm-translator/results"
results.mkdir(parents=True, exist_ok=True)
(results / (identifier + ".res")).write_text(
    "en\t" + "Hello from Rime AI".encode().hex() + "\n" +
    "ja\t" + "こんにちは".encode().hex() + "\n",
    encoding="utf-8"
)
print("Seeded cached translation for", original, "as", identifier)
