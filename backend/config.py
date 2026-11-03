from dataclasses import dataclass
from pathlib import Path
import os

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
            deadline_seconds=float(os.getenv("REQUEST_DEADLINE_SECONDS", "115")),
            provider_timeout=float(os.getenv("PROVIDER_TIMEOUT_SECONDS", "35")),
            generation_tries=int(os.getenv("GENERATION_TRIES", "2")),
        )
