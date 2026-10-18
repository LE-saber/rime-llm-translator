import contextlib
import hashlib
import io
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import rime_mt as mt
import rime_llm_translator as tr


class NativeTests(unittest.TestCase):
    def test_english_is_published_before_japanese_failure(self):
        published = []
        with patch.object(mt.NATIVE, "infer", side_effect=["Hello", RuntimeError("missing Japanese")]):
            with self.assertRaises(RuntimeError):
                mt.local_translate("你好", tr.config_default(), publish=lambda values: published.append(dict(values)))
        self.assertEqual(published, [{"en": "Hello"}])

    def test_skip_japanese_for_outdated_request(self):
        with patch.object(mt.NATIVE, "infer", return_value="Hello") as infer:
            result = mt.local_translate("你好", tr.config_default(), current=lambda: False)
        self.assertEqual(result, {"en": "Hello"})
        self.assertEqual(infer.call_count, 1)

    def test_japanese_retry_reuses_existing_english(self):
        cfg = tr.config_default()
        cfg["translation"]["languages"] = "ja:Japanese"
        with patch.object(mt.NATIVE, "infer", return_value="こんにちは") as infer:
            result = mt.local_translate("你好", cfg, existing={"en": "Hello"})
        infer.assert_called_once_with("en-ja", "Hello", 15)
        self.assertEqual(result, {"ja": "こんにちは"})

    def test_unknown_language_does_not_start_model(self):
        cfg = tr.config_default()
        cfg["translation"]["languages"] = "fr:French"
        with patch.object(mt.NATIVE, "infer") as infer:
            with self.assertRaises(RuntimeError):
                mt.local_translate("你好", cfg)
        infer.assert_not_called()

    def test_helper_timeout_and_idle_exit_return_process_memory(self):
        with tempfile.TemporaryDirectory() as directory:
            helper = Path(directory) / "helper"
            helper.write_text('#!/usr/bin/python3\nimport json,sys,time\n'
                              'for line in sys.stdin:\n'
                              ' r=json.loads(line)\n'
                              ' if r["text"]=="slow": time.sleep(2)\n'
                              ' print(json.dumps({"text":"OK"}),flush=True)\n')
            helper.chmod(0o700)
            runtime = mt.NativeRuntime()
            try:
                with patch.object(mt, "MT_BINARY", helper), patch.object(mt, "check_offline"):
                    self.assertEqual(runtime.infer("zh-en", "你好"), "OK")
                    process = runtime.process
                    runtime.last_used = 0
                    runtime.reap_idle(1)
                    self.assertIsNone(runtime.process)
                    self.assertIsNotNone(process.poll())
                    with self.assertRaises(TimeoutError):
                        runtime.infer("zh-en", "slow", timeout=.05)
                    self.assertIsNone(runtime.process)
            finally:
                runtime.close()

    def test_corrupt_model_fails_before_starting_helper(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / "zh-en").mkdir()
            (root / "zh-en/config.yml").touch()
            (root / "zh-en/model.bin").write_bytes(b"corrupt")
            lock = root / "lock.json"
            lock.write_text(json.dumps({"models": {"zh-en": {"files": {"model": {
                "filename": "model.bin", "uncompressedHash": hashlib.sha256(b"expected").hexdigest()}}}}}))
            with patch.object(mt, "MT_BINARY", Path(sys.executable)), patch.object(mt, "MODEL_DIR", root), \
                    patch.object(mt, "MODEL_LOCK", lock):
                with self.assertRaisesRegex(RuntimeError, "checksum"):
                    mt.check_offline()


class CleanupTests(unittest.TestCase):
    @contextlib.contextmanager
    def home(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(mt.Path, "home", return_value=Path(directory)), \
                patch.object(mt.os, "geteuid", return_value=1000), \
                contextlib.redirect_stdout(io.StringIO()):
            root = Path(directory)
            venv = root / ".local/share/rime-llm-translator/venv"
            venv.mkdir(parents=True)
            (venv / "old-torch").write_bytes(b"old")
            yield root, venv

    def test_dry_run_and_default_cleanup_keep_shared_data_and_settings(self):
        with self.home() as (home, venv), patch.object(mt, "check_offline"), \
                patch.object(mt.subprocess, "run"):
            key = home / ".config/rime-llm-translator/api_key"
            key.parent.mkdir(parents=True)
            key.write_text("keep")
            rime = home / ".config/ibus/rime/user.dict"
            rime.parent.mkdir(parents=True)
            rime.write_text("keep")
            pip = home / ".cache/pip/keep"
            pip.parent.mkdir(parents=True)
            pip.touch()
            mt.cleanup_legacy()
            self.assertTrue(venv.is_dir())
            mt.cleanup_legacy(apply=True)
            self.assertFalse(venv.exists())
            self.assertTrue(key.is_file() and rime.is_file() and pip.is_file())

    def test_refuse_symlink_and_symlink_parent_before_any_delete(self):
        with self.home() as (home, venv), patch.object(mt.subprocess, "run") as run:
            outside = home / "protected"
            outside.mkdir()
            (outside / "keep").touch()
            pip = home / ".cache/pip"
            pip.parent.mkdir()
            pip.symlink_to(outside, target_is_directory=True)
            with self.assertRaisesRegex(RuntimeError, "symlink"):
                mt.cleanup_legacy(apply=True, include_pip=True)
            self.assertTrue(venv.exists() and (outside / "keep").exists())
            run.assert_not_called()

    def test_pip_and_specific_argos_models_require_explicit_flags(self):
        with self.home() as (home, venv), patch.object(mt, "check_offline"), \
                patch.object(mt.subprocess, "run"):
            pip = home / ".cache/pip"
            pip.mkdir(parents=True)
            models = home / ".local/share/argos-translate/packages"
            for name, source, target in (("old-zh-en", "zh", "en"), ("keep-fr-en", "fr", "en")):
                model = models / name
                model.mkdir(parents=True)
                (model / "metadata.json").write_text(json.dumps({"from_code": source, "to_code": target}))
            mt.cleanup_legacy(apply=True, include_pip=True, include_argos=True)
            self.assertFalse(pip.exists() or (models / "old-zh-en").exists())
            self.assertTrue((models / "keep-fr-en").exists())

    def test_invalid_new_install_prevents_removing_old_backend(self):
        with self.home() as (_, venv), patch.object(mt, "check_offline", side_effect=RuntimeError("missing")), \
                patch.object(mt.subprocess, "run") as run:
            with self.assertRaises(RuntimeError):
                mt.cleanup_legacy(apply=True)
            self.assertTrue(venv.exists())
            run.assert_not_called()
