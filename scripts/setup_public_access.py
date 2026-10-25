"""Provision private-CA IP TLS and a read-only gateway token without displaying secrets.

Generated runtime/public files are sensitive and ignored by Git. Never overwrite
an existing installation; explicit certificate/token rotation needs its own procedure.
"""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import secrets
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("public_ip", type=ipaddress.IPv4Address)
    parser.add_argument("--port", type=int, default=443, help="Public frontend port, not the internal gateway port")
    args = parser.parse_args()
    if not 1 <= args.port <= 65535:
        parser.error("port must be between 1 and 65535")
    root = Path(__file__).resolve().parents[1] / "runtime" / "public"
    if root.exists():
        parser.exit(1, "runtime/public already exists; refusing to overwrite certificates or tokens\n")
    os.umask(0o077)
    root.mkdir(parents=True, mode=0o700)
    token = secrets.token_urlsafe(48)
    (root / "access-token").write_text(token + "\n")
    (root / "auth.conf").write_text(
        'map $http_authorization $jobrag_authorized {\n'
        '    default 0;\n'
        f'    "~^Bearer {token}$" 1;\n'
        '}\n'
    )

    def openssl(*arguments):
        subprocess.run(["openssl", *arguments], cwd=root, check=True,
                       stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)

    openssl("req", "-x509", "-newkey", "rsa:3072", "-nodes", "-sha256", "-days", "3650",
            "-subj", "/CN=Job-RAG Private Root CA", "-keyout", "ca.key", "-out", "ca.crt",
            "-addext", "basicConstraints=critical,CA:TRUE,pathlen:0",
            "-addext", "keyUsage=critical,keyCertSign,cRLSign")
    openssl("req", "-newkey", "rsa:2048", "-nodes", "-sha256", "-subj", f"/CN={args.public_ip}",
            "-keyout", "server.key", "-out", "server.csr")
    (root / "server.ext").write_text(
        "basicConstraints=critical,CA:FALSE\nkeyUsage=critical,digitalSignature,keyEncipherment\n"
        "extendedKeyUsage=serverAuth\n"
        f"subjectAltName=IP:{args.public_ip},IP:127.0.0.1,DNS:localhost\n"
    )
    openssl("x509", "-req", "-in", "server.csr", "-CA", "ca.crt", "-CAkey", "ca.key",
            "-CAcreateserial", "-out", "server.crt", "-days", "365", "-sha256", "-extfile", "server.ext")
    port_suffix = "" if args.port == 443 else f":{args.port}"
    public_url = f"https://{args.public_ip}{port_suffix}/mcp"
    (root / "connection.json").write_text(json.dumps({"url": public_url,
                                                       "gateway_certificate_expires_in_days": 365}, indent=2) + "\n")
    # The CA certificate is public; the token and all private keys remain 0600.
    (root / "ca.crt").chmod(0o644)
    print(f"Provisioned gateway TLS/token for public frontend {public_url}")
    print("Internal gateway trust certificate: runtime/public/ca.crt")
    print("Access token: runtime/public/access-token (secret; share securely)")
    print("Do NOT distribute ca.key, server.key, or auth.conf")


if __name__ == "__main__":
    main()
