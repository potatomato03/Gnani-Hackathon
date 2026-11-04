"""Optional WebRTC loopback; text and media transport tests run without aiortc."""
import asyncio
import fractions
import io
import math
import queue
import struct
import time
import wave
import pytest
pytest.importorskip("aiortc")
from aiortc import RTCConfiguration, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamTrack
from av import AudioFrame
from fastapi.testclient import TestClient
from voicerx.agent.webrtc_call import WebRtcCall
from voicerx.agent.whatsapp import WhatsAppChannel, GraphClient
from voicerx.followup_api import create_app
from test_whatsapp import FakeGraph, Clock, CONFIG, FakeSpeech, join, post, call_event, PHONE, SECRET
import json

class CallerTrack(MediaStreamTrack):
    """The patient's microphone: 0.8 s of tone, then 1.2 s of quiet, over and over."""
    kind = "audio"

    def __init__(self):
        super().__init__()
        self.rate, self.start, self.sent = 16000, None, 0

    async def recv(self):
        samples = 320
        if self.start is None:
            self.start = time.time()
        else:
            await asyncio.sleep(max(0, self.start + self.sent / self.rate - time.time()))
        position = (self.sent / self.rate) % 2.0
        loud = position < 0.8
        pcm = b"".join(struct.pack("<h", int(6000 * math.sin(2 * math.pi * 440 * (self.sent + i) / self.rate))
                                   if loud else 0) for i in range(samples))
        frame = AudioFrame(format="s16", layout="mono", samples=samples)
        frame.planes[0].update(pcm.ljust(frame.planes[0].buffer_size, b"\x00"))
        frame.pts, frame.sample_rate, frame.time_base = self.sent, self.rate, fractions.Fraction(1, self.rate)
        self.sent += samples
        return frame


class CallSpeech(FakeSpeech):
    def synthesize(self, text, language, voice, container="mp3", sample_rate=24000):
        self.calls.append(("synthesize", text, container))
        buffer = io.BytesIO()
        with wave.open(buffer, "wb") as out:
            out.setnchannels(1)
            out.setsampwidth(2)
            out.setframerate(sample_rate)
            out.writeframes(b"\x01\x00" * int(0.3 * sample_rate))
        return buffer.getvalue()


def test_a_whatsapp_call_is_answered_and_answers_from_the_approved_row(tmp_path):
    answers = queue.Queue()
    graph, clock = FakeGraph(), Clock()
    original = graph.__call__

    def transport(method, url, headers, body):
        status, h, data = original(method, url, headers, body)
        if url.endswith("/calls") and json.loads(body)["action"] == "pre_accept":
            answers.put(json.loads(body)["session"]["sdp"])
        return status, h, data

    speech = CallSpeech("Montair कब लेनी है?")
    channel = WhatsAppChannel(CONFIG, GraphClient(CONFIG, transport=transport), now=clock)
    app = create_app(tmp_path, speech=speech, whatsapp=channel,
                     call_media=lambda sdp: WebRtcCall(sdp, ice_servers=()))
    with TestClient(app) as client:
        conversation_id = join(client)

        async def meta_and_caller():
            pc = RTCPeerConnection(RTCConfiguration(iceServers=[]))
            pc.addTrack(CallerTrack())
            heard = []

            @pc.on("track")
            def on_track(track):
                async def drain():
                    while True:
                        try:
                            heard.append(await track.recv())
                        except Exception:
                            return
                asyncio.ensure_future(drain())

            await pc.setLocalDescription(await pc.createOffer())
            await asyncio.to_thread(post, client, call_event("connect", "wacid.1", pc.localDescription.sdp),
                                    SECRET, "calls")
            answer = await asyncio.to_thread(answers.get, True, 30)
            await pc.setRemoteDescription(RTCSessionDescription(sdp=answer, type="answer"))
            for _ in range(300):
                conv = (await asyncio.to_thread(client.get, f"/conversations/{conversation_id}")).json()
                if any(m["kind"] == "answer" for m in conv["messages"]):
                    break
                await asyncio.sleep(0.1)
            await asyncio.to_thread(post, client, call_event("terminate", "wacid.1"), SECRET, "calls")
            await pc.close()
            return conv, heard

        conv, heard = asyncio.run(meta_and_caller())
    actions = [c["action"] for c in graph.calls]
    assert actions[:2] == ["pre_accept", "accept"]
    assert heard, "the caller heard nothing from the agent"
    texts = [c[1] for c in speech.calls if c[0] == "synthesize"]
    assert texts[0].startswith("नमस्ते") and "AI" in texts[0]
    answer = next(m for m in conv["messages"] if m["kind"] == "answer")
    assert "MONTAIR" in answer["text"] and answer["text"] in texts
    assert "MONTAIR" in graph.texts()[-1]           # the answer is also written in the WhatsApp chat
    assert any(c[0] == "transcribe" for c in speech.calls)
    for path in tmp_path.rglob("*"):
        assert not (path.is_file() and PHONE.encode() in path.read_bytes())
