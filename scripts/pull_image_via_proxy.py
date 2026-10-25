"""Load a public Docker Hub image using the shell proxy, without changing dockerd.

Usage: .venv/bin/python scripts/pull_image_via_proxy.py python:3.12-slim
Requires httpx (already a project dependency) and passwordless sudo for docker load.
Downloaded bytes are verified against registry SHA256 digests before loading.
"""
import gzip
import hashlib
import json
from pathlib import Path
import platform
import shutil
import subprocess
import sys
import tarfile
import tempfile

import httpx


def main():
    reference = sys.argv[1]
    repository, tag = reference.rsplit(":", 1)
    if "/" not in repository:
        repository = "library/" + repository
    if not all(part.replace("-", "").replace("_", "").replace(".", "").isalnum() for part in repository.split("/")):
        raise ValueError("Only public Docker Hub repository names are supported")
    registry = "https://registry-1.docker.io/v2/" + repository
    accepts = ", ".join(["application/vnd.oci.image.index.v1+json", "application/vnd.docker.distribution.manifest.list.v2+json",
                         "application/vnd.oci.image.manifest.v1+json", "application/vnd.docker.distribution.manifest.v2+json"])
    with httpx.Client(timeout=120, follow_redirects=True) as client:
        auth = client.get("https://auth.docker.io/token", params={"service": "registry.docker.io", "scope": f"repository:{repository}:pull"})
        auth.raise_for_status()
        headers = {"Authorization": "Bearer " + auth.json()["token"], "Accept": accepts}

        def manifest(ref):
            response = client.get(registry + "/manifests/" + ref, headers=headers)
            response.raise_for_status()
            if ref.startswith("sha256:") and hashlib.sha256(response.content).hexdigest() != ref.split(":")[1]:
                raise ValueError("Manifest digest mismatch")
            return response.json()

        image = manifest(tag)
        if "manifests" in image:
            arch = {"x86_64": "amd64", "aarch64": "arm64"}.get(platform.machine(), platform.machine())
            selected = next(item for item in image["manifests"] if item.get("platform", {}).get("os") == "linux" and item["platform"].get("architecture") == arch)
            image = manifest(selected["digest"])
        root = Path(tempfile.mkdtemp(prefix="jobrag-image-", dir="/tmp/opencode"))
        try:
            def blob(digest, destination):
                checksum = hashlib.sha256()
                with client.stream("GET", registry + "/blobs/" + digest, headers=headers) as response:
                    response.raise_for_status()
                    with destination.open("wb") as output:
                        for block in response.iter_bytes():
                            checksum.update(block)
                            output.write(block)
                if "sha256:" + checksum.hexdigest() != digest:
                    raise ValueError("Blob digest mismatch")

            config_name = image["config"]["digest"].split(":")[1] + ".json"
            blob(image["config"]["digest"], root / config_name)
            paths = []
            for number, layer in enumerate(image["layers"]):
                print(f"Downloading {reference} layer {number + 1}/{len(image['layers'])}", flush=True)
                compressed = root / "layer.download"
                blob(layer["digest"], compressed)
                layer_path = f"{number}/layer.tar"
                (root / str(number)).mkdir()
                with compressed.open("rb") as stream:
                    magic = stream.read(2)
                if magic == b"\x1f\x8b":
                    with gzip.open(compressed, "rb") as stream, (root / layer_path).open("wb") as output:
                        shutil.copyfileobj(stream, output)
                else:
                    shutil.copyfile(compressed, root / layer_path)
                compressed.unlink()
                paths.append(layer_path)
            (root / "manifest.json").write_text(json.dumps([{"Config": config_name, "RepoTags": [reference], "Layers": paths}]))
            archive = root / "image.tar"
            with tarfile.open(archive, "w") as tar:
                for name in [config_name, "manifest.json"] + paths:
                    tar.add(root / name, arcname=name)
            subprocess.run(["sudo", "-n", "docker", "load", "-i", str(archive)], check=True)
        finally:
            # This is our own uniquely created temporary directory, never a user-supplied path.
            shutil.rmtree(root)


if __name__ == "__main__":
    main()
