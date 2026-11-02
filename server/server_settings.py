"""Environment-backed server configuration and data paths; no process-wide mutable state."""

import os
import shlex
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
MAX_SEED = 2**48
MAX_PROMPT = 20000
DURATION_RANGE = (2.0, 15.0)
HISTORY_KINDS = {
    "video": ("t2v", "i2v", "fl2v", "r2v", "upscale"),
    "image": ("t2i", "i2i"),
    "music": ("t2m",),
    "3d": ("i23d",),
    "speech": ("tts",),
    "asr": ("asr",),
    "llm": ("llm",),
}


@dataclass(frozen=True)
class ServerSettings:
    comfyui: Path | None
    data: Path
    web_dist: Path
    host: str = "0.0.0.0"
    port: int = 8190
    audio_cpp_dir: Path | None = None
    audio_cpp_port: int = 8191
    audio_cpp_threads: int = 8
    audio_cpp_timeout: int = 1800
    audio_cpp_instances: int = 1
    strata_dir: Path | None = None
    strata_config: Path | None = None
    strata_port: int = 8192
    strata_parallel: int = 8
    strata_concurrency: int = 16
    strata_timeout: int = 1800
    comfy_url: str | None = None
    workflows: Path = ROOT / "workflows"
    comfy_args: tuple = ("--enable-triton-backend", "--use-sage-attention")

    @classmethod
    def from_env(cls):
        return cls(
            comfy_url=os.environ.get("H3_COMFY_URL"),
            workflows=Path(os.environ.get("H3_WORKFLOWS", ROOT / "workflows")).expanduser().resolve(),
            comfyui=Path(os.environ["H3_COMFYUI"])
            if os.environ.get("H3_COMFYUI")
            else None,
            data=Path(os.environ.get("H3_DATA", ROOT / "data")).resolve(),
            web_dist=Path(os.environ.get("H3_WEB_DIST", ROOT / "web_dist")).resolve(),
            host=os.environ.get("H3_HOST", "0.0.0.0"),
            port=int(os.environ.get("H3_PORT", "8190")),
            audio_cpp_dir=Path(os.environ['H3_AUDIOCPP_DIR']).expanduser().resolve() if os.environ.get('H3_AUDIOCPP_DIR') else None,
            audio_cpp_port=int(os.environ.get('H3_AUDIOCPP_PORT', '8191')),
            audio_cpp_threads=int(os.environ.get('H3_AUDIOCPP_THREADS', '8')),
            audio_cpp_timeout=int(os.environ.get('H3_AUDIOCPP_TIMEOUT', '1800')),
            audio_cpp_instances=int(os.environ.get('H3_AUDIOCPP_INSTANCES', '1')),
            strata_dir=Path(os.environ["H3_STRATA_DIR"]).expanduser() if os.environ.get("H3_STRATA_DIR") else None,
            strata_config=Path(os.environ["H3_STRATA_CONFIG"]).expanduser() if os.environ.get("H3_STRATA_CONFIG") else None,
            strata_port=int(os.environ.get("H3_STRATA_PORT", "8192")),
            strata_parallel=int(os.environ.get("H3_STRATA_PARALLEL", "8")),
            strata_concurrency=int(os.environ.get("H3_STRATA_CONCURRENCY", "16")),
            strata_timeout=int(os.environ.get("H3_STRATA_TIMEOUT", "1800")),
            comfy_args=tuple(
                shlex.split(
                    os.environ.get(
                        "H3_COMFY_ARGS", "--enable-triton-backend --use-sage-attention"
                    )
                )
            ),
        )

    @property
    def videos(self):
        return self.data / "videos"

    @property
    def pictures(self):
        return self.data / "pictures"

    @property
    def music(self):
        return self.data / "music"

    @property
    def audio_root(self):
        return self.audio_cpp_dir or (self.comfyui.parent / "audio_cpp" if self.comfyui else self.data / "audio_cpp_runtime")

    @property
    def speech(self):
        return self.data / "speech"

    @property
    def transcripts(self):
        return self.data / "transcripts"

    @property
    def llm(self):
        return self.data / "llm"

    @property
    def thumbs(self):
        return self.data / "thumbs"

    @property
    def uploads(self):
        return self.data / "uploads"

    @property
    def models3d(self):
        return self.data / "models3d"

    def prepare_directories(self):
        for path in (
            self.data,
            self.videos,
            self.pictures,
            self.music,
            self.thumbs,
            self.uploads,
            self.models3d,
            self.speech,
            self.transcripts,
            self.llm,
        ):
            path.mkdir(parents=True, exist_ok=True)
