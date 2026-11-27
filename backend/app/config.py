from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path


@dataclass(slots=True)
class Settings:
    """Runtime settings shared by Colab, cloud and university deployments."""

    project_root: Path = field(default_factory=lambda: Path(__file__).resolve().parents[2])
    database_path: Path | None = None
    catalogue_path: Path | None = None
    auth_mode: str = "dev"
    demo_access_token: str | None = None
    admin_access_token: str | None = None
    firebase_project_id: str | None = None
    reviewer_emails: tuple[str, ...] = ()
    vllm_base_url: str = "http://127.0.0.1:8000/v1"
    vllm_api_key: str = "legalai-local-colab"
    base_model_name: str = "legalai-base"
    lora_model_name: str = "legal-complaint-lora"
    request_timeout_seconds: float = 120.0
    max_concurrent_model_requests: int = 4
    model_queue_timeout_seconds: float = 30.0
    cors_origins: tuple[str, ...] = (
        "https://vidhilens-legal-ai-km.web.app",
        "https://vidhilens-legal-ai-km.firebaseapp.com",
        "https://nyayasetu-legal-ai-km.web.app",
        "https://nyayasetu-legal-ai-km.firebaseapp.com",
        "http://localhost:5173",
        "http://localhost:3000",
        "http://127.0.0.1:5173",
        "http://127.0.0.1:3000",
    )

    def __post_init__(self) -> None:
        if self.database_path is None:
            self.database_path = self.project_root / "backend" / "data" / "legalai.sqlite"
        if self.catalogue_path is None:
            self.catalogue_path = self.project_root / "exports" / "rag_catalogue_v1.json"
        if self.auth_mode not in {"dev", "firebase"}:
            raise ValueError("LEGALAI_AUTH_MODE must be dev or firebase")

    @classmethod
    def from_env(cls) -> "Settings":
        origins = tuple(
            item.strip() for item in os.getenv(
                "LEGALAI_CORS_ORIGINS",
                "https://vidhilens-legal-ai-km.web.app,"
                "https://vidhilens-legal-ai-km.firebaseapp.com,"
                "https://nyayasetu-legal-ai-km.web.app,"
                "https://nyayasetu-legal-ai-km.firebaseapp.com,"
                "http://localhost:5173,http://localhost:3000,"
                "http://127.0.0.1:5173,http://127.0.0.1:3000",
            ).split(",") if item.strip()
        )
        project_root = Path(os.getenv(
            "LEGALAI_PROJECT_ROOT", str(Path(__file__).resolve().parents[2])
        )).expanduser().resolve()
        database = os.getenv("LEGALAI_DATABASE_PATH")
        catalogue = os.getenv("LEGALAI_CATALOGUE_PATH")
        return cls(
            project_root=project_root,
            database_path=Path(database).expanduser().resolve() if database else None,
            catalogue_path=Path(catalogue).expanduser().resolve() if catalogue else None,
            auth_mode=os.getenv("LEGALAI_AUTH_MODE", "dev").strip().lower(),
            demo_access_token=os.getenv("LEGALAI_DEMO_ACCESS_TOKEN") or None,
            admin_access_token=os.getenv("LEGALAI_ADMIN_ACCESS_TOKEN") or None,
            firebase_project_id=os.getenv("FIREBASE_PROJECT_ID") or None,
            reviewer_emails=tuple(email.strip().lower() for email in
                os.getenv("LEGALAI_REVIEWER_EMAILS", "").split(",") if email.strip()),
            vllm_base_url=os.getenv("VLLM_BASE_URL", "http://127.0.0.1:8000/v1").rstrip("/"),
            vllm_api_key=os.getenv("VLLM_API_KEY", "legalai-local-colab"),
            base_model_name=os.getenv("VLLM_BASE_MODEL_NAME", "legalai-base"),
            lora_model_name=os.getenv("VLLM_LORA_MODEL_NAME", "legal-complaint-lora"),
            request_timeout_seconds=float(os.getenv("LEGALAI_REQUEST_TIMEOUT", "120")),
            max_concurrent_model_requests=max(1, int(os.getenv("LEGALAI_MODEL_CONCURRENCY", "4"))),
            model_queue_timeout_seconds=float(os.getenv("LEGALAI_QUEUE_TIMEOUT", "30")),
            cors_origins=origins,
        )
