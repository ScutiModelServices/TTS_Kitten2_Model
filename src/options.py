"""The options the admin page can change. Each can still start from its environment variable; a saved value wins."""

from engine import DEFAULT_REVISION
from settings import Setting

SETTINGS = [
    Setting("update_check_hours", "Check for updates every (hours)", "float", 6.0, "SERVICE_UPDATE_CHECK_HOURS", 0, 720,
            help="0 = only when you press Check now. The revision is pinned, so this finds only a missing download"),
    Setting("max_inflight", "Calls allowed to wait for the model", "int", 0, "SERVICE_MAX_INFLIGHT", 0, 10000,
            help="Per replica; more get 429. 0 = 4"),
    Setting("cache_size", "Answers kept per replica", "int", 32, "SERVICE_CACHE_SIZE", 0, 100000,
            help="Calls with a seed, sent again for the same text, voice, preset, temperature and seed. Each is at most 1 MB. 0 = off"),
    Setting("model_revision", "Model revision", "text", DEFAULT_REVISION, "SERVICE_MODEL_REVISION", restart=True, blank=False,
            help="The Hub commit of KittenML/kitten-tts-2 (Stellon Labs Community License). After a restart, download it from the Updates card"),
    Setting("device", "Device", "text", "cpu", "SERVICE_DEVICE", restart=True, blank=False,
            help="cpu as shipped. cuda only on a host with an NVIDIA GPU and a CUDA build of torch; compose reserves no GPU"),
    Setting("weights", "Weight variant", "text", "packed", "SERVICE_WEIGHTS", restart=True, blank=False,
            help="packed (954 MB, lossless), emb4 (469 MB, lossy embedding) or full (3.5 GB, plain bf16)"),
    Setting("decoder", "Decoder", "text", "default", "SERVICE_DECODER", restart=True, blank=False,
            help="default (best quality, 459 MB) or student_w4 (39 MB, smaller, not faster)"),
    Setting("max_new_tokens", "Most audio tokens per chunk", "int", 1000, "SERVICE_MAX_NEW_TOKENS", 64, 8000, restart=True,
            help="25 tokens are about one second of audio; the model also sizes each chunk's budget from its text"),
    Setting("warm", "Load the model at start", "bool", True, "SERVICE_WARM", restart=True),
]
