"""Long-text jobs and UI state. No GTK dependency; workers own native inference."""
import copy
import json
import re
import uuid

MAX_BYTES = 32768


def pieces(text, limit=900):
    """Lossless UTF-8 bounded chunks; keep paragraph separators verbatim."""
    if len(text.encode()) > MAX_BYTES:
        raise ValueError("长文本最多 32 KiB，请分次发送")
    for paragraph in re.split(r"(\r\n|\n|\r)", text):
        if not paragraph:
            continue
        if paragraph.isspace():
            yield paragraph, False
            continue
        current, size = "", 0
        for char in paragraph:
            count = len(char.encode())
            if size + count > limit:
                yield current, True
                current, size = "", 0
            current += char
            size += count
        if current:
            yield current, True


class Draft:
    def __init__(self):
        self.source, self.language, self.revision = "", "en", 0
        self.results, self.jobs = {}, {}
        self.send_revision = None

    def edit(self, source, language):
        self.source, self.language = source, language
        self.revision += 1
        self.results.clear()
        self.jobs.clear()
        self.send_revision = None

    def job(self, mode):
        if mode not in self.jobs:
            self.jobs[mode] = {"id": uuid.uuid4().hex, "source": self.source,
                               "language": self.language, "revision": self.revision}
        return self.jobs[mode]

    def accept(self, mode, result):
        if result.get("id") != self.jobs.get(mode, {}).get("id"):
            return False
        if "text" in result and result["text"].strip():
            self.results[mode] = result["text"]
        return True

    def begin_send(self, auto_ai):
        self.send_revision = self.revision
        mode = "ai" if auto_ai or "ai" in self.jobs or "ai" in self.results else "mt"
        return mode, self.results.get(mode)

    def ready(self, mode):
        return self.send_revision == self.revision and self.results.get(mode)

    def sent(self):
        # Sending never turns future edits into automatic cloud requests.
        self.edit("", self.language)


class History:
    def __init__(self, entries=()):
        self.entries = list(dict.fromkeys(x for x in entries if isinstance(x, str)
                                         and x.strip() and len(x.encode()) <= MAX_BYTES))[:50]
        self.index, self.bookmark = -1, ""

    def add(self, text):
        if text.strip() and len(text.encode()) <= MAX_BYTES:
            self.entries = [text] + [x for x in self.entries if x != text]
            self.entries = self.entries[:50]
        self.index = -1

    def move(self, direction, current):
        if not self.entries:
            return current
        if self.index < 0:
            if direction > 0:
                return current
            self.bookmark = current
        self.index = max(-1, min(len(self.entries) - 1, self.index - direction))
        return self.bookmark if self.index < 0 else self.entries[self.index]


def validate_shortcuts(bindings):
    values = list(bindings.values())
    if len(set(values)) != len(values):
        raise ValueError("快捷键重复，请重新录制")
    for a in values:
        for b in values:
            if a != b and a.endswith("Alt") and b.endswith("Alt"):
                if a in ("DoubleAlt", "TripleAlt") and b in ("DoubleAlt", "TripleAlt"):
                    raise ValueError("双击 Alt 与三击 Alt 存在前缀冲突")


class PanelWorker:
    """Shares the existing serialized MT/AI processes; one latest job per mode."""
    def __init__(self, mode, core):
        self.mode, self.core, self.last = mode, core, None
        self.request = core.CACHE_DIR / ("panel-" + mode + ".req")
        self.output = core.CACHE_DIR / ("panel-" + mode + ".res")

    def read(self):
        if not self.request.exists() or self.request.stat().st_size > 210000:
            return {}
        try:
            value = json.loads(self.request.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError):
            return {}

    def poll(self):
        job = self.read()
        rid = job.get("id")
        if not rid or rid == self.last:
            return False
        self.last = rid
        try:
            source = job["source"]
            cfg = copy.deepcopy(self.core.load_config())
            if not cfg.getboolean("translation", "enabled", fallback=True):
                raise ValueError("翻译已禁用")
            languages = self.core.parse_languages(cfg["translation"]["languages"])
            code = job["language"]
            if code not in languages:
                raise ValueError("目标语言已变更，请重新翻译")
            cfg["translation"]["languages"] = code + ":" + languages[code]
            key = ""
            if self.mode == "ai":
                key = self.core.KEY_PATH.read_text(encoding="utf-8").strip()
                if not key:
                    raise ValueError("请在设置中保存 API Key")
            elif code not in ("en", "ja"):
                raise ValueError("此语言仅支持手动 AI 翻译")
            elif not cfg.getboolean("translation", "offline_enabled", fallback=True):
                raise ValueError("离线翻译已关闭")
            chunks = list(pieces(source))
            translated = []
            for chunk, translate in chunks:
                if self.read().get("id") != rid:
                    return True
                if not translate:
                    translated.append(chunk)
                else:
                    result = (self.core.translate(chunk, cfg, key) if self.mode == "ai"
                              else self.core.local_translate(chunk, cfg))
                    if code not in result or not result[code].strip():
                        raise ValueError("翻译结果不完整")
                    translated.append(result[code])
            if self.read().get("id") != rid:
                return True
            result = {"id": rid, "text": "".join(translated)}
        except Exception as exc:
            # No provider response, source, key or exception message in IPC/logs.
            result = {"id": rid, "error": type(exc).__name__,
                      "message": "翻译失败，请检查 API、模型、目标语言及网络；原文已保留"}
        self.core.atomically_write(self.output, json.dumps(result, ensure_ascii=False))
        return True
