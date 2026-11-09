# TTS_Audio8_Model

Audio8-TTS-Realistic-Air text to speech with voice cloning (0.6B parameters, 23 languages, Apache-2.0), served over HTTP so projects send text instead of loading a model themselves. It has the same admin page, tokens, rate limits, metrics, settings and update checks as the other model services (`TTS_Paradee_Model` and `TTS_Piper_Model` are the same API shape with CPU engines).

The model runs in this process on an **NVIDIA GPU** (torch, transformers). It needs a CUDA GPU and the NVIDIA Container Toolkit; it is not meant for a box without one. Model: [Edge0/Audio8-TTS-Realistic-Air](https://huggingface.co/Edge0/Audio8-TTS-Realistic-Air), code: [edge0-ai/Audio8_TTS](https://github.com/edge0-ai/Audio8_TTS).

## API

| Call | Purpose |
|---|---|
| `POST /v1/speak` | `{"text", "voice", "seed", "temperature", "stream", "reference_audio_base64", "reference_text"}` returns a WAV file (`audio/wav`, 16-bit mono, the model's sample rate). Headers: `X-Audio-Seconds`, `X-Duration-Ms`, `X-Voice`, `X-Seed`, `X-Cache` (`hit` when the kept answer was sent). |
| `GET /v1/voices` | `{"voices", "default"}`; with a token limited to voices, only those. |
| `PUT /admin/voices/{name}` | Admin password. `{"audio_base64", "transcript"}`: a WAV clip (at most 10 MB) and exactly what it says. Adds or replaces a voice. |
| `DELETE /admin/voices/{name}` | Admin password. Removes a voice. |
| `GET /health` | `{"status": "ok", "model", "ready", "num_thread", "device", "voices"}`; `ready` is true once the model is loaded. No token needed. |

`text` is 1 to 5000 characters. Other fields are refused with 422, so a caller asking for `mp3` finds out instead of getting WAV silently. The model works best on pieces of at most 150 characters, so the service splits longer text at sentence ends (and at spaces inside a very long sentence) and joins the audio.

**One-call voice (nothing kept).** Instead of a stored `voice`, send `reference_audio_base64` (a WAV, up to 10 MB) and `reference_text` (exactly what it says). The clip is written to a temp file only while the speech is made and deleted when the call ends, fails or the client disconnects, streams included. It is never added to the voices volume, and the answer is never cached, even with a `seed`. `X-Voice` is `custom`. Both fields are required together; a `voice` other than `none` beside them gives 422, and a token limited to certain voices gets 403. The audio may also be a `data:audio/wav;base64,...` URL, which is what the Try it panel sends (its **One-call voice clip** and **What the clip says** fields).

**Voices.** A voice is a reference clip and its transcript. `none` (the default when `voice` is left out) uses no reference: the model picks a voice itself, and it changes from call to call unless a `seed` is sent. A token's *projects* list on the admin page limits the voices it may use, and `none` must be in that list to allow calls without a voice. The upstream model has no language parameter: it reads the language from the text.

**Seed and temperature.** `seed` makes the same text, voice and temperature give the same speech on the same GPU and model revision (the reply's `X-Seed` tells which seed a seed-less call got). `temperature` (0.1 to 1.5, default 0.8) is the upstream default; lower is steadier, higher more varied.

**Streaming.** With `"stream": true` the WAV is sent piece by piece while the rest is still being made, so the first audio arrives after the first piece. The header cannot know the length yet: its size fields are `0xFFFFFFFF` (read "until the connection ends"), and there is no `X-Audio-Seconds`. Players and `ffmpeg` read it; Python's `wave` module does not. Errors that can be known early (unknown voice, no speech in the text, model not loaded) are still normal HTTP errors; one after the first piece cuts the stream off.

**Cache.** The *Answers kept per replica* setting (`SERVICE_CACHE_SIZE`, default 32, 0 = off) keeps the last answers **for calls with a `seed`**; a call without one is random, so keeping it would never help. An answer over 1 MB is not kept. It is per replica and in memory, and emptied when the model is reloaded. Replacing a voice does not empty it: use a new voice name, or wait for the entries to age out.

## Admin page

`/admin/` (password `SERVICE_ADMIN_PASSWORD`): tokens with voice scope, rate limit and expiry, usage numbers, CPU threads, the Settings card (update check hours, in-flight cap, answers kept, model revision, device, data type, token limit, load at start), and the Updates card. The Cloned voices card adds, lists and deletes cloned voices (shown because the service has the `voice-cloning` tag); the voice calls above do the same (see `docs/guide-web-ui.md`). `/metrics` (admin password) is Prometheus text per token.

## Run

Startup, warm-up and inference never download weights. With no downloaded weights, `/health` answers `ready: false` and speech calls return 503. Open `/admin/` → **Updates** → **Download** before the first call; see the [admin guide](docs/guide-web-ui.md#updates-and-first-download) for the curl alternative.

```bash
docker compose up -d --build        # http://<host>:29322
python tools/bench.py http://127.0.0.1:29322 --save out
```

Without Docker: `run.bat` (uv, listens on `127.0.0.1:29322`). Startup loads downloaded weights only; open `/admin/`, then **Updates → Download** before the first call. See `deployment.md`.

## Tests

```bash
uv sync
uv run pytest
```

The tests use a fake model, so they need no GPU. Before relying on a new revision, run the real model once and listen to the result (`tools/bench.py` times it).

## Limits worth knowing

- One generation at a time per replica; extra calls wait, and more than the in-flight cap get 429. Reference and no-reference items cannot share a batch in the upstream processor, so there is no batching.
- The rate limit is per replica.
- Output is WAV only. Convert on the caller's side for MP3.
- The model runs remote code from the Hub. The revision is pinned (`SERVICE_MODEL_REVISION`) and the update check only finds a missing download; move the pin only to a commit you have read.
- Cloning a real person's voice needs their consent. Only the admin password can add voices.
- Measured on an RTX 4050 Laptop (6 GB), bfloat16: the model uses about 1.2 GiB after loading and peaks at 2.1 to 2.5 GiB. It speaks slower than real time there (about 1.8 s of work per second of audio), so use `stream: true` for anything interactive; the first audio then arrives after about 3 s. The same seed gave byte-identical audio. Other GPUs will differ; `tools/bench.py` times yours. The image is 17.6 GB (CUDA libraries from the torch wheel).

## Try it from the admin page

Open `/admin/` and use **Try it** to call the public API with a service token held only in memory. Runs use normal token scopes, limits and caches; the panel shows HTTP status, latency, responses, cancellation and a curl equivalent with a token placeholder. See [the web UI guide](docs/guide-web-ui.md#try-it-send-a-real-request).

Speak sends text, voice, seed and temperature to `POST /v1/speak`, then displays WAV audio with playback controls and a download. Audio8 has no speed or language request field. `GET /v1/voices` is filtered by the public token's allowed projects list; include `none` to allow speech without a reference voice. Only seeded calls are cached. An optional streaming request receives WAV chunks; the player is created when the bounded audio response finishes.

## Documentation

- [Purpose: input, output and what it is for](docs/purpose.md)
- [Deployment](deployment.md)
- [Changelog](CHANGELOG.md)
- [Design notes](docs/design.md)
- [Docker on another machine](docs/guide-docker-deployment-device.md)
- [Docker on this PC](docs/guide-docker-same-device.md)
- [Run without Docker](docs/guide-no-docker-same-device.md)
- [Test it from the command line](docs/guide-cli.md)
