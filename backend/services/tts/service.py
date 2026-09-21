"""Speech in and out, via Groq Whisper (STT) and Orpheus (TTS).

Deliberately the same provider and the same GROQ_API_KEY the chat completions
already use, so voice adds no vendor, no key and no dependency -- the groq SDK
already ships `audio.transcriptions.create` and `audio.speech.create`.

Everything here raises VoiceUnavailable rather than letting a provider error
escape. Voice is an enhancement on top of a working text product: a failed
transcription should degrade to "I couldn't hear that, try text", never a 500
that loses the user's message.
"""

from __future__ import annotations

import logging
import os

from services.groq.service import get_groq_client

logger = logging.getLogger(__name__)

# turbo over whisper-large-v3: ~3x cheaper and noticeably faster, at 12% vs
# 10.3% word error rate. For short chat utterances that latency matters more
# than the 1.7 points, and a mis-heard word is recoverable -- the transcript is
# echoed back to the user, who can correct it.
STT_MODEL = os.getenv("GROQ_STT_MODEL", "whisper-large-v3-turbo")
TTS_MODEL = os.getenv("GROQ_TTS_MODEL", "canopylabs/orpheus-v1-english")

# Groq's free tier rejects uploads over 25MB. Checked before upload so an
# oversized clip fails fast and locally with a clear message, rather than
# after a slow upload with a provider-shaped error.
MAX_AUDIO_BYTES = int(os.getenv("MAX_AUDIO_BYTES", str(24 * 1024 * 1024)))

# Orpheus charges per character and a long reply makes a tediously long voice
# note. Replies over this are spoken up to a sentence boundary and the full
# text is still delivered in the message body.
MAX_TTS_CHARS = int(os.getenv("MAX_TTS_CHARS", "1200"))

# The agent JSON files predate any real TTS and use abstract slots
# ("male-1", "female-2"). Map them onto actual Orpheus voices here rather than
# rewriting the JSON, so the agent definitions stay provider-agnostic: swapping
# TTS vendors later means editing this dict, not five agent files.
_ORPHEUS_VOICES = ("autumn", "diana", "hannah", "austin", "daniel", "troy")
VOICE_MAP = {
    "male-1": "troy",
    "male-2": "austin",
    "male-3": "daniel",
    "female-1": "hannah",
    "female-2": "autumn",
    "female-3": "diana",
    "default": "hannah",
}


class VoiceUnavailable(RuntimeError):
    """Raised when speech features are disabled or a provider call fails."""


def voice_enabled() -> bool:
    return os.getenv("VOICE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


def resolve_voice(voice_type: str | None) -> str:
    """Map an agent's voice_type slot to a real Orpheus voice name.

    Accepts a raw Orpheus name too, so an agent can opt straight into a
    specific voice without going through the slot indirection.
    """
    key = (voice_type or "default").strip().lower()
    if key in _ORPHEUS_VOICES:
        return key
    return VOICE_MAP.get(key, VOICE_MAP["default"])


def _truncate_for_speech(text: str) -> str:
    if len(text) <= MAX_TTS_CHARS:
        return text
    head = text[:MAX_TTS_CHARS]
    # Prefer a sentence boundary so the audio doesn't stop mid-word. Only
    # accept one from the latter half, otherwise a single early full stop
    # would clip the whole reply down to one sentence.
    cut = max(head.rfind(". "), head.rfind("! "), head.rfind("? "))
    return head[: cut + 1] if cut > MAX_TTS_CHARS // 2 else head


async def transcribe(audio: bytes, filename: str = "audio.ogg") -> str:
    """Speech -> text. Returns the transcript, or raises VoiceUnavailable."""
    if not voice_enabled():
        raise VoiceUnavailable("Voice features are disabled by VOICE_ENABLED")
    if not audio:
        raise VoiceUnavailable("Received an empty audio file")
    if len(audio) > MAX_AUDIO_BYTES:
        # One decimal place: integer MB truncation rendered a 24.1MB clip as
        # "Audio is 24MB; the limit is 24MB", which reads like a bug report.
        raise VoiceUnavailable(
            f"That recording is {len(audio) / 1024 / 1024:.1f}MB; "
            f"the limit is {MAX_AUDIO_BYTES / 1024 / 1024:.1f}MB. Try a shorter clip."
        )
    try:
        result = await get_groq_client().audio.transcriptions.create(
            model=STT_MODEL,
            # The tuple form carries the filename through; Groq infers the
            # container from its extension, so a wrong/missing one is rejected
            # even when the bytes are fine.
            file=(filename, audio),
            response_format="text",
        )
    except Exception as exc:
        logger.warning("Transcription failed: %s", exc)
        raise VoiceUnavailable(f"Could not transcribe audio: {exc}") from exc
    text = (result if isinstance(result, str) else getattr(result, "text", "")).strip()
    if not text:
        raise VoiceUnavailable("No speech detected in that audio")
    return text


async def synthesize(text: str, voice_type: str | None = None) -> bytes:
    """Text -> WAV bytes. Raises VoiceUnavailable on any failure."""
    if not voice_enabled():
        raise VoiceUnavailable("Voice features are disabled by VOICE_ENABLED")
    spoken = _truncate_for_speech((text or "").strip())
    if not spoken:
        raise VoiceUnavailable("Nothing to speak")
    try:
        response = await get_groq_client().audio.speech.create(
            model=TTS_MODEL,
            voice=resolve_voice(voice_type),
            input=spoken,
            response_format="wav",
        )
        return await response.aread()
    except Exception as exc:
        logger.warning("Speech synthesis failed: %s", exc)
        raise VoiceUnavailable(f"Could not synthesize speech: {exc}") from exc
