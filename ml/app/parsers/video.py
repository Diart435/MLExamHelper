"""Video parser: extract audio track via ffmpeg, then delegate to AudioParser.

ffmpeg is invoked as a subprocess (sync I/O) and offloaded to a thread.
Output: 16 kHz mono WAV — the format faster-whisper prefers.
"""
from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path


class VideoParser:
    extensions = (".mp4", ".mov", ".mkv", ".avi", ".webm")

    def extract(self, data: bytes, *, source: str) -> str:
        # Lazy import to avoid circular dep: registry imports video, video imports audio.
        from app.parsers.audio import AudioParser

        suffix = "." + source.rsplit(".", 1)[-1].lower() if "." in source else ".mp4"
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as vf:
            vf.write(data)
            video_tmp = vf.name
        audio_tmp = str(Path(video_tmp).with_suffix(".wav"))

        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",            # overwrite audio_tmp if it exists
                    "-i", video_tmp,
                    "-vn",           # drop video stream
                    "-acodec", "pcm_s16le",
                    "-ar", "16000",  # 16 kHz — Whisper's native sample rate
                    "-ac", "1",      # mono
                    audio_tmp,
                ],
                check=True,
                capture_output=True,
            )
            with open(audio_tmp, "rb") as f:
                return AudioParser().extract(f.read(), source=audio_tmp)
        except subprocess.CalledProcessError as e:
            raise RuntimeError(
                f"ffmpeg failed to extract audio from {source}: "
                f"{e.stderr.decode(errors='replace')[-500:]}"
            ) from e
        finally:
            for p in (video_tmp, audio_tmp):
                try:
                    os.unlink(p)
                except OSError:
                    pass