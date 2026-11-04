from dataclasses import dataclass
from pathlib import Path
import os
import math

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent


@dataclass(frozen=True)
class Settings:
    storage: Path = ROOT / "storage"
    test_mode: bool = False
    gemini_key: str = ""
    gemini_model: str = ""
    embedding_model: str = ""
    package_module: str = "model_package"
    artifacts: Path = ROOT / "model_artifacts"
    model_base: Path | None = None
    model_checkpoint: Path | None = None
    model_manifest: Path | None = None
    agent_gates_path: Path | None = None
    model_loader: str = "auto"
    generation_rpm: float = 0
    embedding_rpm: float = 0
    provider_retries: int = 1
    max_backoff_seconds: float = 3
    embedding_batch_size: int = 16
    semantic_duplicate_threshold: float = 0.92
    deadline_seconds: float = 115
    provider_timeout: float = 35
    generation_tries: int = 2
    max_pdf_bytes: int = 15 * 1024 * 1024

    def __post_init__(self):
        if not 0 < self.deadline_seconds <= 120:
            raise ValueError("REQUEST_DEADLINE_SECONDS must be in (0, 120]")
        if not 0 < self.provider_timeout <= self.deadline_seconds:
            raise ValueError("PROVIDER_TIMEOUT_SECONDS must fit the request deadline")
        if not 1 <= self.generation_tries <= 3:
            raise ValueError("GENERATION_TRIES must be 1..3")
        if self.model_loader not in {"auto", "package", "coverage_v2"}:
            raise ValueError("MODEL_LOADER must be auto, package or coverage_v2")
        if not 1 <= self.embedding_batch_size <= 80 or not 0 <= self.provider_retries <= 2:
            raise ValueError("Invalid provider batching/retry settings")
        if any(not math.isfinite(x) or x < 0 for x in (self.generation_rpm, self.embedding_rpm, self.max_backoff_seconds)):
            raise ValueError("Rate/backoff settings must be nonnegative")
        if not 0 < self.semantic_duplicate_threshold <= 1:
            raise ValueError("Invalid semantic dedup threshold")

    @classmethod
    def from_env(cls):
        load_dotenv(ROOT / ".env", override=False)
        fake = os.getenv("TRAINER_TEST_MODE", "false").lower()
        if fake not in {"true", "false"}:
            raise ValueError("TRAINER_TEST_MODE must be true or false")
        return cls(
            storage=Path(os.getenv("TRAINER_STORAGE", str(ROOT / "storage"))).resolve(),
            test_mode=fake == "true",
            gemini_key=os.getenv("GEMINI_API_KEY", ""),
            gemini_model=os.getenv("GEMINI_MODEL", ""),
            embedding_model=os.getenv("GEMINI_EMBEDDING_MODEL", ""),
            package_module=os.getenv("MODEL_PACKAGE_MODULE", "model_package"),
            artifacts=Path(os.getenv("MODEL_ARTIFACT_DIR", str(ROOT / "model_artifacts"))).resolve(),
            model_base=Path(os.environ["MODEL_BASE_PATH"]).resolve() if os.getenv("MODEL_BASE_PATH") else None,
            model_checkpoint=Path(os.environ["MODEL_CHECKPOINT_DIR"]).resolve() if os.getenv("MODEL_CHECKPOINT_DIR") else None,
            model_manifest=Path(os.environ["MODEL_MANIFEST_PATH"]).resolve() if os.getenv("MODEL_MANIFEST_PATH") else None,
            agent_gates_path=Path(os.environ["MODEL_AGENT_GATES_PATH"]).resolve() if os.getenv("MODEL_AGENT_GATES_PATH") else None,
            model_loader=os.getenv("MODEL_LOADER", "auto"),
            generation_rpm=float(os.getenv("GEMINI_GENERATION_RPM", "12")),
            embedding_rpm=float(os.getenv("GEMINI_EMBEDDING_RPM", "60")),
            provider_retries=int(os.getenv("GEMINI_PROVIDER_RETRIES", "1")),
            max_backoff_seconds=float(os.getenv("GEMINI_MAX_BACKOFF_SECONDS", "3")),
            embedding_batch_size=int(os.getenv("GEMINI_EMBEDDING_BATCH_SIZE", "16")),
            semantic_duplicate_threshold=float(os.getenv("QUESTION_DEDUP_THRESHOLD", "0.92")),
            deadline_seconds=float(os.getenv("REQUEST_DEADLINE_SECONDS", "115")),
            provider_timeout=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "35")),
            generation_tries=int(os.getenv("GENERATION_TRIES", "2")),
        )
