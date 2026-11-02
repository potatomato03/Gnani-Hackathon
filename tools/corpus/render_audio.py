"""Render case scripts to 16 kHz mono WAV with Gemini TTS.

Clips already rendered are kept, so a run can stop and resume. From the repo root:

    ../.venv/Scripts/python tools/corpus/render_audio.py
"""

import base64
import csv
import hashlib
import io
import json
import math
import re
import sys
import time
import urllib.error
import urllib.request
import wave
from pathlib import Path

import av
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
AUDIO_DIR = REPO_ROOT / "data" / "eval" / "audio" / "gemini"
INDEX_PATH = REPO_ROOT / "data" / "eval" / "audio_index.csv"
URL = "https://generativelanguage.googleapis.com/v1beta/interactions"
# Each model has its own free daily allowance. When one runs out, the next is used,
# and the index records which model made each clip. gemini-3.1-flash-tts-preview is
# left out because it rejects the style hint every request sends.
MODELS = ["gemini-3.8-flash-tts", "gemini-3.8-flash-lite-tts"]
TARGET_RATE = 16000
AUDIO_FORMAT = "wav_pcm16_16000_mono"
PAUSE_SECONDS = 5
MAX_ATTEMPTS = 6
DOCTOR_VOICES = {"doc-001": "Charon", "doc-002": "Fenrir", "doc-003": "Kore"}
PATIENT_VOICE = "Aoede"
STYLES = {
    "doctor": "a doctor dictating clinic notes, calm and quick",
    "patient": "a patient interrupting from across the room",
}
INDEX_FIELDS = [
    "case_id", "source", "model", "voice", "audio_format",
    "duration_s", "audio_hash", "script_hash",
]


class DailyLimitReached(Exception):
    pass


def voices_for(doctor_id):
    return {"doctor": DOCTOR_VOICES[doctor_id], "patient": PATIENT_VOICE}


def build_request(lines, voices, model=MODELS[0]):
    speakers = list(dict.fromkeys(speaker for speaker, _ in lines))
    if len(speakers) > 2:
        raise ValueError(f"Gemini renders at most two speakers, got {speakers}")
    if len(speakers) == 1:
        speaker = speakers[0]
        content = [
            {
                "type": "text",
                "text": " ".join(text for _, text in lines),
                "annotations": [{"type": "speech_metadata", "style": STYLES[speaker]}],
            }
        ]
        speech_config = [{"voice": voices[speaker]}]
    else:
        content = [
            {
                "type": "text",
                "text": text,
                "annotations": [{"type": "speech_metadata", "speaker": speaker, "style": STYLES[speaker]}],
            }
            for speaker, text in lines
        ]
        speech_config = {"speakers": [{"speaker": speaker, "voice": voices[speaker]} for speaker in speakers]}
    return {
        "model": model,
        "input": [{"type": "user_input", "content": content}],
        "response_format": {"type": "audio", "sample_rate": TARGET_RATE},
        "generation_config": {"speech_config": speech_config},
    }


def find_audio(node):
    if isinstance(node, dict):
        if node.get("type") == "audio" and "data" in node:
            return base64.b64decode(node["data"])
        node = list(node.values())
    if isinstance(node, list):
        for item in node:
            found = find_audio(item)
            if found:
                return found
    return None


def to_16k(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as clip:
        if (clip.getframerate(), clip.getnchannels(), clip.getsampwidth()) == (TARGET_RATE, 1, 2):
            return wav_bytes
    resampler = av.AudioResampler(format="s16", layout="mono", rate=TARGET_RATE)
    samples = bytearray()
    with av.open(io.BytesIO(wav_bytes)) as container:
        for frame in container.decode(audio=0):
            for converted in resampler.resample(frame):
                samples += converted.to_ndarray().tobytes()
    for converted in resampler.resample(None):
        samples += converted.to_ndarray().tobytes()
    output = io.BytesIO()
    with wave.open(output, "wb") as clip:
        clip.setnchannels(1)
        clip.setsampwidth(2)
        clip.setframerate(TARGET_RATE)
        clip.writeframes(bytes(samples))
    return output.getvalue()


def retry_delay(body, default, retry_after=None):
    match = re.search(r'"retryDelay"\s*:\s*"([\d.]+)s"', body)
    if match:
        return math.ceil(float(match[1])) + 1
    if retry_after and retry_after.strip().isdigit():
        return int(retry_after) + 1
    return default


def is_daily_limit(body):
    return "PerDay" in body or re.search(r"per day", body, re.IGNORECASE) is not None


def next_model(models, exhausted):
    return next((model for model in models if model not in exhausted), None)


def script_hash(lines):
    text = "\n".join(f"[{speaker}] {line}" for speaker, line in lines)
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def cases_from_family(family):
    return [
        {
            "case_id": variant["variant_id"],
            "doctor_id": encounter["doctor_id"],
            "language": family["language"],
            "lines": [(item["speaker"], item["text"]) for item in variant["utterances"]],
        }
        for encounter in family["encounters"]
        for variant in encounter["variants"]
    ]


def pending(cases, index, on_disk):
    def current(case):
        row = index.get(case["case_id"])
        same = row is not None and row["script_hash"] == script_hash(case["lines"])
        return same and case["case_id"] in on_disk

    return [case for case in cases if not current(case)]


def request_audio(body, key):
    request = urllib.request.Request(
        URL,
        data=json.dumps(body, ensure_ascii=False).encode("utf-8"),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
        method="POST",
    )
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(request, timeout=240) as response:
                audio = find_audio(json.load(response))
            if audio:
                return audio
            print(f"  attempt {attempt}: reply had no audio", flush=True)
            time.sleep(10 * attempt)
        except urllib.error.HTTPError as error:
            message = error.read().decode("utf-8", "replace").replace(key, "<key>")
            if error.code == 429 and is_daily_limit(message):
                raise DailyLimitReached(message[:400]) from error
            if error.code not in {429, 500, 502, 503, 504}:
                raise RuntimeError(f"HTTP {error.code}: {message[:400]}") from error
            wait = retry_delay(message, default=20 * attempt, retry_after=error.headers.get("Retry-After"))
            print(f"  attempt {attempt}: HTTP {error.code}, waiting {wait}s: {message[:160]}", flush=True)
            time.sleep(wait)
        except (urllib.error.URLError, TimeoutError) as error:
            print(f"  attempt {attempt}: {type(error).__name__}, waiting", flush=True)
            time.sleep(20 * attempt)
    raise RuntimeError(f"no audio after {MAX_ATTEMPTS} attempts")


def read_key(root):
    for line in (root / ".env").read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("GEMINI_API_KEY is not set in .env")


def read_index():
    if not INDEX_PATH.exists():
        return {}
    with INDEX_PATH.open(encoding="utf-8", newline="") as handle:
        return {row["case_id"]: row for row in csv.DictReader(handle)}


def write_index(index):
    with INDEX_PATH.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=INDEX_FIELDS, lineterminator="\n")
        writer.writeheader()
        writer.writerows(index[case_id] for case_id in sorted(index))


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    key = read_key(REPO_ROOT)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    cases = []
    for path in sorted((REPO_ROOT / "data" / "eval" / "cases").glob("*.yaml")):
        cases += cases_from_family(yaml.safe_load(path.read_text(encoding="utf-8")))
    index = read_index()
    on_disk = {path.stem for path in AUDIO_DIR.glob("*.wav")}
    todo = pending(cases, index, on_disk)
    print(f"{len(cases)} scripts, {len(todo)} to render", flush=True)

    exhausted = set()
    for number, case in enumerate(todo, start=1):
        case_id = case["case_id"]
        path = AUDIO_DIR / f"{case_id}.wav"
        voices = voices_for(case["doctor_id"])
        speakers = list(dict.fromkeys(speaker for speaker, _ in case["lines"]))
        started = time.time()
        reuse = path.exists() and case_id not in index
        model = MODELS[0]
        raw = path.read_bytes() if reuse else None
        while raw is None:
            model = next_model(MODELS, exhausted)
            if model is None:
                print(f"every model's daily limit is used up. {number - 1} of {len(todo)} done. Run again tomorrow.", flush=True)
                return 3
            try:
                raw = request_audio(build_request(case["lines"], voices, model), key)
            except DailyLimitReached as limit:
                exhausted.add(model)
                print(f"  {model} reached its daily limit, switching: {str(limit)[:160]}", flush=True)
        audio = to_16k(raw)
        path.write_bytes(audio)
        with wave.open(str(path)) as clip:
            duration = clip.getnframes() / clip.getframerate()
        index[case_id] = {
            "case_id": case_id,
            "source": "gemini",
            "model": model,
            "voice": "+".join(voices[speaker] for speaker in speakers),
            "audio_format": AUDIO_FORMAT,
            "duration_s": f"{duration:.2f}",
            "audio_hash": hashlib.sha256(audio).hexdigest(),
            "script_hash": script_hash(case["lines"]),
        }
        write_index(index)
        print(f"[{number}/{len(todo)}] {case_id}: {duration:.1f}s audio in {time.time() - started:.0f}s"
              f" from {model}{' (reused)' if reuse else ''}", flush=True)
        if not reuse:
            time.sleep(PAUSE_SECONDS)
    print(f"finished. {len(index)} clips in the index", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
