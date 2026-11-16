"""E3-C0: dossie de consumo REAL do TAR E3-B, NAO e outbox V1.

Nao concede publicacao. Entradas: tres relatórios produzidos pelo mesmo
contêiner Docker, executado sem credenciais e sem rede, arquivo TAR atestado
e identidade do run GitHub. Saida: manifesto fechado e validável offline.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re

SCHEMA = "CHDEVFLOW-F7-E3C0-CONSUMER/1"
EXECUTOR_SCHEMA = "CHDEVFLOW-F7-E3B-EXECUTOR/1"
SOURCE_SHA = "389bcc61342cbcdd3183e291a18eef42ad78f488"
SOURCE_RUN = 43887485901
SOURCE_ARTIFACT_ID = 14235142079
TAR_SHA256 = "b7b912afad6422f134501fd997eb13cc1bf70de8aa88de43e0988841a84b0242"
IMAGE_ID = "sha256:e0c1bddedb8763803370d0a02b9d05371a30d9c4c82f0fe0b8813bb3b5b9f7ed"
HEX40 = re.compile(r"^[0-9a-f]{40}$")
HEX64 = re.compile(r"^[0-9a-f]{64}$")
REPORTS = {
    "self": ("SELF_CHECK_OK", None),
    "pass": ("TESTS_PASS", 0),
    "fail": ("TESTS_FAILED", 1),
}


def read_report(path: Path, expected_status: str, code: int | None) -> dict:
    if path.is_symlink() or not path.is_file() or path.stat().st_size > 20_000:
        raise ValueError("Relatorio E3C0 ausente ou inseguro")
    item = json.loads(path.read_bytes())
    if not isinstance(item, dict) or item.get("schema") != EXECUTOR_SCHEMA:
        raise ValueError("Schema executor divergente")
    if item.get("status") != expected_status:
        raise ValueError("Resultado real diferente do esperado")
    if code is not None and (type(item.get("tests_exit_code")) is not int
                             or item["tests_exit_code"] != code):
        raise ValueError("Exit status dos testes divergente")
    if code is None and (type(item.get("uid")) is not int or item["uid"] != 65534
                         or type(item.get("gid")) is not int or item["gid"] != 65534):
        raise ValueError("Executor nao rodou com usuario do sandbox")
    return item


def digest_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_manifest(root: Path, consumer_sha: str, consumer_run: int) -> dict:
    if not HEX40.fullmatch(consumer_sha) or type(consumer_run) is not int or consumer_run < 1:
        raise ValueError("Identidade de consumidor invalida")
    reports = {}
    for key, (status, code) in REPORTS.items():
        path = root / (key + ".json")
        read_report(path, status, code)
        reports[key] = {"sha256": digest_file(path), "status": status}
    tar = root / "f7-e3b-executor.tar"
    if digest_file(tar) != TAR_SHA256:
        raise ValueError("TAR de executor diferente do artefato atestado")
    image = (root / "f7-e3b-image-id.txt").read_text(encoding="ascii").strip()
    if image != IMAGE_ID:
        raise ValueError("Identidade da imagem divergente")
    return {
        "schema": SCHEMA,
        "source_run": SOURCE_RUN,
        "source_artifact_id": SOURCE_ARTIFACT_ID,
        "source_commit": SOURCE_SHA,
        "tar_sha256": TAR_SHA256,
        "image_id": IMAGE_ID,
        "consumer_commit": consumer_sha,
        "consumer_run": consumer_run,
        "reports": reports,
        "authorization": "E3C0_LAB_ONLY_NO_AGENTS_NO_OUTBOX_NO_POST",
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("operation", choices=("emit", "verify"))
    ap.add_argument("--root", type=Path, required=True)
    ap.add_argument("--consumer-sha", required=True)
    ap.add_argument("--consumer-run", type=int, required=True)
    args = ap.parse_args()
    current = build_manifest(args.root, args.consumer_sha, args.consumer_run)
    path = args.root / "e3c0-manifest.json"
    canonical = json.dumps(current, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=True) + "\n"
    if args.operation == "emit":
        if path.exists():
            raise ValueError("Manifesto E3-C0 ja existe")
        path.write_text(canonical, encoding="ascii")
        print("E3C0_MANIFEST_EMITTED:" + hashlib.sha256(canonical.encode()).hexdigest())
    else:
        if path.read_bytes() != canonical.encode("ascii"):
            raise ValueError("Manifesto E3-C0 alterado ou nao corresponde ao executor")
        print("E3C0_MANIFEST_VERIFIED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
