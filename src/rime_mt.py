"""Packaged native offline MT and explicit legacy cleanup; no pip/network use."""
import hashlib
import json
import os
from pathlib import Path
import selectors
import shutil
import subprocess
import time

ASSET_DIR = Path("/usr/share/rime-llm-translator")
MT_BINARY = Path("/usr/libexec/rime-llm-translator/rime-mt")
MODEL_DIR = ASSET_DIR / "models"
MODEL_LOCK = ASSET_DIR / "models.lock.json"
REVISION_FILE = ASSET_DIR / "mt-revision"


def revision():
    return REVISION_FILE.read_text().strip() if REVISION_FILE.is_file() else "bergamot-v1"


def check_offline():
    if not MT_BINARY.is_file() or not os.access(MT_BINARY, os.X_OK):
        raise RuntimeError("Native MT engine missing; reinstall the .deb")
    lock = json.loads(MODEL_LOCK.read_text())
    for direction, model in lock["models"].items():
        if not (MODEL_DIR / direction / "config.yml").is_file():
            raise RuntimeError("Offline model configuration missing: " + direction)
        for asset in model["files"].values():
            path = MODEL_DIR / direction / asset["filename"]
            with path.open("rb") as fp:
                checksum = hashlib.file_digest(fp, "sha256").hexdigest()
            if checksum != asset["uncompressedHash"]:
                raise RuntimeError("Offline model checksum mismatch: " + direction)
    try:
        subprocess.run([str(MT_BINARY), "--check-cpu"], check=True, timeout=5,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except subprocess.SubprocessError as exc:
        raise RuntimeError("Native engine cannot start; check CPU SSE4.1 support and system libraries") from exc
    return lock


class NativeRuntime:
    """One bounded request at a time; idle process exit returns native memory."""
    def __init__(self):
        self.process = None
        self.last_used = 0

    def close(self):
        if self.process is not None:
            process, self.process = self.process, None
            if process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            process.stdin.close()
            process.stdout.close()

    def reap_idle(self, seconds=60):
        if self.process and time.monotonic() - self.last_used >= seconds:
            self.close()

    def infer(self, direction, text, timeout=15):
        if self.process is None or self.process.poll() is not None:
            self.close()
            check_offline()
            env = dict(os.environ, OMP_NUM_THREADS="1", OPENBLAS_NUM_THREADS="1",
                       MKL_NUM_THREADS="1", MALLOC_ARENA_MAX="2")
            # Third-party diagnostics can include user text: never forward them.
            self.process = subprocess.Popen([str(MT_BINARY), str(MODEL_DIR)],
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, env=env)
        try:
            message = json.dumps({"direction": direction, "text": text}, ensure_ascii=False).encode() + b"\n"
            if len(message) > 65536:
                raise ValueError("Offline request too large")
            self.process.stdin.write(message)
            self.process.stdin.flush()
            deadline = time.monotonic() + timeout
            buffer = b""
            with selectors.DefaultSelector() as selector:
                selector.register(self.process.stdout, selectors.EVENT_READ)
                while b"\n" not in buffer:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TimeoutError("Offline translation timed out")
                    chunk = os.read(self.process.stdout.fileno(), 8192)
                    if not chunk:
                        raise RuntimeError("Offline computation process exited")
                    buffer += chunk
                    if len(buffer) > 65536:
                        raise RuntimeError("Offline response too large")
            value = json.loads(buffer).get("text")
            if not isinstance(value, str) or not value.strip() or len(value.encode()) > 32768:
                raise RuntimeError("Offline translation failed")
            self.last_used = time.monotonic()
            return value.strip().replace("\r", " ").replace("\n", " ")
        except Exception:
            self.close()
            raise


NATIVE = NativeRuntime()


def local_translate(text, cfg, publish=None, current=None, existing=None):
    if cfg.get("translation", "source_language", fallback="auto") not in ("auto", "zh", "zt"):
        raise ValueError("Source language must be auto, zh or zt")
    codes = [item.split(":", 1)[0].strip() for item in cfg["translation"]["languages"].split(",")]
    if not any(code in ("en", "ja") for code in codes):
        raise RuntimeError("Only English and Japanese offline models are bundled")
    timeout = max(2, min(cfg.getfloat("translation", "offline_timeout_seconds", fallback=15), 60))
    english = (existing or {}).get("en") or NATIVE.infer("zh-en", text, timeout)
    result = {}
    if "en" in codes:
        result["en"] = english
        if publish:
            publish(result)
    if "ja" in codes and (current is None or current()):
        result["ja"] = NATIVE.infer("en-ja", english, timeout)
        if publish:
            publish(result)
    return result


def legacy_candidates(include_pip=False, include_argos=False):
    data = Path.home() / ".local/share/rime-llm-translator"
    paths = [(data / "venv", "project private venv")]
    if data.is_dir() and not data.is_symlink():
        paths.extend((p, "project interrupted installation") for p in data.glob("install-*"))
    if include_pip:
        paths.append((Path.home() / ".cache/pip", "SHARED pip cache; installed packages retained"))
    if include_argos:
        root = Path.home() / ".local/share/argos-translate/packages"
        if root.is_dir():
            checked_cleanup_path(root)
            for path in root.iterdir():
                checked_cleanup_path(path)
                metadata = path / "metadata.json"
                if metadata.is_file() and not metadata.is_symlink():
                    try:
                        data = json.loads(metadata.read_text())
                        if (data.get("from_code"), data.get("to_code")) in (("zh", "en"), ("zt", "en"), ("en", "ja")):
                            paths.append((path, "SHARED Argos model; other Argos apps may use it"))
                    except (ValueError, OSError):
                        continue
    return [(p, label) for p, label in paths if p.exists() or p.is_symlink()]


def checked_cleanup_path(path):
    """Reject redirected parents too, before traversing or deleting anything."""
    home = Path.home().absolute()
    path = path.absolute()
    if path == home or not path.is_relative_to(home):
        raise RuntimeError("Refusing cleanup outside the current user's home")
    current = path
    while current != home:
        if current.is_symlink():
            raise RuntimeError("Refusing cleanup through a symlink: " + str(current))
        current = current.parent
    if path.resolve() != path:
        raise RuntimeError("Refusing redirected cleanup path: " + str(path))
    return path


def legacy_size(path):
    total = 0
    if path.is_file():
        return path.stat().st_size
    for directory, _, files in os.walk(path, followlinks=False):
        for name in files:
            file = Path(directory) / name
            if not file.is_symlink():
                total += file.stat().st_size
    return total


def cleanup_legacy(apply=False, include_pip=False, include_argos=False):
    if os.geteuid() == 0:
        raise RuntimeError("Run cleanup-legacy as your desktop user, without sudo")
    paths = legacy_candidates(include_pip, include_argos)
    checked = [(checked_cleanup_path(p), label) for p, label in paths]
    total = 0
    for path, label in checked:
        size = legacy_size(path)
        total += size
        print("%.1f MiB  %s  [%s]" % (size / 1024 ** 2, path, label))
    print("Selected legacy files: %.1f MiB (logical file sizes)." % (total / 1024 ** 2))
    if not apply:
        print("Preview only. Add --apply to delete these selected paths.")
        print("Shared pip cache / Argos models excluded unless --pip-cache / --argos-models is supplied.")
        return
    if not checked:
        print("No selected remnants to remove.")
        return
    check_offline()
    was_active = subprocess.run(["systemctl", "--user", "is-active", "--quiet",
                                 "rime-llm-translator.service"], check=False).returncode == 0
    subprocess.run(["systemctl", "--user", "stop", "rime-llm-translator.service"], check=True)
    try:
        for path, _ in checked:
            checked_cleanup_path(path)
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()
    finally:
        if was_active:
            subprocess.run(["systemctl", "--user", "start", "rime-llm-translator.service"], check=False)
    print("Legacy files removed. Configuration, API key and Rime dictionaries retained.")
