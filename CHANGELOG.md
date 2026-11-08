# Changelog

## Unreleased

- Fix: after Download, a CPU threads change or a sync from another replica drops the loaded model, the service now reloads it in the background (when "Load the model at start" is on) instead of showing "Starting" on `/admin/` until the first request.
- `POST /v1/speak` accepts a one-call reference voice: `reference_audio_base64` + `reference_text` instead of `voice`. The clip lives in a temp file only while the speech is made, is deleted when the call ends, fails or is closed (streams too), is never stored in the voices volume, and its answers are never cached. `X-Voice` is `custom`; a token limited to certain voices gets 403. The audio may be a `data:` URL; the admin **Try it** panel has fields for it. Same change in TTS_Kitten2_Model.

- Breaking: startup, warm-up and inference load downloaded weights only. Before the first call, open `/admin/` → Updates → Download (or POST `/admin/updates/weights` with the admin token). Missing weights leave health/admin available and speech returns 503. Checks never download; explicit Downloads invalidate every replica.

- `SERVICE_MODELS_DIR` sets where a local (no Docker) run keeps downloaded model weights: `settings.apply_models_dir()` maps it to `HF_HOME` and `OLLAMA_MODELS` at start.
- Docs: `docs/guide-cli.md`, a PowerShell-only way to test the service.

### Breaking: common service environment variables

Service-owned environment variables now use `SERVICE_*`. Old names are no longer read.
Rename old names once in your real `.env`, Compose `environment:` block, and CI/secret settings.

| Old name | New name |
|---|---|
| `AUDIO8_ADMIN_PASSWORD` | `SERVICE_ADMIN_PASSWORD` |
| `AUDIO8_CACHE_SIZE` | `SERVICE_CACHE_SIZE` |
| `AUDIO8_DEVICE` | `SERVICE_DEVICE` |
| `AUDIO8_DTYPE` | `SERVICE_DTYPE` |
| `AUDIO8_HOST` | `SERVICE_HOST` |
| `AUDIO8_MAX_INFLIGHT` | `SERVICE_MAX_INFLIGHT` |
| `AUDIO8_MAX_NEW_TOKENS` | `SERVICE_MAX_NEW_TOKENS` |
| `AUDIO8_MODEL_REVISION` | `SERVICE_MODEL_REVISION` |
| `AUDIO8_NUM_THREAD` | `SERVICE_NUM_THREAD` |
| `AUDIO8_PORT` | `SERVICE_PORT` |
| `AUDIO8_REPLICAS` | `SERVICE_REPLICAS` |
| `AUDIO8_TOKENS_FILE` | `SERVICE_TOKENS_FILE` |
| `AUDIO8_UPDATE_CHECK_HOURS` | `SERVICE_UPDATE_CHECK_HOURS` |
| `AUDIO8_VOICES_DIR` | `SERVICE_VOICES_DIR` |
| `AUDIO8_WARM` | `SERVICE_WARM` |
| `AUDIO8_WEB_DIR` | `SERVICE_WEB_DIR` |
| `AUDIO8_WEIGHTS_MARKER` | `SERVICE_WEIGHTS_MARKER` |

- Move the default service port from 9200 to 29322, including API replicas and the nginx load balancer. Update any explicit old port in your real `.env`, saved tool-service `backends.json` connections, and browser or MCP client configuration once. With Compose defaults, recreate the stack to use the new host and container ports; a custom host-port override stays as configured, while container ports still change to 29322.

- Renamed `TTSAudio8Model` to `TTS_Audio8_Model`; Docker project, API image, services, load balancer and volumes now use `tts_audio8_model` names. Callers on `citadel_core` connect to `tts_audio8_model_lb` at the existing port.
- Docker volume migration: existing volumes with old names are orphaned; renaming does not move data. Stop the old stack before copying; never use `down -v`. The commands below assume the previous default Compose project name; substitute actual volume names if `-p` or `COMPOSE_PROJECT_NAME` overrode it.
  - `audio8_models` → `tts_audio8_model_models`: `docker volume inspect audio8_models && docker volume create tts_audio8_model_models && docker run --rm -v audio8_models:/from:ro -v tts_audio8_model_models:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
  - `audio8_voices` → `tts_audio8_model_voices`: `docker volume inspect audio8_voices && docker volume create tts_audio8_model_voices && docker run --rm -v audio8_voices:/from:ro -v tts_audio8_model_voices:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
  - `audio8_tokens` → `tts_audio8_model_data`: `docker volume inspect audio8_tokens && docker volume create tts_audio8_model_data && docker run --rm -v audio8_tokens:/from:ro -v tts_audio8_model_data:/to alpine:3.21 sh -c "cd /from && cp -a . /to/"`
- To retain an old volume instead, set its top-level volume definition to `external: true` and `name: <old-volume-name>` in a local Compose override. Rollback: stop the renamed stack, restore the previous checkout and folder name, and restart the old stack with its original volumes; copy back newer data first if the renamed stack accepted writes.

- `run.bat` loads `.env` from the service folder for a local run: it passes `--dotenv`, the service prints which variable names it loaded (never the values), and a real environment variable still wins. A plain `python src/app.py` and Docker never read `.env`.
- Untracked folders now start with `.` or `_`: `zip_versions/` is `_zip_versions/`, `voices/` to `_voices/`. A local `voices`, `tem_code` or `zip_versions` folder from an older checkout needs renaming by hand.
- `run.bat` is now a menu (run the service, deploy, build the release ZIP) and `run.bat run|deploy|zip` skips it. `tools/deploy.bat`, `tools/make_zip.bat` and `tools/deploy.local.example.bat` are gone; the local deploy target is `tools/deploy.local.ini` (copy `tools/deploy.local.example.ini`).
- Admin page: **Connect to this service** card with the addresses other services can use (this page's address, same PC, Docker network, `host.docker.internal`) and every endpoint, each with a Copy button.
- Admin **Try it** panel: descriptor-driven public API requests, live text streams, JSON/media output, status and latency, cancellation and redacted curl. Auth choice (b): pasted public token stays in memory; normal scope, limits and caches apply. Shared `web/playground.js` is copied across all model and tool services.

- `run.bat`: runs `uv sync` directly; `python -m uv` failed when uv was installed only as a program (winget).
- Docker: `.dockerignore` keeps `.git`, `.venv`, tests and local state out of the build context (the same file in every model service).
- First version: Audio8-TTS-Realistic-Air (0.6B, 23 languages, zero-shot voice cloning, Apache-2.0) served on the GPU, with the admin page, tokens (scope, rate limit, expiry), metrics, Settings card, update checks and file downloads shared with the other model services.
- `POST /v1/speak` takes `text`, `voice`, `seed`, `temperature` and `stream` and returns a WAV file. `GET /v1/voices` lists the voices; `none` means no reference voice.
- Voices are a reference clip plus its transcript: `PUT /admin/voices/{name}` (admin password) and `DELETE /admin/voices/{name}`, kept in the shared `voices` volume.
- Text over 150 characters is split into pieces before the model sees it; `stream: true` sends the WAV piece by piece.
- Answer cache keeps only calls with a `seed` (`SERVICE_CACHE_SIZE`, default 32, 0 = off; `X-Cache` header).
- The model revision is pinned to one Hub commit because the model runs remote code (`SERVICE_MODEL_REVISION`).
- `tools/bench.py` times a service so `TTS_Piper_Model`, `TTS_Paradee_Model` and `TTS_Audio8_Model` can be compared.
