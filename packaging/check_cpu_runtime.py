#!/usr/bin/python3
"""Check the installed CPU-only runtime without downloading language models."""
import importlib.metadata as metadata
import os

gpu_packages = sorted(dist.metadata.get("Name", "") for dist in metadata.distributions()
                      if dist.metadata.get("Name", "").lower().replace("_", "-").startswith(
                          ("nvidia-", "cuda-", "triton")))
if gpu_packages:
    raise SystemExit("Unexpected GPU dependencies remain: " + ", ".join(gpu_packages) +
                     ". Run rime-llm-translator repair-offline to rebuild the private environment.")
if metadata.version("torch") != "2.8.0+cpu":
    raise SystemExit("Expected the pinned CPU-only torch wheel")
if metadata.version("argostranslate") != "1.11.0":
    raise SystemExit("Expected the pinned Argos Translate version")
os.environ["ARGOS_DEVICE_TYPE"] = "cpu"
os.environ["ARGOS_CHUNK_TYPE"] = "DEFAULT"
import torch
assert torch.version.cuda is None, "torch contains CUDA support"
from argostranslate import package, translate
print("PASS: CPU torch and Argos imports; no CUDA/NVIDIA/Triton packages installed.")
