# TTS_Audio8_Model: Docker Desktop on this PC

Before the first call, open `/admin/` → **Updates** → **Download**. Startup never downloads weights. The [admin guide](guide-web-ui.md#updates-and-first-download) includes the curl alternative.

Run Audio8-TTS-Realistic-Air text to speech with voice cloning on an NVIDIA GPU (1.2 GiB loaded, 2.5 GiB peak) in Docker Desktop on the machine you work on, so other programs on it can call it.

## Requirements

- Docker Desktop with Compose v2 (Windows: WSL2 backend).
- An NVIDIA GPU with a current driver, and GPU support in Docker Desktop. Check it: `docker run --rm --gpus all nvidia/cuda:12.6.0-base-ubuntu24.04 nvidia-smi` must print your card.
- Network access for explicit Downloads from the Updates card; startup and inference use downloaded files only.
- GPU memory per replica: about 1.2 GiB loaded and up to 2.5 GiB while speaking long text (measured), so a 6 GB card holds one replica comfortably. The weights are about 2.5 GB on disk; the image is 17.6 GB.
- This service does not belong on a box without a GPU (ZimaOS here). Run it on the GPU PC and let other machines call it over the LAN or Tailscale.

## Steps

1. Configure. In `TTS_Audio8_Model/`:
   ```bash
   cp .env.example .env
   ```
   Set `SERVICE_ADMIN_PASSWORD` (required to download weights through the admin page). Leave `SERVICE_PORT=29322`. Leave `SERVICE_REPLICAS=1`.
2. Start:
   ```bash
   docker compose --env-file .env.compose up -d --build
   ```
   Startup loads downloaded weights only; open `/admin/`, then **Updates → Download** before the first call. `tts_audio8_model_lb` starts once `/health` answers; readiness may still be false
   (300 s startup grace). Watch with `docker compose ps` and `docker compose logs -f tts_audio8_model`.
3. Check:
   ```bash
   curl http://127.0.0.1:29322/health
   ```
   `ready` is `false` until the model has loaded, then `true`.
4. Open the admin page: `http://127.0.0.1:29322/admin/` (see [guide-web-ui.md](guide-web-ui.md)) and make a token for each caller.
5. Try a call:
   ```bash
   curl -X POST http://127.0.0.1:29322/v1/speak -H "Content-Type: application/json" -H "X-Internal-Token: audio8_..." -d '{"text":"Hello from the model service."}' -o hello.wav
   ```
   Expect a WAV file, `hello.wav`.
6. Callers connect to the published port. The caller holds the URL and token:
   - Caller on the host: `http://127.0.0.1:29322`.
   - Caller in another Docker stack on the same host: `http://host.docker.internal:29322`.

## Settings

In `.env.compose` next to `docker-compose.yml` (start with `docker compose --env-file .env.compose up -d --build`):

| Variable | Default | Effect |
|---|---|---|
| `SERVICE_REPLICAS` | `1` | Number of `tts_audio8_model` containers. Read by Compose. |
| `SERVICE_PORT` | `29322` | Host port `tts_audio8_model_lb` publishes. |
| `SERVICE_ADMIN_PASSWORD` | empty | Password for `/admin/`. When set, every call except `/health` must send a token as `X-Internal-Token`. Empty = no auth. |
| `SERVICE_NUM_THREAD` | torch decides | Starting value for the CPU threads card (it only serves what runs on the CPU, such as reading the reference clip); a value saved on `/admin/` wins. Use the number of physical cores, not logical CPUs. |

On the **Settings** card of `/admin/` (saved in `settings.json` beside the tokens, shared by all replicas; a saved
value beats the environment variable named in brackets): update check hours (`SERVICE_UPDATE_CHECK_HOURS`, 6),
in-flight cap (`SERVICE_MAX_INFLIGHT`, 0 = 4), answers kept per replica (`SERVICE_CACHE_SIZE`, 32, 0 = off; seeded calls only, at most 1 MB each), model revision (`SERVICE_MODEL_REVISION`, restart; the pinned Hub commit), device (`SERVICE_DEVICE`, restart, `cuda`), data type (`SERVICE_DTYPE`, restart, `bfloat16`; the CPU needs `float32`), most audio tokens per piece (`SERVICE_MAX_NEW_TOKENS`, restart, 1024) and load at start (`SERVICE_WARM`, restart). Compose does not pass these;
add the variable under `environment:` of `tts_audio8_model` to use one as a starting value.

## Daily use

```bash
docker compose ps          # state
docker compose logs -f tts_audio8_model
docker compose down        # stop (the weights volume is kept)
docker compose --env-file .env.compose up -d --build && docker compose restart tts_audio8_model_lb   # after a code change
```

## Time it

Try it and time it:

```bash
python tools/bench.py http://127.0.0.1:29322 --save out
```

## Problems

| Symptom | Fix |
|---|---|
| `address already in use` on 29322 | Another copy (`run.bat`, or the same stack on another compose project) is running. Stop it or change `SERVICE_PORT`. |
| `/health` shows `ready: false` for minutes | Download weights from the Updates card first; otherwise the service stays available with `ready: false`. Check `docker compose logs -f tts_audio8_model`. |
| 401 Invalid token | The caller's token is missing or revoked; make one on `/admin/`. |
| 503 `no GPU is visible here` | The container has no GPU. Enable GPU support in Docker Desktop and re-run the `nvidia-smi` check above. |
| Container restarts in a loop | Out of GPU memory. Close other GPU programs. |
| `tts_audio8_model_lb` never starts | No replica is healthy yet (process failure or out of memory). `docker compose logs tts_audio8_model`. |
| Replicas restart in a loop | Out of GPU memory. Lower `SERVICE_REPLICAS`, or check `docker compose logs tts_audio8_model` for `no GPU is visible`. |
| 403 "may not use voice" | The token's list on `/admin/` does not include that voice (or `none`, when `voice` is left out). |
| 404 on `/v1/speak` | The voice is not served here. `GET /v1/voices` lists them. |
| 422 on `format` or another field | Only `text`, `voice`, `seed`, `temperature` and `stream` exist; the reply is always WAV. |
| 429 | Over the token's rate limit, or too many calls waiting for the model. |
| nginx 502 after scaling | `tts_audio8_model_lb` not restarted after the replica count changed. |

The load balancer also joins external `citadel_core` as `tts_audio8_model_lb`. Start the Citadel stack first so that network exists; tool services on it use `http://tts_audio8_model_lb:29322`. Docker project and API image are `tts_audio8_model` and `tts_audio8_model:latest`; persistent volumes have explicit `tts_audio8_model_*` names. Volume migration and rollback instructions are in [CHANGELOG.md](../CHANGELOG.md).
