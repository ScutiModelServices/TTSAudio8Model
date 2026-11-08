"""The options the admin page can change. Each can still start from its environment variable; a saved value wins."""

from engine import DEFAULT_REVISION
from settings import Setting

SETTINGS = [
    Setting("update_check_hours", "Check for updates every (hours)", "float", 6.0, "SERVICE_UPDATE_CHECK_HOURS", 0, 720,
            help="0 = only when you press Check now. The revision is pinned, so this finds only a missing download"),
    Setting("max_inflight", "Calls allowed to wait for the model", "int", 0, "SERVICE_MAX_INFLIGHT", 0, 10000,
            help="Per replica; more get 429. 0 = 4"),
    Setting("cache_size", "Answers kept per replica", "int", 32, "SERVICE_CACHE_SIZE", 0, 100000,
            help="Calls with a seed, sent again for the same text, voice, temperature and seed. Each is at most 1 MB. 0 = off"),
    Setting("model_revision", "Model revision", "text", DEFAULT_REVISION, "SERVICE_MODEL_REVISION", restart=True, blank=False,
            help="The Hub commit of Edge0/Audio8-TTS-Realistic-Air. It runs remote code, so move it only to a commit you have read. After a restart, download it from the Updates card"),
    Setting("device", "Device", "text", "cuda", "SERVICE_DEVICE", restart=True, blank=False,
            help="cuda for the GPU, cpu only for tests: it is far slower than real time"),
    Setting("dtype", "Data type", "text", "bfloat16", "SERVICE_DTYPE", restart=True, blank=False,
            help="bfloat16 on the GPU; the CPU needs float32"),
    Setting("max_new_tokens", "Most audio tokens per piece of text", "int", 1024, "SERVICE_MAX_NEW_TOKENS", 64, 8000, restart=True,
            help="A piece that does not finish is tried once more with 2000. Each piece is at most 150 characters"),
    Setting("warm", "Load the model at start", "bool", True, "SERVICE_WARM", restart=True),
]
