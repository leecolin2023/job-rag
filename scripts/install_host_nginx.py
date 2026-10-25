"""Install an isolated /mcp route into this server's inspected existing IP TLS site.

Preserve the original file in /etc/nginx/jobrag-backups, validate nginx config and
reload gracefully. This script is intentionally specific to this server, not a
generic site replacement. It never prints certificate private keys or tokens.
"""
from datetime import datetime, timezone
from pathlib import Path
import subprocess
import uuid


def sudo(*args):
    subprocess.run(["sudo", "-n", *args], check=True)


root = Path(__file__).resolve().parents[1]
site = Path("/etc/nginx/sites-enabled/openchamber").resolve(strict=True)
source = site.read_text()
marker = "    include /etc/nginx/snippets/job-rag-mcp.conf;"
if marker in source:
    raise SystemExit("Job-RAG include already installed; existing configuration left unchanged")
anchor = "    client_max_body_size 200m;\n"
if source.count(anchor) != 1 or source.count("server_name 106.55.35.201;") != 2:
    raise SystemExit("Existing site differs from the inspected deployment; refusing to modify")
snippet = Path("/etc/nginx/snippets/job-rag-mcp.conf")
if snippet.exists():
    raise SystemExit("Target snippet already exists; refusing to overwrite")
staged = root / "runtime" / "host-nginx-staged.conf"
staged.write_text(source.replace(anchor, anchor + "\n" + marker + "\n", 1))
backup_name = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ") + "-" + uuid.uuid4().hex[:8]
backup = Path("/etc/nginx/jobrag-backups") / f"{backup_name}.conf"
sudo("install", "-d", "-m", "700", str(backup.parent))
sudo("cp", "-a", str(site), str(backup))
if site.read_text() != source:
    raise SystemExit("Site changed during provisioning; refusing to overwrite")
sudo("install", "-m", "644", str(root / "deploy" / "host-nginx-mcp.conf"), str(snippet))
try:
    sudo("install", "-m", "644", str(staged), str(site))
    sudo("nginx", "-t")
    sudo("systemctl", "reload", "nginx")
except subprocess.CalledProcessError:
    sudo("cp", "-a", str(backup), str(site))
    sudo("nginx", "-t")
    sudo("systemctl", "reload", "nginx")
    raise
print("Installed https://106.55.35.201/mcp (token required)")
print(f"Original site backup: {backup}")
