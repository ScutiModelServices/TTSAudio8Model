"""Audio8-TTS-Realistic-Air (0.6B, 23 languages, zero-shot voice cloning) run in this process, on the GPU.

The model and its processor are remote code from the Hub (`trust_remote_code`), so the revision is pinned to one commit.
The calls below are the ones `audio8_tts_infer.py` of github.com/edge0-ai/Audio8_TTS makes. A voice is a reference clip
and its transcript (see voices.py); with no voice the model speaks in a voice of its own choosing. One generation runs
at a time per replica (the processor cannot mix reference and no-reference items in a batch); scale with replicas.

shortcut: the revision is a pinned commit, so the update check only reports a change when the `model_revision` setting
moves. Text over 150 characters is split before the model sees it (upstream: longer input lowers quality)."""

from __future__ import annotations

import asyncio
import logging
import os
import random
import re
import tempfile
import threading
import uuid
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Iterator

from audio import wav_bytes
from voices import NO_REFERENCE, VoiceStore

_log = logging.getLogger(__name__)

MODEL_ID = "Edge0/Audio8-TTS-Realistic-Air"
DEFAULT_REVISION = "23c305cc013fde378edb459f538317043c993a74"
MAX_CHARS = 150  # upstream: "keep each input within 150 characters"
RETRY_TOKENS = 2000  # upstream retries an item that did not reach its end token with this limit
BOUNDARY = re.compile(r"(?<=[.!?;:])\s+|(?<=[。！？；：])\s*")  # not inside "3.14" or "10:30"


class EngineError(RuntimeError):
    """The text could not be spoken. `status` is the HTTP status the service maps it to."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


def split_text(text: str, limit: int = MAX_CHARS, pack: bool = True) -> list[str]:
    """Sentences packed into pieces of at most `limit` characters (`pack` False: one piece per sentence, so a stream
    starts after one sentence). A sentence longer than that is cut at spaces, or at `limit` when it has none (Chinese,
    Japanese)."""
    pieces: list[str] = []
    current = ""
    for sentence in filter(None, (part.strip() for part in BOUNDARY.split(text.strip()))):
        while len(sentence) > limit:
            cut = sentence.rfind(" ", 0, limit + 1)
            cut = cut if cut > 0 else limit
            sentence, rest = sentence[:cut].strip(), sentence[cut:].strip()
            if current:
                pieces.append(current)
                current = ""
            pieces.append(sentence)
            sentence = rest
        if pack and len(current) + len(sentence) + 1 <= limit:
            current = f"{current} {sentence}".strip()
        else:
            if current:
                pieces.append(current)
            current = sentence
    if current:
        pieces.append(current)
    return [piece for piece in pieces if any(char.isalnum() for char in piece)]  # "..." has nothing to say


class Speaker:
    """A loaded model that turns text into 16-bit mono PCM."""

    def __init__(self, processor: Any, model: Any, device: str) -> None:
        self._processor, self._model, self._device = processor, model, device
        self.rate = int(model.config.codec_sample_rate)

    def pieces(self, texts: list[str], reference: tuple[Path, str] | None, seed: int, temperature: float,
               max_new_tokens: int, threads: int | None) -> Iterator[bytes]:
        """One piece of audio per text, made as the caller asks for the next one."""
        import torch

        if threads:
            torch.set_num_threads(threads)
        generator = torch.Generator(device=self._device).manual_seed(seed)  # one stream for all pieces of a call
        for text in texts:
            yield self._speak(text, reference, generator, temperature, max_new_tokens)

    def _speak(self, text: str, reference: tuple[Path, str] | None, generator: Any, temperature: float, max_new_tokens: int) -> bytes:
        import torch

        fields: dict[str, Any] = {"text": [text], "return_tensors": "pt"}
        if reference is not None:
            fields.update(reference_audio=[reference[0]], reference_text=[reference[1]])
        with torch.no_grad():
            inputs = {name: value.to(self._device) for name, value in self._processor(**fields).items()}
            for limit in dict.fromkeys((max_new_tokens, max(max_new_tokens, RETRY_TOKENS))):
                out = self._model.generate(**inputs, max_new_tokens=limit, temperature=temperature, top_p=0.95, top_k=50,
                                           do_sample=True, generator=generator, return_dict_in_generate=True)
                if bool(out.finished[0]):
                    break
            else:
                _log.warning("The model did not reach its end token for %r; the audio may be cut off", text[:60])
            waves, lengths = self._model.decode_audio(out.codes)
            wave = waves[0, : int(lengths[0])].float().clamp(-1.0, 1.0)
            return (wave * 32767).to(torch.int16).cpu().numpy().astype("<i2").tobytes()


def load(model_id: str, revision: str, device: str, dtype: str) -> Speaker:
    """Loads the downloaded pinned model without network access. Blocking: run it in a thread."""
    import torch
    from transformers import AutoModel, AutoProcessor

    processor = AutoProcessor.from_pretrained(model_id, revision=revision, local_files_only=True, trust_remote_code=True)

    if device.startswith("cuda") and not torch.cuda.is_available():
        raise EngineError("The device is cuda but no GPU is visible here. Install a CUDA build of torch or set the device to cpu.", 503)
    if device == "cpu" and dtype != "float32":
        raise EngineError("CPU inference needs the float32 dtype", 503)
    model = AutoModel.from_pretrained(model_id, revision=revision, local_files_only=True, trust_remote_code=True, dtype=getattr(torch, dtype)).eval().to(device)
    speaker = Speaker(processor, model, device)
    list(speaker.pieces(["Warm up."], None, 0, 0.8, 64, None))  # the first call costs seconds of GPU setup (measured: 12 s vs 8 s)
    return speaker


def _remote_sha(model_id: str, revision: str) -> str:
    from huggingface_hub import HfApi

    return HfApi().model_info(model_id, revision=revision, token=False).sha


def _write_temp_clip(wav: bytes) -> Path:
    """The one-call reference clip as a file the processor can read; the caller deletes it."""
    handle, name = tempfile.mkstemp(prefix="audio8-ref-", suffix=".wav")
    with os.fdopen(handle, "wb") as file:
        file.write(wav)
    return Path(name)


def _cached_sha(model_id: str, revision: str) -> str | None:
    from huggingface_hub import snapshot_download

    try:
        return Path(snapshot_download(model_id, revision=revision, local_files_only=True)).name
    except Exception:  # not downloaded yet
        return None


def _download(model_id: str, revision: str) -> None:
    from huggingface_hub import snapshot_download
    from progress import hub_blobs, hub_total, tracking

    with tracking(model_id, hub_total(model_id, revision), hub_blobs(model_id)):
        snapshot_download(model_id, revision=revision, token=False)


def default_marker() -> Path:
    """File in the shared models volume whose content changes when one replica downloads new weights."""
    configured = os.environ.get("SERVICE_WEIGHTS_MARKER")
    return Path(configured) if configured else Path(os.environ.get("HF_HOME") or "~/.cache/huggingface").expanduser() / ".audio8-weights-version"


class Audio8Engine:
    """The `loader`, `remote_sha`, `cached_sha` and `download` callables are injectable for tests."""

    def __init__(self, revision: str = DEFAULT_REVISION, device: str = "cuda", dtype: str = "bfloat16", max_new_tokens: int = 1024, *,
                 store: VoiceStore | None = None, marker: Path | None = None,
                 loader: Callable[[str, str, str, str], Speaker] = load,
                 remote_sha: Callable[[str, str], str] = _remote_sha, cached_sha: Callable[[str, str], str | None] = _cached_sha,
                 download: Callable[[str, str], None] = _download) -> None:
        self.model = MODEL_ID
        self.revision, self.device, self.dtype, self.max_new_tokens = revision, device, dtype, max_new_tokens
        self.store = store or VoiceStore()
        self._threads: int | None = None
        self._marker = marker
        self._seen = self._read_marker()
        self._loader = loader
        self._remote_sha_of, self._cached_sha_of, self._download_of = remote_sha, cached_sha, download
        self._loaded: Speaker | None = None
        self._load_lock = threading.Lock()
        self._gate = asyncio.Semaphore(1)
        self.generation = 0  # part of the answer cache key; changes whenever the loaded model is dropped

    @property
    def voices(self) -> list[str]:
        return [NO_REFERENCE, *self.store.names()]

    @property
    def default_voice(self) -> str:
        return NO_REFERENCE

    @property
    def num_thread(self) -> int | None:
        return self._threads

    @num_thread.setter
    def num_thread(self, count: int) -> None:
        self._threads = count  # read on every call; the model stays loaded

    @property
    def ready(self) -> bool:
        return self._loaded is not None

    async def close(self) -> None:
        self._loaded = None

    async def warm(self) -> None:
        """Load the model now so the first request does not pay for it."""
        await asyncio.to_thread(self._speaker)

    def _speaker(self) -> Speaker:
        with self._load_lock:
            if self._loaded is None:
                try:
                    self._loaded = self._loader(self.model, self.revision, self.device, self.dtype)
                except OSError:
                    raise EngineError("Model weights are not downloaded. Ask an admin to press Download on the Updates card.", 503) from None
            return self._loaded

    def _reference(self, voice: str | None) -> tuple[str, tuple[Path, str] | None]:
        name = voice or NO_REFERENCE
        if name == NO_REFERENCE:
            return name, None
        reference = self.store.get(name)
        if reference is None:
            raise EngineError(f"Voice {name!r} is not served here; GET /v1/voices lists them", 404)
        return name, reference

    async def synthesize(self, text: str, voice: str | None, seed: int | None, temperature: float,
                         clip: tuple[bytes, str] | None = None) -> dict[str, Any]:
        rate, parts, name = None, bytearray(), voice
        async for rate, piece in self.stream(text, voice, seed, temperature, clip=clip):
            parts += piece
        return {"wav": wav_bytes(bytes(parts), rate), "seconds": len(parts) / 2 / rate, "voice": name or NO_REFERENCE}

    async def stream(self, text: str, voice: str | None, seed: int | None, temperature: float,
                     pack: bool = True, clip: tuple[bytes, str] | None = None) -> AsyncIterator[tuple[int, bytes]]:
        """The audio as it is made: (sample rate, 16-bit mono PCM) per piece of text; `pack` False = one piece per
        sentence. Holds the generation slot until the last piece, or until the caller closes the iterator.
        `clip` = (WAV bytes, transcript) of a one-call reference voice: it is written to a temp file only while the
        audio is made and deleted when the iterator ends, fails or is closed; it is never kept."""
        _, reference = self._reference(None if clip else voice)
        texts = split_text(text, pack=pack)
        if not texts:
            raise EngineError("No speech could be made from that text.", 422)
        seed = random.getrandbits(62) if seed is None else seed
        async with self._gate:
            loaded = await asyncio.to_thread(self._speaker)
            temp: Path | None = None
            try:
                if clip:
                    temp = await asyncio.to_thread(_write_temp_clip, clip[0])
                    reference = (temp, clip[1])
                pieces = loaded.pieces(texts, reference, seed, temperature, self.max_new_tokens, self._threads)
                while (piece := await asyncio.to_thread(next, pieces, None)) is not None:
                    yield loaded.rate, piece
            finally:
                if temp is not None:
                    temp.unlink(missing_ok=True)

    # Updates: the Hub revision of the model files, shared by all replicas through one models volume.

    async def cached_sha(self) -> str | None:
        return await asyncio.to_thread(self._cached_sha_of, self.model, self.revision)

    async def remote_sha(self) -> str:
        return await asyncio.to_thread(self._remote_sha_of, self.model, self.revision)

    async def pull(self) -> None:
        await asyncio.to_thread(self._download_of, self.model, self.revision)

    async def unload(self) -> None:
        """Forget the loaded model here and tell the other replicas to do the same; the next call loads the new files."""
        if self._marker is not None:
            self._marker.parent.mkdir(parents=True, exist_ok=True)
            self._seen = uuid.uuid4().hex
            self._marker.write_text(self._seen, "utf-8")
        self._forget()

    def sync(self) -> None:
        """Called every second: drop the loaded model when another replica downloaded new files."""
        current = self._read_marker()
        if current != self._seen:
            self._seen = current
            self._forget()

    def _forget(self) -> None:
        with self._load_lock:
            self._loaded = None
            self.generation += 1  # kept answers are from the old files

    def _read_marker(self) -> str | None:
        try:
            return self._marker.read_text("utf-8") if self._marker else None
        except OSError:
            return None
