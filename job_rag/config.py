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
    embedding_api_format: str = os.getenv("EMBEDDING_API_FORMAT", "openai")
    embedding_batch_size: int = int(os.getenv("EMBEDDING_BATCH_SIZE", "20"))
    embedding_send_dimensions: bool = os.getenv("EMBEDDING_SEND_DIMENSIONS", "false").lower() == "true"
    embedding_trust_env: bool = os.getenv("EMBEDDING_TRUST_ENV", "false").lower() == "true"
    chunking_strategy: str = os.getenv("CHUNKING_STRATEGY", "section_typed")
    chunk_size: int = int(os.getenv("CHUNK_SIZE", "1100"))
    chunk_budget_unit: str = os.getenv("CHUNK_BUDGET_UNIT", "chars")
    tokenizer_path: str = os.getenv("TOKENIZER_PATH", "")
    chat_base_url: str = os.getenv("CHAT_BASE_URL", "https://api.openai.com/v1")
    chat_api_key: str = os.getenv("CHAT_API_KEY", "")
    chat_model: str = os.getenv("CHAT_MODEL", "")
    admin_token: str = os.getenv("ADMIN_TOKEN", "")

    @property
    def semantic_enabled(self):
        return bool(self.embedding_api_key and self.embedding_model)

    @property
    def index_signature(self):
        from .chunking import CHUNKING_VERSION, PARSER_VERSION
        from .preprocessing.normalize import digest
        tokenizer_hash = "none"
        if self.chunk_budget_unit == "tokens":
            from pathlib import Path
            import hashlib
            tokenizer_hash = hashlib.sha256(Path(self.tokenizer_path).read_bytes()).hexdigest()
        document_signature = digest({"parser": PARSER_VERSION, "chunker": CHUNKING_VERSION,
                                     "strategy": self.chunking_strategy, "size": self.chunk_size,
                                     "budget_unit": self.chunk_budget_unit, "tokenizer": tokenizer_hash})[:20]
        if not self.semantic_enabled:
            return f"lexical:{document_signature}"
        return (f"{self.embedding_base_url}|{self.embedding_model}|"
                f"{self.embedding_dimensions}|{self.embedding_version}|{self.embedding_api_format}|{document_signature}")
