# TTS_Audio8_Model

Audio8-TTS-Realistic-Air text to speech with voice cloning, served over HTTP on an NVIDIA GPU, behind the shared model-service admin page, tokens and settings. Port 29322, env prefix `SERVICE_`, token prefix `audio8_`.

## Agent instructions
This file is the one instruction file for every coding agent; `CLAUDE.md` only imports it (`@AGENTS.md`). Edit this file, never `CLAUDE.md`.

## Commands (from this folder, venv `.venv`, managed by uv)
- Install: `uv sync` (`winget install astral-sh.uv` if uv is missing)
- Test: `uv run pytest -q`. `tests/test_admin_ui.py` needs Playwright and its browser and is skipped without it. On Windows, if uv fails with "cannot move the file to a different disk drive", set `UV_CACHE_DIR` to a folder on the same drive and `UV_LINK_MODE=copy`.
- Run: `run.bat run`, or `uv run python src/app.py` (add `--dotenv` to load `.env`), or `docker compose up -d --build`

## Rules
- Load downloaded weights only. Startup, warm-up and inference must never download; missing weights keep health/admin available and inference returns 503 with an admin Updates Download hint. Only the Updates Download callback accesses the network for weights.
- Follow the `model-service-parity` skill and `AI/ModelServices/_docs/SHARED-FEATURES.md` (what must match in every model service) and `AI/ModelServices/_docs/SERVICE-SPECIFIC.md` (what differs on purpose). A change to a shared feature goes to every service; a new difference goes into `SERVICE-SPECIFIC.md` in the same change.
- `web/index.html`, `src/tokens.py`, `src/settings.py`, `src/updates.py` and `.dockerignore` are copies shared with the other model services. Change one, copy it to the others, run `python tools/check_sync.py` in each repo.
- `POST /v1/speak` takes `text`, `voice`, `seed`, `temperature`, `stream` and returns WAV. Voices are a reference clip plus transcript in the `tts_audio8_model_voices` volume (`src/voices.py`), added with `PUT /admin/voices/{name}` (admin password). `none` means no reference. `src/audio.py` is the same file as in the other two TTS services.
- The model runs code from the Hub (`trust_remote_code`), so `model_revision` is a pinned commit: read a new commit before moving it. Text is split at 150 characters; streams make one piece per sentence; the cache keeps only seeded calls.
- Needs an NVIDIA GPU. Measured on an RTX 4050 Laptop: 1.2 GiB loaded, 2.5 GiB peak, about 1.8 s of work per second of audio; the image is 17.6 GB. The tests use a fake model.
- Behaviour changes update `README.md`, `deployment.md`, `docs/guide-web-ui.md`, `.env.example` and `CHANGELOG.md` in the same commit.
- Never read or print `.env`, `tokens.json` or `settings.json`.
- Commit with the noreply author email `214214011+scutiii2@users.noreply.github.com` (another address is rejected on push). Push `main`, then run `python tools/publish_live.py`. Build Docker only when the Dockerfile or the dependencies changed.
