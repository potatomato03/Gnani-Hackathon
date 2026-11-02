"""Transcribe rendered clips with Whisper on the local GPU.

These are Whisper's results, not Prisma's. They show that the audio path works,
and say nothing about Prisma's accuracy. From the repo root:

    ../.venv/Scripts/python tools/corpus/transcribe_audio.py

Whisper stops a decode at 224 tokens. Dense Devanagari passes that within about
20 seconds, and the rest of the window is dropped silently. So speech is split
into chunks of at most 10 seconds and each chunk is decoded on its own.
"""

import csv
import os
import sys
import time
from pathlib import Path

import yaml

from render_audio import cases_from_family

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "data" / "eval" / "audio" / "gemini"
OUTPUT_DIR = REPO_ROOT / "data" / "eval" / "results" / "whisper"
DEFAULT_MODEL = REPO_ROOT.parent / "models" / "faster-whisper-large-v3"
LANGUAGE_CODES = {"english": "en", "hindi": "hi", "hinglish": "hi", "tamil": "ta", "telugu": "te"}
SUMMARY_FIELDS = ["case_id", "language", "audio_s", "took_s", "segments", "words", "script_words", "truncated"]
CHUNK_SECONDS = 10
TOKEN_CAP = 224


def looks_truncated(token_counts, text):
    return "�" in text or any(count >= TOKEN_CAP - 4 for count in token_counts)


def add_gpu_libraries():
    """Put NVIDIA's CUDA 12 libraries on PATH. Windows needs this before faster-whisper loads."""
    site = Path(sys.prefix) / "Lib" / "site-packages" / "nvidia"
    for part in ("cublas", "cudnn"):
        os.environ["PATH"] = str(site / part / "bin") + os.pathsep + os.environ["PATH"]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    add_gpu_libraries()
    from faster_whisper import BatchedInferencePipeline, WhisperModel

    cases = []
    for path in sorted((REPO_ROOT / "data" / "eval" / "cases").glob("*.yaml")):
        cases += cases_from_family(yaml.safe_load(path.read_text(encoding="utf-8")))
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    model = WhisperModel(os.environ.get("WHISPER_MODEL_DIR", str(DEFAULT_MODEL)), device="cuda", compute_type="int8_float16")
    pipeline = BatchedInferencePipeline(model)

    rows = []
    for case in cases:
        audio = AUDIO_DIR / f"{case['case_id']}.wav"
        if not audio.exists():
            print(f"missing audio for {case['case_id']}", flush=True)
            continue
        started = time.time()
        segments, info = pipeline.transcribe(
            str(audio),
            language=LANGUAGE_CODES[case["language"]],
            beam_size=5,
            batch_size=4,
            chunk_length=CHUNK_SECONDS,
        )
        segments = list(segments)
        parts = [segment.text.strip() for segment in segments]
        took = time.time() - started
        text = " ".join(parts)
        truncated = looks_truncated([len(segment.tokens) for segment in segments], text)
        (OUTPUT_DIR / f"{case['case_id']}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
        rows.append(
            {
                "case_id": case["case_id"],
                "language": case["language"],
                "audio_s": f"{info.duration:.1f}",
                "took_s": f"{took:.1f}",
                "segments": len(parts),
                "words": len(text.split()),
                "script_words": sum(len(line.split()) for _, line in case["lines"]),
                "truncated": truncated,
            }
        )
        flag = " TRUNCATED" if truncated else ""
        print(f"{case['case_id']}: {info.duration:.1f}s audio in {took:.1f}s{flag}", flush=True)
    with (OUTPUT_DIR / "summary.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(rows)
    print(f"transcribed {len(rows)} clips", flush=True)


if __name__ == "__main__":
    main()
