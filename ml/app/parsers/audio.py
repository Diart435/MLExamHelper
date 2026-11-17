"""Audio parser via local `faster-whisper` (CTranslate2).

Whisper model is loaded lazily on first call and cached on the parser object
(it can take 5-30 seconds to load and ~150 MB-1.5 GB RAM depending on size).
The model files themselves are cached by HuggingFace in `~/.cache/huggingface`.

Requires ffmpeg in PATH (pydub uses it for non-mp3 formats and faster-whisper
needs it for some decoders).
"""
from __future__ import annotations

import os
import tempfile
import time
from threading import Lock

from loguru import logger

from app.core.config import get_settings


# Как часто логировать прогресс транскрибации. Меньше — шумнее, больше —
# кажется что висит. 30 секунд аудио — компромисс.
_PROGRESS_EVERY_SEC = 30.0


class AudioParser:
    extensions = (".mp3", ".wav", ".m4a", ".ogg", ".flac")

    def __init__(self) -> None:
        self._model = None
        self._lock = Lock()

    def _ensure_model(self):
        # Lazy + thread-safe — model load is heavy and not thread-safe to start.
        if self._model is None:
            with self._lock:
                if self._model is None:
                    logger.info(f"Loading Whisper model "
                                f"(size={get_settings().whisper_model_size}, "
                                f"device={get_settings().whisper_device}) — "
                                f"first call can take 5-30s")
                    from faster_whisper import WhisperModel
                    s = get_settings()
                    self._model = WhisperModel(
                        s.whisper_model_size,
                        device=s.whisper_device,
                        compute_type=s.whisper_compute_type,
                    )
        return self._model

    def extract(self, data: bytes, *, source: str) -> str:
        s = get_settings()
        if not s.whisper_enabled:
            raise RuntimeError(
                "Whisper is disabled (WHISPER_ENABLED=false). "
                "Set WHISPER_ENABLED=true in .env to transcribe audio/video."
            )

        # faster-whisper accepts a path or file-like; temp file is simplest.
        suffix = "." + source.rsplit(".", 1)[-1].lower() if "." in source else ".mp3"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as f:
            f.write(data)
            tmp_path = f.name
        try:
            t0 = time.monotonic()
            model = self._ensure_model()
            segments_iter, info = model.transcribe(tmp_path, beam_size=5)
            total_sec = float(getattr(info, "duration", 0.0) or 0.0)
            logger.info(
                f"Whisper transcribing {source}: "
                f"duration={total_sec:.0f}s, "
                f"language={getattr(info, 'language', '?')}, "
                f"beam=5"
            )

            # faster-whisper отдаёт сегменты лениво — собираем с периодическим
            # логом прогресса, чтобы не казалось, что висим.
            pieces: list[str] = []
            last_log_at = 0.0
            for seg in segments_iter:
                pieces.append(seg.text.strip())
                seg_end = float(getattr(seg, "end", 0.0) or 0.0)
                if seg_end - last_log_at >= _PROGRESS_EVERY_SEC and total_sec > 0:
                    pct = min(100.0, seg_end / total_sec * 100.0)
                    logger.info(
                        f"Whisper progress: {seg_end:.0f}/{total_sec:.0f}s "
                        f"({pct:.0f}%), {len(pieces)} segments so far"
                    )
                    last_log_at = seg_end

            text = " ".join(p for p in pieces if p).strip()
            elapsed = time.monotonic() - t0
            if total_sec > 0 and elapsed > 0:
                rate = f", {total_sec / elapsed:.1f}x realtime"
            else:
                rate = ""
            logger.info(
                f"Whisper done: {len(text)} chars, "
                f"{len(pieces)} segments, {elapsed:.1f}s wall time{rate}"
            )
            return text
        finally:
            try:
                os.unlink(tmp_path)
            except OSError:
                pass