import pytest

from engine import Audio8Engine
from voices import VoiceStore

WAV = b"RIFF" + b"\0" * 4 + b"WAVE" + b"\0" * 32  # passes the store's header check; the fake model never decodes it


@pytest.fixture(autouse=True)
def _tmp_files(tmp_path, monkeypatch):
    """Keeps tokens.json, settings.json and the voices out of the repo, and a saved setting from leaking into the next test."""
    monkeypatch.setenv("SERVICE_TOKENS_FILE", str(tmp_path / "tokens.json"))
    monkeypatch.setenv("SERVICE_VOICES_DIR", str(tmp_path / "voices"))


class FakeSpeaker:
    """Stands in for the loaded model: 0.1 s of audio per text (4800 bytes at 24 kHz) and a record of every call."""

    rate = 24000

    def __init__(self):
        self.calls = []
        self.fail = False

    def pieces(self, texts, reference, seed, temperature, max_new_tokens, threads):
        self.calls.append({"texts": texts, "reference": reference, "seed": seed, "temperature": temperature,
                           "max_new_tokens": max_new_tokens, "threads": threads,
                           "reference_bytes": reference[0].read_bytes() if reference else None})  # read now: a one-call clip is deleted later
        if self.fail:
            raise RuntimeError("model crashed")
        for _ in texts:
            yield b"\1\0" * (self.rate // 10)


def make_engine(voices=(), **options):
    """An engine whose loader builds a FakeSpeaker; `engine.loads` lists the (revision, device, dtype) it was asked for."""
    loads, made = [], []

    def loader(model_id, revision, device, dtype):
        loads.append((revision, device, dtype))
        made.append(FakeSpeaker())
        return made[-1]

    options.setdefault("loader", loader)
    engine = Audio8Engine(**options)
    for name in voices:
        engine.store.put(name, WAV, f"Transcript of {name}.")
    engine.loads, engine.made = loads, made
    return engine
