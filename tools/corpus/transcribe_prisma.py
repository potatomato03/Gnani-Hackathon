"""Transcribe rendered clips with Gnani Prisma v3.0, with or without formulary keyterms.

Gnani's EULA restricts publishing accuracy results, so transcripts go to a
git-ignored folder (data/eval/results/prisma*/). From the repo root:

    ../.venv/Scripts/python tools/corpus/transcribe_prisma.py fam-001-a fam-005-a
    ../.venv/Scripts/python tools/corpus/transcribe_prisma.py --keyterms fam-001-a fam-005-a

Gemini renders at 24 kHz, so each clip is resampled to 16 kHz mono first.
The REST endpoint takes at most 30 seconds of audio per request.
"""

import argparse
import csv
import io
import json
import sys
import time
import urllib.error
import urllib.request
import uuid
import wave
from pathlib import Path

import numpy
import yaml

from render_audio import cases_from_family

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "data" / "eval" / "audio" / "gemini"
URL = "https://api.vachana.ai/stt/v3"
LANGUAGE_CODES = {"english": "en-IN", "hindi": "hi-IN", "hinglish": "hi-IN,en-IN", "tamil": "ta-IN", "telugu": "te-IN"}
MAX_SECONDS = 30
MAX_KEYTERMS = 200
SUMMARY_FIELDS = ["case_id", "language", "audio_s", "took_s", "keyterms", "status", "words", "truncated"]


def read_key(env_path):
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("GNANI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GNANI_API_KEY is not set in .env")


def formulary_keyterms():
    """Brand names and aliases from the formulary only, so no test answer leaks in (runbook D-13)."""
    terms = []
    with (REPO_ROOT / "data" / "formulary" / "products.csv").open(encoding="utf-8") as handle:
        for row in csv.DictReader(handle):
            for term in [row["brand"], *row["aliases"].split(";")]:
                if term.strip() and term.strip() not in terms:
                    terms.append(term.strip())
    return terms[:MAX_KEYTERMS]


def wav_16k(path):
    from faster_whisper import decode_audio

    samples = decode_audio(str(path), sampling_rate=16000)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as out:
        out.setnchannels(1)
        out.setsampwidth(2)
        out.setframerate(16000)
        out.writeframes((numpy.clip(samples, -1, 1) * 32767).astype("<i2").tobytes())
    return buffer.getvalue(), len(samples) / 16000


def multipart(fields, audio):
    boundary = uuid.uuid4().hex
    parts = []
    for name, value in fields.items():
        parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n{value}\r\n'.encode("utf-8"))
    parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="audio_file"; filename="clip.wav"\r\n'
                 "Content-Type: audio/wav\r\n\r\n".encode("utf-8") + audio + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode("utf-8"))
    return b"".join(parts), "multipart/form-data; boundary=" + boundary


def transcribe(key, audio, fields):
    body, content_type = multipart(fields, audio)
    request = urllib.request.Request(URL, data=body, method="POST", headers={
        "X-API-Key-ID": key, "Content-Type": content_type, "User-Agent": "voicerx"})
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return response.status, json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as error:
        return error.code, {"error": error.read().decode("utf-8", "replace")[:500]}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case_ids", nargs="+")
    parser.add_argument("--keyterms", action="store_true", help="send the formulary brand names as keyterms")
    parser.add_argument("--format", default="codemix", choices=["codemix", "verbatim", "transcribe", "transliterate"])
    args = parser.parse_args()

    key = read_key(REPO_ROOT / ".env")
    cases = {}
    for path in sorted((REPO_ROOT / "data" / "eval" / "cases").glob("*.yaml")):
        for case in cases_from_family(yaml.safe_load(path.read_text(encoding="utf-8"))):
            cases[case["case_id"]] = case
    terms = formulary_keyterms() if args.keyterms else []
    output_dir = REPO_ROOT / "data" / "eval" / "results" / ("prisma-keyterms" if args.keyterms else "prisma")
    output_dir.mkdir(parents=True, exist_ok=True)

    rows = []
    for case_id in args.case_ids:
        case = cases[case_id]
        audio, seconds = wav_16k(AUDIO_DIR / f"{case_id}.wav")
        if seconds > MAX_SECONDS:
            print(f"{case_id}: {seconds:.1f}s is over the {MAX_SECONDS}s REST limit, skipped", flush=True)
            continue
        fields = {"model": "prisma-v3.0", "language_code": LANGUAGE_CODES[case["language"]], "format": args.format}
        if terms:
            fields["keyterms"] = json.dumps(terms, ensure_ascii=False)
        started = time.time()
        status, reply = transcribe(key, audio, fields)
        took = time.time() - started
        text = reply.get("transcript", "") if status == 200 else ""
        if status == 200:
            (output_dir / f"{case_id}.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
        rows.append({"case_id": case_id, "language": case["language"], "audio_s": f"{seconds:.1f}",
                     "took_s": f"{took:.1f}", "keyterms": len(terms), "status": status,
                     "words": len(text.split()), "truncated": bool(reply.get("truncated"))})
        print(f"{case_id}: HTTP {status} in {took:.1f}s" + ("" if status == 200 else f" {reply.get('error')}"), flush=True)
    summary = output_dir / "summary.csv"
    previous = {r["case_id"]: r for r in csv.DictReader(summary.open(encoding="utf-8"))} if summary.exists() else {}
    previous.update({r["case_id"]: r for r in rows})
    with summary.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(previous[k] for k in sorted(previous))


if __name__ == "__main__":
    main()
