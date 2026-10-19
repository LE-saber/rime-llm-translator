import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
import os
import subprocess
import shutil
from contextlib import ExitStack, contextmanager
from unittest.mock import patch, Mock

MODULE = Path(__file__).resolve().parents[1] / "src/rime_llm_translator.py"
spec = importlib.util.spec_from_file_location("translator", MODULE)
tr = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tr)

class Response:
    def __init__(self, data):
        self.data = json.dumps(data).encode("utf-8")
    def __enter__(self):
        return self
    def __exit__(self, *_):
        return False
    def read(self, maximum):
        return self.data[:maximum]

class TranslatorTests(unittest.TestCase):
    @contextmanager
    def worker_environment(self):
        with tempfile.TemporaryDirectory() as directory, ExitStack() as stack:
            root = Path(directory)
            paths = {"CACHE_DIR": root, "MT_RESULTS": root / "mt", "AI_RESULTS": root / "ai",
                     "LATEST_PATH": root / "latest.req", "AI_REQUEST": root / "ai.req",
                     "KEY_PATH": root / "api_key"}
            for name, path in paths.items():
                stack.enter_context(patch.object(tr, name, path))
            tr.MT_RESULTS.mkdir()
            tr.AI_RESULTS.mkdir()
            cfg = tr.config_default()
            stack.enter_context(patch.object(tr, "load_config", side_effect=lambda: self.copy_config(cfg)))
            tr.LATEST_PATH.write_text("12345678abcdef90\n" + "你好".encode().hex() + "\n")
            os.utime(tr.LATEST_PATH, (0, 0))
            yield cfg

    @staticmethod
    def copy_config(cfg):
        copy = tr.config_default()
        copy.read_dict({section: dict(cfg[section]) for section in cfg.sections()})
        return copy

    def test_mt_retries_unchanged_request_after_transient_failure(self):
        with self.worker_environment(), patch.object(tr.time, "monotonic", return_value=10), \
                patch.object(tr, "local_translate", side_effect=[RuntimeError("transient"),
                         {"en": "Hello", "ja": "こんにちは"}]) as translate:
            worker = tr.Worker("mt")
            self.assertFalse(worker.poll())
            self.assertFalse(worker.poll())
            self.assertEqual(translate.call_count, 1)
            worker.retry_at = 0
            self.assertTrue(worker.poll())
            self.assertEqual(translate.call_count, 2)
            self.assertEqual(tr.read_results(tr.MT_RESULTS / "12345678abcdef90.res")["en"], "Hello")
            worker.poll()
            self.assertEqual(translate.call_count, 2)

    def test_partial_mt_cache_is_preserved_and_only_missing_language_retried(self):
        with self.worker_environment(), patch.object(tr, "local_translate",
                side_effect=[{"en": "Hello"}, {"ja": "こんにちは"}]) as translate:
            worker = tr.Worker("mt")
            self.assertFalse(worker.poll())
            worker.retry_at = 0
            self.assertTrue(worker.poll())
            self.assertEqual(translate.call_args.args[1]["translation"]["languages"], "ja:Japanese")
            self.assertEqual(len(tr.read_results(tr.MT_RESULTS / "12345678abcdef90.res")), 2)

    def test_published_english_survives_later_native_failure(self):
        def partial_failure(text, cfg, publish, **kwargs):
            publish({"en": "Hello"})
            raise RuntimeError("Japanese engine failed")
        with self.worker_environment(), patch.object(tr, "local_translate", side_effect=partial_failure):
            self.assertFalse(tr.Worker("mt").poll())
            self.assertEqual(tr.read_results(tr.MT_RESULTS / "12345678abcdef90.res"), {"en": "Hello"})

    def test_mt_worker_never_reads_key_or_calls_ai(self):
        with self.worker_environment(), patch.object(tr, "translate", side_effect=AssertionError("AI called")) as ai, \
                patch.object(tr, "local_translate", return_value={"en": "Hello", "ja": "Hi"}):
            self.assertTrue(tr.Worker("mt").poll())
            ai.assert_not_called()
            self.assertFalse(tr.AI_REQUEST.exists())

    def test_ai_receives_mt_drafts_and_reuses_completed_cache(self):
        with self.worker_environment(), patch.object(tr, "translate",
                return_value={"en": "Hello", "ja": "こんにちは"}) as ai:
            tr.AI_REQUEST.write_bytes(tr.LATEST_PATH.read_bytes())
            tr.KEY_PATH.write_text("fake-test-key")
            (tr.MT_RESULTS / "12345678abcdef90.res").write_text(tr.encode_results({"en": "Helo"}))
            self.assertTrue(tr.Worker("ai").poll())
            self.assertEqual(ai.call_args.kwargs["drafts"], {"en": "Helo"})
            self.assertFalse(tr.Worker("ai").poll())
            self.assertEqual(ai.call_count, 1)

    def test_cache_cleanup_bounds_both_active_directories(self):
        with self.worker_environment():
            for folder in (tr.MT_RESULTS, tr.AI_RESULTS):
                for index in range(5):
                    path = folder / (str(index) + ".res")
                    path.write_text("cached")
                    os.utime(path, (index + 1, index + 1))
            tr.trim_cache(keep=2)
            for folder in (tr.MT_RESULTS, tr.AI_RESULTS):
                self.assertEqual({p.name for p in folder.iterdir()}, {"3.res", "4.res"})

    def test_default_languages(self):
        self.assertEqual(list(tr.parse_languages(tr.DEFAULT_LANGUAGES)),
                         ["en", "ja"])

    def test_hotkey_normalization_and_legacy_default(self):
        self.assertEqual(tr.config_default()["translation"]["ai_hotkey"], "Control+Shift+Return")
        for raw, expected in (("Ctrl+Alt+J", "Control+Alt+j"),
                              ("shift + ctrl + enter", "Control+Shift+Return"),
                              ("Super+f8", "Super+F8"), ("Alt+space", "Alt+space"),
                              (" doublealt ", "DoubleAlt")):
            with self.subTest(raw=raw):
                self.assertEqual(tr.normalize_hotkey(raw), expected)

    def test_reject_unsafe_or_invalid_hotkeys(self):
        for raw in ("", "j", "Shift+j", "Control", "Control+", "Ctrl+Control+j",
                    "Control+Alt+F13", "Release+Control+j", "Control+Shift+Foo",
                    "Control+Alt+j+q", "Control+Alt+\n"):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                tr.normalize_hotkey(raw)

    def test_hotkey_command_preserves_configuration_and_key(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cfg = tr.config_default()
            cfg["provider"]["model"] = "my-existing-model"
            cfg["translation"]["languages"] = "en:English"
            with patch.object(tr, "CONFIG_DIR", root), \
                    patch.object(tr, "CONFIG_PATH", root / "config.ini"), \
                    patch.object(tr.os, "geteuid", return_value=1000, create=True), \
                    patch("sys.stdout", new_callable=io.StringIO) as output:
                tr.save_config(cfg)
                key = root / "api_key"
                key.write_text("fake-secret")
                tr.hotkey("Ctrl+Alt+j")
                saved = tr.load_config()
                self.assertEqual(saved["translation"]["ai_hotkey"], "Control+Alt+j")
                self.assertEqual(saved["provider"]["model"], "my-existing-model")
                self.assertEqual(saved["translation"]["languages"], "en:English")
                self.assertEqual(key.read_text(), "fake-secret")
                before = tr.CONFIG_PATH.read_bytes()
                tr.hotkey()
                self.assertIn("AI shortcut: Control+Alt+j", output.getvalue())
                with self.assertRaises(ValueError):
                    tr.hotkey("j")
                self.assertEqual(tr.CONFIG_PATH.read_bytes(), before)

    def test_custom_languages(self):
        self.assertEqual(tr.parse_languages("en:English,fr:French,ko:Korean")["fr"],
                         "French")

    def test_reject_duplicate_and_invalid_language(self):
        for value in ("en:English,en:English", "xx", "", "en:English,invalid:Name"):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    tr.parse_languages(value)

    def test_api_url(self):
        self.assertEqual(tr.chat_url("https://api.deepseek.com"),
                         "https://api.deepseek.com/chat/completions")
        self.assertEqual(tr.chat_url("https://example.com/v1/chat/completions"),
                         "https://example.com/v1/chat/completions")
        with self.assertRaises(ValueError):
            tr.chat_url("http://example.com")

    def test_parse_model_answer(self):
        got = tr.parse_answer('{"en":"Hello","ja":"こんにちは","other":"x"}',
                              {"en": "English", "ja": "Japanese"})
        self.assertEqual(got, {"en": "Hello", "ja": "こんにちは"})
        self.assertEqual(tr.parse_answer('```json\n{"en":"Hi"}\n```',
                                          {"en":"English"}), {"en":"Hi"})

    def test_mock_chat_completions(self):
        cfg = tr.config_default()
        record = {}
        def opener(req, timeout):
            record["url"] = req.full_url
            record["headers"] = dict(req.headers)
            record["body"] = json.loads(req.data)
            return Response({"choices":[{"message":{"content":
                             '{"en":"Hello","ja":"こんにちは"}'}}]})
        result = tr.translate("你好", cfg, "test-secret", opener, drafts={"en": "Helo"})
        self.assertEqual(result["en"], "Hello")
        self.assertIn("/chat/completions", record["url"])
        self.assertEqual(record["body"]["model"], "deepseek-chat")
        self.assertEqual(json.loads(record["body"]["messages"][1]["content"])["offline_mt_drafts"]["en"], "Helo")
        self.assertTrue(record["headers"]["Authorization"].startswith("Bearer "))
        self.assertNotIn("test-secret", json.dumps(record["body"]))

    def test_request_encoding(self):
        original = "你好，世界"
        rid = "12345678abcdef90"
        self.assertEqual(tr.decode_request(rid+"\n"+original.encode().hex()+"\n"),
                         (rid, original))
        with self.assertRaises(ValueError):
            tr.decode_request("../bad\n0a\n")
        self.assertIn("e38193", tr.encode_results({"ja": "こ"}))

    def test_bad_answer(self):
        for content in ("not json", "[]", '{"x":"missing"}'):
            with self.subTest(content=content):
                with self.assertRaises(ValueError):
                    tr.parse_answer(content, {"en": "English"})

    def test_rime_schema_patch_preserves_user_patches(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("Requires python3-yaml")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            custom = root / "luna_pinyin.custom.yaml"
            custom.write_text('patch:\n  "menu/page_size": 9\n',
                              encoding="utf-8")
            with patch.object(tr, "RIME_DIR", root):
                tr.safe_schema_patch()
                tr.safe_schema_patch()
                data = yaml.safe_load(custom.read_text(encoding="utf-8"))
                self.assertEqual(data["patch"]["menu/page_size"], 9)
                self.assertEqual(data["patch"][tr.PATCH_KEY], [tr.PATCH_VALUE])
                self.assertEqual(data["patch"][tr.PROCESSOR_KEY], tr.PROCESSOR_VALUE)
                self.assertNotIn(tr.LEGACY_PATCH_KEY, data["patch"])
                tr.remove_schema_patch()
            data = yaml.safe_load(custom.read_text(encoding="utf-8"))
            self.assertEqual(data["patch"]["menu/page_size"], 9)
            self.assertNotIn(tr.PATCH_KEY, data["patch"])
            self.assertNotIn(tr.PROCESSOR_KEY, data["patch"])

    def test_legacy_filter_patch_migration(self):
        try:
            import yaml
        except ImportError:
            self.skipTest("Requires python3-yaml")
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            custom = root / "luna_pinyin.custom.yaml"
            custom.write_text('patch:\n  "engine/filters/@before 0": "lua_filter@*rime_llm_translator"\n', encoding="utf-8")
            with patch.object(tr, "RIME_DIR", root):
                tr.safe_schema_patch()
            data = yaml.safe_load(custom.read_text(encoding="utf-8"))["patch"]
            self.assertNotIn(tr.LEGACY_PATCH_KEY, data)
            self.assertEqual(data[tr.PATCH_KEY], [tr.PATCH_VALUE])
            self.assertEqual(data[tr.PROCESSOR_KEY], tr.PROCESSOR_VALUE)

if __name__ == "__main__":
    unittest.main()
