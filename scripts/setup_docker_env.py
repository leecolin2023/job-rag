"""Provision a local generated secret without printing it or overwriting existing config."""
import os
from pathlib import Path
import secrets


path = Path(__file__).resolve().parents[1] / ".env.docker"
try:
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
except FileExistsError:
    print(".env.docker already exists; left unchanged")
else:
    with os.fdopen(fd, "w") as stream:
        stream.write(f"POSTGRES_PASSWORD={secrets.token_hex(32)}\n"
                     "JOB_RAG_API_PORT=8008\nJOB_RAG_MCP_PORT=8009\n"
                     "ADMIN_TOKEN=\nEMBEDDING_MODEL=\nEMBEDDING_API_KEY=\n")
    print("Created .env.docker with a random password and permissions 0600")
