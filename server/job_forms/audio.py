"""Validate speech modes and audio/video transcription uploads before saving files."""

import math
import re
from pathlib import Path
import secrets
import shutil
from aiohttp import web

from audio_catalog import (
    ASR_MODELS,
    LANGUAGES,
    QWEN_VOICES,
    SPEECH_MODELS,
    omni_instruction,
)


def media_upload(upload, *, max_seconds):
    import av

    if not isinstance(upload, web.FileField):
        raise ValueError("An audio or video file is required")
    try:
        upload.file.seek(0)
        with av.open(upload.file, mode="r") as container:
            if not container.streams.audio:
                raise ValueError("The uploaded file has no audio track")
            stream = container.streams.audio[0]
            if stream.duration:
                seconds = float(stream.duration * stream.time_base)
            elif container.duration:
                seconds = float(container.duration / av.time_base)
            else:
                # Browser/live WebM recordings may omit duration metadata.
                # Packet timestamps can be scanned without decoding video frames.
                first, end = None, None
                for packet in container.demux(stream):
                    stamp = packet.pts if packet.pts is not None else packet.dts
                    if stamp is None:
                        continue
                    rate = packet.time_base or stream.time_base
                    start = float(stamp * rate)
                    first = start if first is None else min(first, start)
                    finish = float((stamp + (packet.duration or 0)) * rate)
                    end = finish if end is None else max(end, finish)
                    if end - first > max_seconds + 1:
                        raise ValueError(
                            f"Audio length must be at most {max_seconds:g} seconds"
                        )
                seconds = (end - first) if first is not None and end is not None else 0
        if not math.isfinite(seconds) or not 0.2 <= seconds <= max_seconds:
            raise ValueError(
                f"Audio length must be between 0.2 and {max_seconds:g} seconds"
            )
    except ValueError:
        raise
    except Exception:
        raise ValueError("The uploaded file is not readable audio/video") from None
    finally:
        upload.file.seek(0)
    return seconds


def save_media(upload, folder):
    suffix = Path(upload.filename or "").suffix.lower()
    if suffix not in (
        ".wav",
        ".mp3",
        ".mp4",
        ".mov",
        ".mkv",
        ".webm",
        ".flac",
        ".m4a",
        ".ogg",
        ".opus",
        ".aac",
        ".avi",
    ):
        suffix = ".media"
    name = secrets.token_hex(8) + suffix
    with (folder / name).open("wb") as output:
        shutil.copyfileobj(upload.file, output)
    return name


def base_options(form):
    language = form.get("language") or "auto"
    if not re.fullmatch(r"[A-Za-z][A-Za-z -]{1,31}", language):
        raise ValueError("Use a language name or ISO language code")
    return {"language": language}


def reject_other_inputs(form):
    if any(
        isinstance(form.get(k), web.FileField)
        for k in ("image", "ref_image", "ref_video", "last_image", "audio")
    ):
        raise ValueError(
            "Use voice_audio for speech references or media for transcription"
        )


def speech_fields(form, common, settings):
    reject_other_inputs(form)
    model = form.get("audio_model") or "qwen3_tts"
    if model not in SPEECH_MODELS:
        raise ValueError("Unknown speech model")
    mode = form.get("speech_mode") or "generate"
    if mode not in SPEECH_MODELS[model]["modes"]:
        raise ValueError("Unsupported speech mode")
    if len(common["prompt"]) > 4000:
        raise ValueError("Speech text must be at most 4000 characters")
    options = {
        **base_options(form),
        "speech_mode": mode,
        "instruction": (form.get("instruction") or "").strip(),
        "reference_text": (form.get("reference_text") or "").strip(),
        "voice": form.get("voice") or "Vivian",
    }
    if model == "qwen3_tts" and options["language"] not in LANGUAGES:
        raise ValueError("Qwen3-TTS supports the ten listed languages")
    if max(len(options["instruction"]), len(options["reference_text"])) > 4000:
        raise ValueError(
            "Instructions and reference transcripts must be at most 4000 characters"
        )
    if model == "qwen3_tts" and mode == "clone":
        options["instruction"] = ""
    if model == "omnivoice":
        options["instruction"] = omni_instruction(options["instruction"])
    if mode == "design" and not options["instruction"]:
        raise ValueError("Describe the voice to design")
    if (
        model == "qwen3_tts"
        and mode == "generate"
        and options["voice"] not in QWEN_VOICES
    ):
        raise ValueError("Unknown Qwen voice preset")
    upload = form.get("voice_audio")
    if mode == "clone":
        media_upload(upload, max_seconds=30)
    elif isinstance(upload, web.FileField):
        raise ValueError("Reference audio is only used in Clone mode")
    name = save_media(upload, settings.uploads) if mode == "clone" else None
    return dict(
        mode="tts",
        prompt=common["prompt"],
        audio_model=model,
        audio_options=options,
        input_media=name,
        seed=common["seed"],
        refs=[],
    )


def asr_fields(form, common, settings):
    reject_other_inputs(form)
    model = form.get("audio_model") or "qwen3_asr"
    if model not in ASR_MODELS:
        raise ValueError("Unknown transcription model")
    timestamps = form.get("timestamps") or "word"
    if timestamps not in ASR_MODELS[model]["timestamps"]:
        raise ValueError("This model does not produce the requested timestamps")
    options = {**base_options(form), "timestamps": timestamps}
    upload = form.get("media")
    duration = media_upload(upload, max_seconds=7200)
    name = save_media(upload, settings.uploads)
    return dict(
        mode="asr",
        prompt=(form.get("prompt") or "Transcription").strip(),
        audio_model=model,
        audio_options=options,
        input_media=name,
        duration=duration,
        seed=common["seed"],
        refs=[],
    )
