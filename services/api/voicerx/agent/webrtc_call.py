"""WebRTC media for a WhatsApp call, with aiortc (runbook D-114).

Meta's Calling API sends the caller's SDP offer in the `connect` webhook. We answer with our SDP through
POST /{phone_number_id}/calls (pre_accept, then accept once connected). Media is ICE + DTLS + SRTP with Opus,
straight between this machine and Meta over UDP: the tunnel carries only the signalling.

Incoming audio is resampled to 16 kHz mono for voice-activity detection and held in memory only. Outgoing
speech is queued as 20 ms frames, with silence in between so the stream never stalls.
"""
import asyncio
import fractions
import io
import time
import wave

from aiortc import RTCConfiguration, RTCIceServer, RTCPeerConnection, RTCSessionDescription
from aiortc.mediastreams import MediaStreamError, MediaStreamTrack
from av import AudioFrame, AudioResampler

from .call import RATE, Utterances

PTIME = 0.02
STUN = 'stun:stun.l.google.com:19302'


class SpeakerTrack(MediaStreamTrack):
    """Our side of the call: plays queued PCM in real time, and silence when there's nothing to say."""

    kind = 'audio'

    def __init__(self):
        super().__init__()
        self.rate = 24000
        self._queue = bytearray()
        self._drained = asyncio.Event()
        self._drained.set()
        self._start = None
        self._timestamp = 0

    def play(self, pcm: bytes, rate: int):
        if rate != self.rate:
            self._queue.clear()
            self.rate, self._start, self._timestamp = rate, None, 0
        self._queue.extend(pcm)
        self._drained.clear()

    async def played(self):
        await self._drained.wait()

    async def recv(self):
        if self.readyState != 'live':
            raise MediaStreamError
        samples = int(PTIME * self.rate)
        if self._start is None:
            self._start, self._timestamp = time.time(), 0
        else:
            self._timestamp += samples
            await asyncio.sleep(max(0.0, self._start + self._timestamp / self.rate - time.time()))
        size = samples * 2
        chunk, self._queue[:size] = bytes(self._queue[:size]), b''
        if not self._queue:
            self._drained.set()
        frame = AudioFrame(format='s16', layout='mono', samples=samples)
        frame.planes[0].update(chunk.ljust(frame.planes[0].buffer_size, b'\x00'))
        frame.pts, frame.sample_rate, frame.time_base = self._timestamp, self.rate, fractions.Fraction(1, self.rate)
        return frame


class WebRtcCall:
    """CallAudio over aiortc. answer() gives the SDP for pre_accept and accept."""

    def __init__(self, offer_sdp: str, ice_servers=(STUN,), vad: Utterances | None = None):
        config = RTCConfiguration(iceServers=[RTCIceServer(urls=url) for url in ice_servers])
        self.pc = RTCPeerConnection(configuration=config)
        self.offer = offer_sdp
        self.speaker = SpeakerTrack()
        self.pc.addTrack(self.speaker)
        self.vad = vad or Utterances()
        self.hung_up = False
        self._listening = False
        self._heard: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._connected = asyncio.Event()
        self._readers = []

        @self.pc.on('track')
        def on_track(track):
            if track.kind == 'audio':
                self._readers.append(asyncio.ensure_future(self._read(track)))

        @self.pc.on('connectionstatechange')
        async def on_state():
            if self.pc.connectionState == 'connected':
                self._connected.set()
            elif self.pc.connectionState in ('failed', 'closed'):
                self.hang_up()

    async def answer(self) -> str:
        await self.pc.setRemoteDescription(RTCSessionDescription(sdp=self.offer, type='offer'))
        await self.pc.setLocalDescription(await self.pc.createAnswer())   # aiortc gathers ICE here
        return self.pc.localDescription.sdp

    async def connected(self, timeout=20.0):
        await asyncio.wait_for(self._connected.wait(), timeout)

    async def _read(self, track):
        resampler = AudioResampler(format='s16', layout='mono', rate=RATE)
        while not self.hung_up:
            try:
                frame = await track.recv()
            except MediaStreamError:
                self.hang_up()
                return
            if not self._listening:
                continue
            for mono in resampler.resample(frame):
                utterance = self.vad.feed(bytes(mono.planes[0])[:mono.samples * 2])
                if utterance is not None and self._listening:
                    self._listening = False
                    self._heard.put_nowait(utterance)

    async def listen(self, timeout: float) -> bytes | None:
        if self.hung_up:
            return None
        while not self._heard.empty():
            self._heard.get_nowait()
        self.vad.reset()
        self._listening = True
        try:
            return await asyncio.wait_for(self._heard.get(), timeout)
        except asyncio.TimeoutError:
            return None
        finally:
            self._listening = False

    async def speak(self, wav_bytes: bytes):
        with wave.open(io.BytesIO(wav_bytes)) as clip:
            if clip.getsampwidth() != 2 or clip.getnchannels() != 1:
                raise ValueError('call speech must be 16-bit mono WAV')
            rate, pcm = clip.getframerate(), clip.readframes(clip.getnframes())
        self.speaker.play(pcm, rate)
        while not self.hung_up:
            try:
                await asyncio.wait_for(self.speaker.played(), 0.5)
                return
            except asyncio.TimeoutError:
                continue

    def hang_up(self):
        self.hung_up = True
        self._heard.put_nowait(None)

    async def close(self):
        self.hang_up()
        for reader in self._readers:
            reader.cancel()
        await self.pc.close()
