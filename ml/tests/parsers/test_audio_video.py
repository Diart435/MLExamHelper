"""Tests for AudioParser / VideoParser — Whisper and ffmpeg are mocked.

Real audio transcription is integration-tested manually (see plan §Verification);
unit tests just confirm the wiring: model is called once and cached, video invokes
ffmpeg and delegates to audio, errors surface clearly.
"""
from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest


def _fake_segment(text: str):
    seg = MagicMock()
    seg.text = text
    return seg


def test_audio_parser_calls_model_and_joins_segments(monkeypatch, tmp_path: Path):
    """End-to-end shape: bytes → temp file → model.transcribe → joined text."""
    monkeypatch.setenv("WHISPER_ENABLED", "true")
    monkeypatch.setenv("WHISPER_MODEL_SIZE", "base")

    # Reload settings after monkeypatching.
    from app.core import config as cfg_mod
    cfg_mod._settings = None

    fake_model = MagicMock()
    fake_model.transcribe.return_value = (
        [_fake_segment("привет"), _fake_segment("мир")],
        MagicMock(),
    )

    # Patch WhisperModel class so the lazy _ensure_model returns our mock.
    with patch("faster_whisper.WhisperModel", return_value=fake_model) as WMC:
        from app.parsers.audio import AudioParser
        parser = AudioParser()
        out = parser.extract(b"fake mp3 bytes", source="hello.mp3")
        assert out == "привет мир"
        # Model constructed exactly once (cached on second use).
        WMC.assert_called_once()


def test_audio_parser_disabled_fails_fast(monkeypatch):
    monkeypatch.setenv("WHISPER_ENABLED", "false")
    from app.core import config as cfg_mod
    cfg_mod._settings = None

    from app.parsers.audio import AudioParser
    parser = AudioParser()
    with pytest.raises(RuntimeError, match="Whisper is disabled"):
        parser.extract(b"x", source="x.mp3")


def test_audio_parser_model_cached_across_calls(monkeypatch):
    """_ensure_model must not rebuild the WhisperModel on every call."""
    monkeypatch.setenv("WHISPER_ENABLED", "true")
    from app.core import config as cfg_mod
    cfg_mod._settings = None

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([_fake_segment("ok")], MagicMock())

    with patch("faster_whisper.WhisperModel", return_value=fake_model) as WMC:
        from app.parsers.audio import AudioParser
        parser = AudioParser()
        parser.extract(b"x", source="x.mp3")
        parser.extract(b"y", source="y.mp3")
        parser.extract(b"z", source="z.mp3")
        # Model constructed only once even though extract was called 3 times.
        assert WMC.call_count == 1


def test_video_parser_extracts_audio_via_ffmpeg(monkeypatch, tmp_path: Path):
    """Video → ffmpeg → audio bytes → AudioParser.extract()."""
    monkeypatch.setenv("WHISPER_ENABLED", "true")
    from app.core import config as cfg_mod
    cfg_mod._settings = None

    fake_model = MagicMock()
    fake_model.transcribe.return_value = ([_fake_segment("распознано")], MagicMock())

    def fake_ffmpeg(*args, **kwargs):
        # subprocess.run(cmd, ...) — cmd is the first positional arg.
        cmd = args[0]
        audio_out = cmd[-1]  # last element of the ffmpeg command
        Path(audio_out).write_bytes(b"fake wav data")
        return MagicMock(returncode=0)

    with (
        patch("subprocess.run", side_effect=fake_ffmpeg) as RUN,
        patch("faster_whisper.WhisperModel", return_value=fake_model),
    ):
        from app.parsers.video import VideoParser
        out = VideoParser().extract(b"fake mp4 bytes", source="lecture.mp4")
        assert out == "распознано"
        # ffmpeg invoked once with expected flags
        RUN.assert_called_once()
        cmd = RUN.call_args[0][0]
        assert cmd[0] == "ffmpeg"
        assert "-vn" in cmd
        assert "pcm_s16le" in cmd


def test_video_parser_surfaces_ffmpeg_errors(monkeypatch):
    monkeypatch.setenv("WHISPER_ENABLED", "true")
    from app.core import config as cfg_mod
    cfg_mod._settings = None

    import subprocess as sp
    err = sp.CalledProcessError(1, ["ffmpeg"], stderr=b"Invalid data found")
    with patch("subprocess.run", side_effect=err):
        from app.parsers.video import VideoParser
        with pytest.raises(RuntimeError, match="ffmpeg failed"):
            VideoParser().extract(b"corrupt", source="corrupt.mp4")