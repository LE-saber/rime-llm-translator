#!/usr/bin/python3
"""Native CLI diagnostics use only the fixed public examples below."""
import json
import subprocess

examples = [{"direction": "zh-en", "text": "你好，我明天上午十点到学校。"},
            {"direction": "zh-en", "text": "謝謝你的幫助。"},
            {"direction": "en-ja", "text": "Thank you for your help."}]
result = subprocess.run(["/usr/libexec/rime-llm-translator/rime-mt",
                         "/usr/share/rime-llm-translator/models"],
    input="".join(json.dumps(row, ensure_ascii=False) + "\n" for row in examples),
    stdout=subprocess.PIPE, text=True, check=True, timeout=60)
rows = [json.loads(line) for line in result.stdout.splitlines()]
assert len(rows) == len(examples) and all(row.get("text", "").strip() for row in rows), result.stdout
for example, row in zip(examples, rows):
    print(example["direction"], example["text"], "=>", row["text"])
