"""LiveKit adapter (experimental).

Joins a LiveKit room as a participant, publishes the scripted user audio as a
microphone track, and records every remote audio track as agent audio. It can
dispatch a named LiveKit Agents worker into the room before the session starts.

Requires ``pip install 'voicebench[livekit]'``. Credentials come from options or
from the ``LIVEKIT_URL``, ``LIVEKIT_API_KEY``, and ``LIVEKIT_API_SECRET``
environment variables, and never appear in the report.

Limitations: LiveKit does not send an explicit "clear" on interruption, so
barge-in timing comes from the audio the agent stops sending. Received timing
includes the jitter buffer of the LiveKit client SDK.
"""

from __future__ import annotations

import asyncio
import contextlib
import os
import uuid
from typing import Any, ClassVar

import numpy as np

from voicebench import audio as au
from voicebench.adapters.base import Adapter, AdapterError, AgentAudio, Role, Transcript

try:
    from livekit import api, rtc
except ImportError as exc:  # pragma: no cover - exercised only without the extra
    raise ImportError("the livekit adapter needs the 'livekit' and 'livekit-api' packages") from exc


class LiveKitAdapter(Adapter):
    """Talks to an agent through a LiveKit room. Runs on the real clock."""

    name: ClassVar[str] = "livekit"

    def __init__(
        self,
        url: str | None = None,
        api_key: str | None = None,
        api_secret: str | None = None,
        room: str | None = None,
        agent_name: str | None = None,
        identity: str = "voicebench",
        wait_for_agent_s: float = 20.0,
        **options: Any,
    ) -> None:
        super().__init__(**options)
        self.url = url or os.environ.get("LIVEKIT_URL", "")
        self._api_key = api_key or os.environ.get("LIVEKIT_API_KEY", "")
        self._api_secret = api_secret or os.environ.get("LIVEKIT_API_SECRET", "")
        self.room_name = room or f"voicebench-{uuid.uuid4().hex[:8]}"
        self.agent_name = agent_name
        self.identity = identity
        self.wait_for_agent_s = wait_for_agent_s
        self._room: rtc.Room | None = None
        self._source: rtc.AudioSource | None = None
        self._tasks: set[asyncio.Task[None]] = set()
        self._agent_joined = asyncio.Event()
        self._user_track_sid = ""

    async def connect(self) -> None:
        if not (self.url and self._api_key and self._api_secret):
            raise AdapterError(
                "livekit: set url, api_key, and api_secret (or LIVEKIT_URL, LIVEKIT_API_KEY, "
                "LIVEKIT_API_SECRET)"
            )
        sr = self.session.sample_rate
        token = (
            api.AccessToken(self._api_key, self._api_secret)
            .with_identity(self.identity)
            .with_name(self.identity)
            .with_grants(api.VideoGrants(room_join=True, room=self.room_name))
            .to_jwt()
        )
        if self.agent_name:
            lkapi = api.LiveKitAPI(self.url, self._api_key, self._api_secret)
            try:
                await lkapi.agent_dispatch.create_dispatch(
                    api.CreateAgentDispatchRequest(agent_name=self.agent_name, room=self.room_name)
                )
            finally:
                await lkapi.aclose()

        room = rtc.Room()
        self._room = room

        def _on_track(
            track: rtc.Track, _pub: rtc.RemoteTrackPublication, _p: rtc.RemoteParticipant
        ) -> None:
            if track.kind == rtc.TrackKind.KIND_AUDIO:
                self._agent_joined.set()
                task = asyncio.ensure_future(self._read_track(track))
                self._tasks.add(task)
                task.add_done_callback(self._tasks.discard)

        def _on_transcription(segments: list[Any], participant: Any, _pub: Any) -> None:
            is_user = participant is not None and participant.identity == self.identity
            role: Role = "user" if is_user else "agent"
            for seg in segments:
                if getattr(seg, "final", True) and seg.text:
                    self.emit(Transcript(role, seg.text, self.session.clock.now()))

        room.on("track_subscribed", _on_track)
        room.on("transcription_received", _on_transcription)

        def _on_text_stream(reader: rtc.TextStreamReader, _identity: str) -> None:
            task = asyncio.ensure_future(self._read_transcription(reader))
            self._tasks.add(task)
            task.add_done_callback(self._tasks.discard)

        room.register_text_stream_handler("lk.transcription", _on_text_stream)

        await room.connect(self.url, token)
        self._source = rtc.AudioSource(sr, 1)
        track = rtc.LocalAudioTrack.create_audio_track("voicebench-user", self._source)
        options = rtc.TrackPublishOptions(source=rtc.TrackSource.SOURCE_MICROPHONE)
        publication = await room.local_participant.publish_track(track, options)
        self._user_track_sid = publication.sid
        try:
            await asyncio.wait_for(self._agent_joined.wait(), timeout=self.wait_for_agent_s)
        except TimeoutError as exc:
            await self.close()
            raise AdapterError(
                f"livekit: no agent audio track in room {self.room_name!r} after "
                f"{self.wait_for_agent_s:g} s"
            ) from exc

    async def _read_transcription(self, reader: rtc.TextStreamReader) -> None:
        # LiveKit Agents 1.x publishes transcripts as text streams. A stream that
        # names our published track as its source transcribes the user.
        attrs = reader.info.attributes or {}
        text = await reader.read_all()
        if attrs.get("lk.transcription_final", "true") != "true" or not text.strip():
            return
        is_user = attrs.get("lk.transcribed_track_id") == self._user_track_sid
        role: Role = "user" if is_user else "agent"
        self.emit(Transcript(role, text, self.session.clock.now()))

    async def _read_track(self, track: rtc.Track) -> None:
        sr = self.session.sample_rate
        stream = rtc.AudioStream(track, sample_rate=sr, num_channels=1)
        try:
            async for event in stream:
                data = np.frombuffer(event.frame.data, dtype=np.int16)
                pcm = (data.astype(np.float32) / 32768.0).astype(np.float32)
                self.emit(AgentAudio(pcm, self.session.clock.now()))
        finally:
            await stream.aclose()

    async def send_audio(self, pcm: au.FloatArray) -> None:
        if self._source is None:
            raise AdapterError("livekit: not connected")
        samples = np.clip(pcm * 32768.0, -32768, 32767).astype(np.int16)
        frame = rtc.AudioFrame(
            data=samples.tobytes(),
            sample_rate=self.session.sample_rate,
            num_channels=1,
            samples_per_channel=samples.size,
        )
        await self._source.capture_frame(frame)

    async def close(self) -> None:
        for task in list(self._tasks):
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await task
        if self._room is not None:
            with contextlib.suppress(Exception):
                await self._room.disconnect()
        self._room = None
        self._source = None

    def describe(self) -> dict[str, Any]:
        return {
            "type": self.name,
            "experimental": True,
            "url": self.url.split("?", 1)[0],
            "room": self.room_name,
            "agent_name": self.agent_name,
        }
