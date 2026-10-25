import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///runtime/jobs.db")
    embedding_base_url: str = os.getenv("EMBEDDING_BASE_URL", "https://api.openai.com/v1")
    embedding_api_key: str = os.getenv("EMBEDDING_API_KEY", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "")
    embedding_dimensions: int = int(os.getenv("EMBEDDING_DIMENSIONS", "1536"))
    embedding_version: str = os.getenv("EMBEDDING_VERSION", "v1")
    chat_base_url: str = os.getenv("CHAT_BASE_URL", "https://api.openai.com/v1")
    chat_api_key: str = os.getenv("CHAT_API_KEY", "")
    chat_model: str = os.getenv("CHAT_MODEL", "")
    admin_token: str = os.getenv("ADMIN_TOKEN", "")

    @property
    def semantic_enabled(self):
        return bool(self.embedding_api_key and self.embedding_model)

    @property
    def index_signature(self):
        if not self.semantic_enabled:
            return "lexical:document-v1"
        return (f"{self.embedding_base_url}|{self.embedding_model}|"
                f"{self.embedding_dimensions}|{self.embedding_version}|document-v1")
