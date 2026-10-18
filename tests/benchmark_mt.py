#!/usr/bin/python3
"""Real packaged model smoke/latency/memory tests; public synthetic inputs only."""
import hashlib
import json
import math
import os
from pathlib import Path
import platform
import resource
import subprocess
import sys
import threading
import time

sys.path.insert(0, "/usr/share/rime-llm-translator")
import rime_mt as mt

CASES = ["你好", "你", "謝謝你的幫助。", "我明天上午十点到学校。",
         "不要删除这个文件。", "价格是二十五元，一共三个。", "我正在使用 Ubuntu 输入中文。",
         "今天下雨，请带上雨伞。", "请问车站在哪里？", "这个程序运行在虚拟机中。",
         "我们可以下周再讨论这个问题。", "我不喜欢太甜的咖啡。", "他昨天没有参加会议。",
         "請把這份文件寄給老師。", "电脑只有两个处理器核心和四 GB 内存。",
         "把温度保持在二十度左右。", "我已经保存了修改。", "请稍等，我正在检查网络。",
         "北京和上海之间有高速铁路。", "如果没有时间，我们明天再见。"]


def memory(pid):
    try:
        values = {}
        for line in Path(f"/proc/{pid}/status").read_text().splitlines():
            if line.startswith(("VmRSS:", "VmHWM:", "Threads:")):
                name, value, *_ = line.split()
                values[name.rstrip(":")] = int(value)
        pss = sum(int(line.split()[1]) for line in Path(f"/proc/{pid}/smaps_rollup").read_text().splitlines()
                  if line.startswith("Pss:"))
        values["Pss"] = pss
        return values
    except (FileNotFoundError, ProcessLookupError):
        return {}


def main():
    mt.check_offline()
    runtime = mt.NativeRuntime()
    peaks = {"english_rss_kib": 0, "both_rss_kib": 0, "parent_rss_kib": 0,
             "child_pss_kib": 0, "threads": 0}
    stage = ["english"]
    stop = threading.Event()

    def sample():
        while not stop.wait(.01):
            parent = memory(os.getpid())
            peaks["parent_rss_kib"] = max(peaks["parent_rss_kib"], parent.get("VmRSS", 0))
            process = runtime.process
            if process:
                child = memory(process.pid)
                key = stage[0] + "_rss_kib"
                peaks[key] = max(peaks[key], child.get("VmRSS", 0) + parent.get("VmRSS", 0))
                peaks["child_pss_kib"] = max(peaks["child_pss_kib"], child.get("Pss", 0))
                peaks["threads"] = max(peaks["threads"], child.get("Threads", 0))
    monitor = threading.Thread(target=sample)
    monitor.start()
    started = time.monotonic()
    cold = runtime.infer("zh-en", CASES[0])
    cold_ms = (time.monotonic() - started) * 1000
    english = []
    for source in CASES:
        started = time.monotonic()
        output = runtime.infer("zh-en", source)
        english.append({"source": source, "english": output, "ms": (time.monotonic() - started) * 1000})
    stage[0] = "both"
    runtime.infer("en-ja", "Hello, how are you?")
    rows = []
    try:
        for source in CASES:
            started = time.monotonic()
            en = runtime.infer("zh-en", source)
            en_ms = (time.monotonic() - started) * 1000
            ja = runtime.infer("en-ja", en)
            total_ms = (time.monotonic() - started) * 1000
            assert en.strip() and ja.strip() and len(en.encode()) <= 32768 and len(ja.encode()) <= 32768
            rows.append({"source": source, "english": en, "japanese": ja,
                         "english_ms": en_ms, "both_ms": total_ms})
        # Long input must run through token-budget splitting and retain a final marker.
        long_source = "这是一个测试句子。" * 30 + "最后的数字是 9876。"
        assert len(long_source.encode()) <= 1200
        long_en = runtime.infer("zh-en", long_source, timeout=60)
        assert "9876" in long_en, "long translation silently dropped its final sentence"
        # A real idle interval demonstrates that weights are returned to the OS.
        process = runtime.process
        runtime.last_used = time.monotonic()
        time.sleep(60.1)
        runtime.reap_idle(60)
        assert runtime.process is None and process.poll() is not None
    finally:
        runtime.close()
        stop.set()
        monitor.join()
    p95 = lambda values: sorted(values)[math.ceil(len(values) * .95) - 1]
    report = {"cpu": next(line.split(":", 1)[1].strip() for line in Path("/proc/cpuinfo").read_text().splitlines()
                          if line.startswith("model name")),
              "platform": platform.platform(), "allowed_cpu_count": len(os.sched_getaffinity(0)),
              "engine_revision": mt.revision(), "cold_english_ms": cold_ms,
              "english_p95_ms": p95([r["ms"] for r in english]),
              "both_p95_ms": p95([r["both_ms"] for r in rows]), "memory": peaks,
              "idle_parent_rss_kib": memory(os.getpid()).get("VmRSS"),
              "child_cpu_seconds": resource.getrusage(resource.RUSAGE_CHILDREN).ru_utime,
              "long_english": long_en, "samples": rows, "cold_output": cold}
    dist = Path("dist")
    dist.mkdir(exist_ok=True)
    (dist / "mt-benchmark.json").write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    # Count all installed project files (including source archives and small entrypoints).
    paths = subprocess.check_output(["dpkg-query", "-L", "rime-llm-translator"]).decode().splitlines()
    project_bytes = sum(Path(p).stat().st_size for p in paths if Path(p).is_file() and not Path(p).is_symlink())
    deb_bytes = sum(p.stat().st_size for p in dist.glob("*.deb"))
    text = ("# Lightweight MT resource report\n\n"
        "Real packaged models; network disabled; one logical CPU selected by taskset. "
        "These are GitHub runner measurements, not the user's VM measurements. "
        "No cloud API was called. Quality still requires human acceptance.\n\n"
        f"- CPU: {report['cpu']}\n- Engine/model identity: `{mt.revision()}`\n"
        f"- Deb: {deb_bytes / 1024**2:.1f} MiB\n"
        f"- Project installed files (logical size): {project_bytes / 1024**2:.1f} MiB\n"
        f"- Cold English: {cold_ms:.0f} ms\n"
        f"- Warm English p95 (20 inputs): {report['english_p95_ms']:.0f} ms\n"
        f"- Warm English + Japanese p95: {report['both_p95_ms']:.0f} ms\n"
        f"- English process tree sampled RSS peak: {peaks['english_rss_kib']/1024:.1f} MiB\n"
        f"- Both models process tree sampled RSS peak: {peaks['both_rss_kib']/1024:.1f} MiB\n"
        f"- Native child sampled PSS peak: {peaks['child_pss_kib']/1024:.1f} MiB\n"
        f"- Native child maximum observed thread count: {peaks['threads']}\n"
        f"- After 60 seconds idle: child exited; parent RSS {report['idle_parent_rss_kib']/1024:.1f} MiB\n\n"
        "RSS is sampled every 10 ms and summed across parent and child; shared pages can be counted twice. "
        "The benchmark parent includes measurement code, not the separate AI worker or IBus/Rime. "
        "Source and translated public samples are in mt-benchmark.json. "
        "System dependency sizes and apt transaction logs are separate from project files.\n")
    (dist / "RESOURCE_REPORT.md").write_text(text)
    print(text)
    assert deb_bytes <= 120 * 1024**2, "deb exceeds planned size budget"
    assert project_bytes <= 250 * 1024**2, "installed project exceeds size budget"
    assert peaks["english_rss_kib"] <= 200 * 1024, "English memory exceeds budget"
    assert peaks["both_rss_kib"] <= 350 * 1024, "two-model memory exceeds budget"
    assert report["english_p95_ms"] <= 1500, "English short-input latency exceeds budget"
    assert report["both_p95_ms"] <= 3000, "two-language latency exceeds budget"


if __name__ == "__main__":
    main()
