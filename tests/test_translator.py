import importlib.util
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
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
    def test_default_languages(self):
        self.assertEqual(list(tr.parse_languages(tr.DEFAULT_LANGUAGES)),
                         ["en", "ja"])

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

    def test_offline_argos_short_text_and_traditional(self):
        cfg = tr.config_default()
        mock_translate = Mock()
        mock_translate.translate.side_effect = (
            lambda text, src, dst: f"{src}:{dst}:{text}")
        with patch.dict(sys.modules, {"argostranslate": Mock(translate=mock_translate)}):
            self.assertEqual(tr.local_translate("你", cfg)["en"], "zh:en:你")
            self.assertEqual(tr.local_translate("學", cfg)["ja"], "zt:ja:學")
            cfg["translation"]["source_language"] = "zt"
            self.assertEqual(tr.local_translate("好", cfg)["en"], "zt:en:好")

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
