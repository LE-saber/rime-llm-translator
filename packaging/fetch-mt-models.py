#!/usr/bin/env python3
"""Build-time only: fetch hash-pinned models, never invoked on user install."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import shutil
from urllib.request import urlopen

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / "native/mt/models.lock.json"
REGISTRY = "https://storage.googleapis.com/moz-fx-translations-data--303e-prod-translations-data/db/models.json"
SELECTED = {"zh-en": "cjk_icu_CQYVbMd3R5mtPx9PhXbNCA",
            "en-ja": "llmaat_finetune10M_qe8_f2_ApiGGQIwTKuF9i_k3n9Q2Q"}

def digest(path):
    with path.open("rb") as fp:
        return hashlib.file_digest(fp, "sha256").hexdigest()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--lock", action="store_true", help="Developer-only initial lock creation")
    args = ap.parse_args()
    if args.lock:
        with urlopen(REGISTRY, timeout=60) as fp:
            registry = json.load(fp)
        lock = {"registry": REGISTRY, "generated": registry["generated"], "models": {}}
        for direction, name in SELECTED.items():
            selected = next(m for m in registry["models"][direction]
                            if name in m["files"]["model"]["path"])
            lock["models"][direction] = {"name": name, "releaseStatus": selected["releaseStatus"],
                                         "files": selected["files"]}
            for asset in selected["files"].values():
                asset["url"] = registry["baseUrl"] + "/" + asset.pop("path")
    else:
        lock = json.loads(LOCK.read_text())
    for direction, model in lock["models"].items():
        directory = ROOT / ".build/models" / direction
        directory.mkdir(parents=True, exist_ok=True)
        for asset in model["files"].values():
            name = asset["url"].rsplit("/", 1)[1]
            archive = directory / name
            output = directory / name.removesuffix(".gz")
            if args.lock or not archive.exists() or digest(archive) != asset["sha256"]:
                with urlopen(asset["url"], timeout=120) as fp, archive.open("wb") as out:
                    shutil.copyfileobj(fp, out)
            archive_hash = digest(archive)
            if not args.lock and archive_hash != asset["sha256"]:
                raise RuntimeError("Model download checksum mismatch: " + name)
            with gzip.open(archive, "rb") as fp, output.open("wb") as out:
                shutil.copyfileobj(fp, out)
            raw_hash = digest(output)
            if "uncompressedHash" in asset and raw_hash != asset["uncompressedHash"]:
                raise RuntimeError("Uncompressed model checksum mismatch: " + name)
            if "uncompressedSize" in asset and output.stat().st_size != asset["uncompressedSize"]:
                raise RuntimeError("Uncompressed model size mismatch: " + name)
            asset.update(sha256=archive_hash, compressedSize=archive.stat().st_size,
                         uncompressedHash=raw_hash, uncompressedSize=output.stat().st_size,
                         filename=output.name)
        files = model["files"]
        vocab = files.get("vocab", files.get("srcVocab"))["filename"]
        trg = files.get("vocab", files.get("trgVocab"))["filename"]
        # Relative paths are resolved by Bergamot against the config path.
        config = ("models: [" + files["model"]["filename"] + "]\n"
                  "vocabs: [" + vocab + ", " + trg + "]\n"
                  "shortlist: [" + files["lexicalShortlist"]["filename"] + ", false]\n"
                  "beam-size: 1\nnormalize: 1.0\nword-penalty: 0\n"
                  "max-length-break: 64\nmini-batch-words: 192\nmaxi-batch: 1\n"
                  "workspace: 32\ncpu-threads: 1\nssplit-mode: sentence\n"
                  "gemm-precision: int8shiftAll\nskip-cost: true\nquiet: true\nquiet-translation: true\n")
        (directory / "config.yml").write_text(config)
    if args.lock:
        LOCK.write_text(json.dumps(lock, indent=2) + "\n")
    print("Verified all model assets.")

if __name__ == "__main__":
    main()
