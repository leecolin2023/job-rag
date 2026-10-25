"""Enter a fresh Bailian key in your own terminal, without shell-history/log leakage."""
import argparse
import getpass
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--host", required=True, help="HTTPS workspace API host; never put an API key here")
    parser.add_argument("--empty-key", action="store_true", help="Provision host-only template; no interactive secret input")
    parser.add_argument("--set-key", action="store_true", help="Explicitly replace only the API key in an existing local configuration")
    args = parser.parse_args()
    from urllib.parse import urlsplit
    url = urlsplit(args.host)
    if url.scheme != "https" or not url.hostname or url.path not in {"", "/"} or url.query or url.fragment or url.username:
        parser.error("Use a real HTTPS API host without paths or credentials")
    path = Path(__file__).resolve().parents[1] / ".env.experiments"
    if path.exists() and not args.set_key:
        parser.exit(1, ".env.experiments already exists; edit it locally rather than overwriting existing credentials\n")
    if args.set_key and (not path.exists() or args.empty_key):
        parser.error("--set-key requires an existing file and interactive secret entry")
    key = "" if args.empty_key else getpass.getpass("Fresh Bailian API key (hidden input): ").strip()
    if not args.empty_key and not key:
        parser.error("Key cannot be empty")
    if any(char in key for char in ["\n", "\r", "'", '"']):
        parser.error("Invalid key characters")
    if args.set_key:
        lines = path.read_text().splitlines()
        if sum(line.startswith("BAILIAN_API_KEY=") for line in lines) != 1:
            parser.error("Expected exactly one BAILIAN_API_KEY entry; edit this file manually")
        from tempfile import NamedTemporaryFile
        with NamedTemporaryFile(mode="w", dir=path.parent, prefix=".env.experiments.", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write("\n".join(f"BAILIAN_API_KEY={key}" if line.startswith("BAILIAN_API_KEY=") else line for line in lines) + "\n")
        temporary.chmod(0o600)
        os.replace(temporary, path)
        print("Updated only the local API key (0600); key not displayed")
        return
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as stream:
        stream.write(f"BAILIAN_API_HOST={args.host.rstrip('/')}\nBAILIAN_API_KEY={key}\n"
                     "BAILIAN_EMBEDDING_MODEL=qwen3.7-text-embedding-flash\n"
                     "BAILIAN_EMBEDDING_DIMENSIONS=1024\nBAILIAN_RERANK_MODEL=qwen3.7-text-rerank\n"
                     "BAILIAN_BATCH_SIZE=20\nBAILIAN_TRUST_ENV=false\n")
    print("Created .env.experiments (0600); key not displayed")


if __name__ == "__main__":
    main()
