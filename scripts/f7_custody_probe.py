"""CI: executa tres reprovacoes F6 em Docker e atesta em outro runner."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from chdevflow.core import generic_cycle
from chdevflow.core.manual_pipeline_runner import Mission, SCHEMA
from chdevflow.core.po_escalation import REPO
from chdevflow.core.po_escalation_attestation import (
    SSH_NAMESPACE, execution_statement, statement_bytes, verify_external_attestation,
)
from chdevflow.core.po_escalation_publication import _eligible_outbox
from chdevflow.core.po_escalation_provenance import create_provenance


def run(*command: str, cwd: Path | None = None, data: bytes | None = None) -> bytes:
    completed = subprocess.run(
        command, cwd=cwd, input=data, capture_output=True, check=False, timeout=20)
    if completed.returncode:
        raise RuntimeError(f"Comando controlado falhou: {command[0]}")
    return completed.stdout


def produce(destination: Path) -> None:
    with TemporaryDirectory(prefix="f7-producer-") as folder:
        root = Path(folder)
        # O conteiner roda como nobody. Somente dados inofensivos ficam visiveis.
        root.chmod(0o755)
        worktree = root / "CH-Lab-F7-Custody"
        worktree.mkdir()
        (worktree / "tests").mkdir()
        (worktree / "candidate.py").write_text("def value():\n    return 1\n", encoding="ascii")
        (worktree / "prompt.txt").write_text("Preserve o resultado 1.", encoding="ascii")
        (worktree / "tests" / "test_value.py").write_text(
            "import sys\nfrom pathlib import Path\nimport unittest\n"
            "sys.path.insert(0, str(Path(__file__).resolve().parents[1]))\n"
            "from candidate import value\n"
            "class Contract(unittest.TestCase):\n"
            "    def test_expected_value(self):\n"
            "        self.assertEqual(value(), 1)\n",
            encoding="ascii")
        run("git", "init", "-b", "f7-custody-probe", cwd=worktree)
        run("git", "remote", "add", "origin", f"https://github.com/{REPO}.git", cwd=worktree)
        run("git", "add", ".", cwd=worktree)
        run("git", "-c", "user.name=F7 custody probe", "-c",
            "user.email=f7-probe@example.invalid", "commit", "-m", "Harmless F7 fixture", cwd=worktree)
        base = run("git", "rev-parse", "HEAD", cwd=worktree).decode("ascii").strip()
        manifest = Mission.from_dict({
            "schema": SCHEMA, "mission_id": "F7-CUSTODY-PROBE", "repository": REPO,
            "issue": 86, "base_sha": base, "worktree": str(worktree),
            "allowed_paths": ["candidate.py"], "prompt_ref": "prompt.txt", "timeout_seconds": 480,
        })
        path = root / "mission.json"
        path.write_bytes(manifest.canonical())
        # Substitui apenas o fornecedor de codigo; Git, F6 e Docker executam de verdade.
        worker = root / "candidate_worker.py"
        worker.write_text(
            "import json\nprint(json.dumps({'status':'SUCCESS',"
            "'response':'```python\\ndef value():\\n    return 2\\n```'}))\n", encoding="ascii")
        with patch.object(generic_cycle, "_executables",
                          return_value=([sys.executable, str(worker)], [sys.executable, "-I"])):
            result = generic_cycle.run_generic_cycle(
                manifest_path=path, evidence=destination, accepted=True, isolated_tests=True)
        if (result.status != "AGUARDANDO_PO" or len(result.attempts) != 3
                or any(row["status"] != "TESTES_REPROVADOS" for row in result.attempts)):
            raise RuntimeError("Sonda nao observou tres reprovacoes efetivas: "
                               + result.status + " " + ",".join(result.findings))


def seal(outbox_path: Path, private_key: Path, public_key: str, producer_sha: str,
         producer_run: str, destination: Path) -> dict:
    outbox = _eligible_outbox(outbox_path)
    statement = execution_statement(outbox, producer_sha=producer_sha, producer_run=producer_run)
    signature = run("ssh-keygen", "-Y", "sign", "-n", SSH_NAMESPACE, "-f", str(private_key),
                    data=statement_bytes(statement)).decode("ascii").replace("\r\n", "\n")
    with destination.open("x", encoding="ascii") as receipt:
        json.dump({"statement": statement, "signature": signature}, receipt)
    return verify_external_attestation(
        destination, outbox, trusted_key=public_key, trusted_producer_sha=producer_sha)


def sign_probe(evidence: Path, public_outputs: Path) -> None:
    outbox = evidence / "escalonamento_po.json"
    if _eligible_outbox(outbox)["mission_id"] != "F7-CUSTODY-PROBE":
        raise ValueError("O emissor da CI aceita somente o dossie da sonda controlada")
    # Esta chave nasce APENAS no job de atestacao, fora do diretorio de artefatos.
    with TemporaryDirectory(prefix="f7-probe-key-") as folder:
        key = Path(folder) / "key"
        run("ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-f", str(key))
        public_key = " ".join(key.with_suffix(".pub").read_text(encoding="ascii").split()[:2])
        public_outputs.mkdir()
        (public_outputs / "f7-probe.pub").write_text(public_key + "\n", encoding="ascii")
        origin = f"github-actions:probe:{os.environ['GITHUB_RUN_ID']}:{os.environ['GITHUB_RUN_ATTEMPT']}"
        receipt = public_outputs / "f7-attestation.json"
        proof = seal(outbox, key, public_key, os.environ["GITHUB_SHA"], origin, receipt)

    with TemporaryDirectory(prefix="f7-probe-tamper-") as folder:
        altered = shutil.copytree(evidence, Path(folder) / "evidence")
        (altered / "attempt-02" / "testes.log").write_text("log adulterado", encoding="ascii")
        altered_outbox = altered / outbox.name
        rewritten = json.loads(altered_outbox.read_text(encoding="utf-8"))
        rewritten["provenance"] = create_provenance(altered)
        altered_outbox.write_text(json.dumps(rewritten), encoding="utf-8")
        try:
            verify_external_attestation(
                receipt, _eligible_outbox(altered_outbox), trusted_key=public_key,
                trusted_producer_sha=os.environ["GITHUB_SHA"])
        except ValueError as exc:
            if str(exc) != "Recibo externo diverge do dossie ou do produtor confiavel":
                raise
        else:
            raise RuntimeError("Dossie adulterado passou apos recalcular hashes locais")
    print("PROBE_REHASHED_TAMPERING_REJECTED")
    print(json.dumps({"status": "PROBE_ATTESTATION_VERIFIED", **proof}, sort_keys=True))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    producer = sub.add_parser("produce")
    producer.add_argument("evidence", type=Path)
    signer = sub.add_parser("sign")
    signer.add_argument("evidence", type=Path)
    signer.add_argument("public_outputs", type=Path)
    args = parser.parse_args()
    if args.command == "produce":
        produce(args.evidence)
    else:
        sign_probe(args.evidence, args.public_outputs)


if __name__ == "__main__":
    main()
