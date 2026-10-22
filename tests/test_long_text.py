import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from rime_long_text import Draft, History, PanelWorker, pieces, validate_shortcuts
import rime_llm_translator as core


class LongTextTests(unittest.TestCase):
    def test_chunks_preserve_unicode_paragraphs_and_tail(self):
        source = ("這是一個長句子。123，不要刪除！" * 150) + "\n\n最後一段\r\n  "
        chunks = list(pieces(source))
        self.assertEqual("".join(value for value, _ in chunks), source)
        self.assertTrue(all(len(value.encode()) <= 900 for value, _ in chunks))
        self.assertIn(("\n", False), chunks)

    def test_oversize_rejected_before_translation(self):
        with self.assertRaises(ValueError):
            list(pieces("中" * 11000))

    def test_edit_invalidates_ai_and_pending_send(self):
        draft = Draft()
        draft.edit("你好", "en")
        old = draft.job("ai").copy()
        draft.begin_send(True)
        draft.edit("谢谢", "en")
        self.assertFalse(draft.accept("ai", {"id": old["id"], "text": "Hello"}))
        self.assertFalse(draft.ready("ai"))
        self.assertNotIn("ai", draft.jobs)

    def test_send_reuses_inflight_ai_then_resets_to_mt(self):
        draft = Draft()
        draft.edit("你好", "ja")
        job = draft.job("ai")
        self.assertIs(draft.job("ai"), job)
        mode, value = draft.begin_send(True)
        self.assertEqual(mode, "ai")
        self.assertIsNone(value)
        self.assertFalse(draft.ready("ai"))
        draft.accept("ai", {"id": job["id"], "text": "こんにちは"})
        self.assertEqual(draft.ready("ai"), "こんにちは")
        draft.sent()
        self.assertEqual(draft.begin_send(False), ("mt", None))

    def test_language_change_and_same_text_new_revision_reject_old(self):
        draft = Draft()
        draft.edit("你好", "en")
        job = draft.job("mt").copy()
        draft.edit("你好", "ja")
        draft.edit("你好", "en")
        draft.job("mt")
        self.assertFalse(draft.accept("mt", {"id": job["id"], "text": "Hello"}))

    def test_history_deduplicates_bounds_and_restores_unsent(self):
        history = History(["一", "二", "一"])
        self.assertEqual(history.move(-1, "未发送"), "一")
        self.assertEqual(history.move(-1, "一"), "二")
        self.assertEqual(history.move(1, "二"), "一")
        self.assertEqual(history.move(1, "一"), "未发送")
        for i in range(80):
            history.add(str(i))
        self.assertEqual(len(history.entries), 50)
        history.add("79")
        self.assertEqual(len(history.entries), 50)

    def test_shortcut_conflicts(self):
        with self.assertRaises(ValueError):
            validate_shortcuts({"open": "DoubleAlt", "ai": "TripleAlt"})
        with self.assertRaises(ValueError):
            validate_shortcuts({"open": "Control+space", "send": "Control+space"})
        validate_shortcuts({"open": "Alt+space", "ai": "DoubleAlt", "send": "Button8"})

    def test_truncated_cloud_result_is_rejected(self):
        from unittest.mock import Mock
        from test_translator import Response
        response = Response({"choices": [{"finish_reason": "length", "message": {
            "content": '{"en":"A valid looking but unfinished translation"}'}}]})
        with self.assertRaises(ValueError):
            core.translate("原文还有内容", core.config_default(), "fake-key", opener=Mock(return_value=response))

    def worker(self, directory, mode, callback):
        cfg = core.config_default()
        root = Path(directory)
        key = root / "key"
        key.write_text("fake-test-key")
        helper = SimpleNamespace(CACHE_DIR=root, KEY_PATH=key,
            load_config=lambda: copy.deepcopy(cfg), parse_languages=core.parse_languages,
            translate=lambda text, cfg, key: callback(text),
            local_translate=lambda text, cfg: callback(text),
            atomically_write=lambda path, text: path.write_text(text, encoding="utf-8"))
        worker = PanelWorker(mode, helper)
        worker.request.write_text(json.dumps({"id": "one", "source": "你好\n谢谢", "language": "en"}))
        return worker

    def test_worker_explicit_ai_once_and_preserves_paragraphs(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def translate(text):
                calls.append(text)
                return {"en": text + "!"}
            worker = self.worker(directory, "ai", translate)
            self.assertTrue(worker.poll())
            self.assertFalse(worker.poll())
            self.assertEqual(calls, ["你好", "谢谢"])
            self.assertEqual(json.loads(worker.output.read_text(encoding="utf-8"))["text"], "你好!\n谢谢!")

    def test_worker_stops_between_chunks_when_source_changed(self):
        with tempfile.TemporaryDirectory() as directory:
            calls = []
            def translate(text):
                calls.append(text)
                worker.request.write_text("{}")
                return {"en": "outdated"}
            worker = self.worker(directory, "ai", translate)
            worker.poll()
            self.assertEqual(len(calls), 1)
            self.assertFalse(worker.output.exists())

    def test_ai_failure_no_mt_fallback_no_retry_loop(self):
        with tempfile.TemporaryDirectory() as directory:
            def fail(text):
                raise RuntimeError("secret-provider-response")
            worker = self.worker(directory, "ai", fail)
            worker.poll()
            self.assertFalse(worker.poll())
            result = worker.output.read_text(encoding="utf-8")
            self.assertNotIn("secret-provider-response", result)
            self.assertNotIn("text", json.loads(result))


if __name__ == "__main__":
    unittest.main()
