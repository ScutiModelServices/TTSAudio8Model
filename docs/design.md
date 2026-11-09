# TTS_Audio8_Model: design notes

Built from `TTS_Paradee_Model` (API shape, voices, WAV streaming, shared files) and `IMG_TEM_Model` (GPU, torch, compose reservation). Behaviour is in `README.md`; the differences from the other services are listed in `.agents/skills/model-service-parity/SKILL.md`.

Sources read: GitHub `edge0-ai/Audio8_TTS` (README, `guides/inference.md`, `audio8_tts_infer.py`, `requirements.txt`) and the Hub model `Edge0/Audio8-TTS-Realistic-Air` at commit `23c305cc013fde378edb459f538317043c993a74` (`processing_arktts.py`, model metadata).

## Decisions

- **Engine = the calls in `audio8_tts_infer.py`.** `AutoProcessor` + `AutoModel` with `trust_remote_code`, `generate(...)`, `decode_audio(codes)`. No pip package or server API exists upstream.
- **Pinned revision.** The model runs remote code, so `model_revision` is a commit and the Updates card only reports a missing download.
- **No `language` field.** The processor takes `text`, `reference_text`, `reference_audio` and nothing else; the language comes from the text.
- **Voices = reference clip + transcript** in a shared `tts_audio8_model_voices` volume. `none` = no reference. Upload is admin-only and JSON/base64 (no multipart dependency). Reference and no-reference items cannot share a batch upstream, so no batching: one call, one generation, one slot per replica.
- **Text splitting at 150 characters** (upstream advice), at sentence ends, then spaces, then hard cut for text without spaces (Chinese, Japanese). One torch generator per call, seeded, so a seed reproduces the whole call.
- **Cache only for seeded calls**, like IMG_TEM_Model; a seed-less call is random and never repeats.
- **Deploy on the GPU PC, not ZimaOS.** Compose reserves one GPU. Callers get a connection error when the PC is off.

## Measured (RTX 4050 Laptop 6 GB, Docker Desktop WSL2)

Loaded 1.2 GiB VRAM, peak 2.5 GiB; about 1.8 s of work per second of audio; same seed = identical bytes; seeded repeat from cache in 0.03 s; sentence-by-sentence stream starts after about 3 s (a packed 150-character piece took 17 s, which is why streams are unpacked); image built (17.6 GB), container healthy with the GPU, token, voice upload, plain, cloned, cache, stream and 401 all checked through nginx.

## Not done / not measured

1. Listening quality of the output is unchecked (levels are sane: no clipping). `tests/` use a fake model.
2. Playwright admin-UI test not run.
3. The admin page has a voice card, switched on by the `voice-cloning` tag in `CONFIG.tags` of the shared `web/index.html`; services without the tag do not show it. `GET /admin/voices` feeds it.
4. Reference clip length limits and audio quality advice are not stated upstream.
5. No git repo or commit yet.
