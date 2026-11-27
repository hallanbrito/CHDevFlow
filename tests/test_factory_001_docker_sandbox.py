from __future__ import annotations

import os
from pathlib import Path
import unittest
from unittest.mock import patch

from scripts.factory_001_docker_sandbox import (
    CONTAINER_USER,
    IMAGE_DIGESTS,
    IMAGE_REPOSITORY,
    MEMORY_BYTES,
    PID_LIMIT,
    TMPFS_DEFAULT_SIZE_BYTES,
    TMPFS_SIZE_BYTES,
    WORKSPACE_TARGET,
    DockerSandbox,
    SandboxError,
    _docker_environment,
    _validate_container,
    image_reference,
)


class DockerSandboxUnitTests(unittest.TestCase):
    def test_official_images_are_pinned_by_architecture_digest(self):
        amd64, amd64_platform = image_reference("x86_64")
        arm64, arm64_platform = image_reference("aarch64")

        self.assertEqual(amd64_platform, "linux/amd64")
        self.assertEqual(arm64_platform, "linux/arm64")
        self.assertEqual(amd64, f"{IMAGE_REPOSITORY}@{IMAGE_DIGESTS['amd64']}")
        self.assertEqual(arm64, f"{IMAGE_REPOSITORY}@{IMAGE_DIGESTS['arm64']}")
        self.assertTrue(all("@sha256:" in ref for ref in (amd64, arm64)))

    def test_unknown_architecture_fails_closed(self):
        with self.assertRaisesRegex(SandboxError, "sem digest"):
            image_reference("mips")

    def test_docker_client_drops_fake_tokens_and_auth_config(self):
        fake = "FACTORY001-FAKE-CREDENTIAL-NOT-VALID"
        base = {
            "PATH": "/usr/bin",
            "COPILOT_GITHUB_TOKEN": fake,
            "GH_TOKEN": fake,
            "GITHUB_TOKEN": fake,
            "OPENAI_API_KEY": fake,
            "DOCKER_CONTEXT": "untrusted",
        }

        result = _docker_environment(base, "/tmp/empty-docker-config")

        self.assertEqual(result["PATH"], "/usr/bin")
        self.assertEqual(result["DOCKER_CONFIG"], "/tmp/empty-docker-config")
        self.assertNotIn("DOCKER_CONTEXT", result)
        for name in ("COPILOT_GITHUB_TOKEN", "GH_TOKEN", "GITHUB_TOKEN", "OPENAI_API_KEY"):
            self.assertNotIn(name, result)

    def test_remote_docker_daemon_is_rejected(self):
        with self.assertRaisesRegex(SandboxError, "socket Unix"):
            _docker_environment({"DOCKER_HOST": "tcp://example.invalid:2375"}, "/tmp/config")

    def _valid_inspect(self, workspace: Path) -> dict[str, object]:
        image, _ = image_reference("x86_64")
        return {
            "Config": {
                "Image": image,
                "User": CONTAINER_USER,
                "Env": ["HOME=/tmp", "COPILOT_AUTO_UPDATE=false"],
            },
            "HostConfig": {
                "Privileged": False,
                "CapDrop": ["ALL"],
                "SecurityOpt": ["no-new-privileges=true"],
                "ReadonlyRootfs": True,
                "NetworkMode": "none",
                "PidsLimit": PID_LIMIT,
                "Memory": MEMORY_BYTES,
                "NanoCpus": 1_000_000_000,
                "Tmpfs": {
                    "/tmp": (
                        "rw,nosuid,nodev,noexec,"
                        f"size={TMPFS_DEFAULT_SIZE_BYTES},mode=1777"
                    ),
                    "/var/tmp": (
                        f"rw,nosuid,nodev,size={TMPFS_SIZE_BYTES},mode=1777"
                    ),
                },
            },
            "Mounts": [
                {
                    "Type": "bind",
                    "Source": str(workspace),
                    "Destination": WORKSPACE_TARGET,
                    "RW": False,
                },
            ],
        }

    def test_inspect_accepts_only_the_expected_sandbox_configuration(self):
        with self.subTest("accepted"):
            workspace = Path("/tmp/workspace")
            image, _ = image_reference("x86_64")
            _validate_container(self._valid_inspect(workspace), image, workspace)
            details = self._valid_inspect(workspace)
            details["HostConfig"]["Tmpfs"] = {
                "/tmp": "rw,nosuid,nodev,noexec,size=16m,mode=1777",
                "/var/tmp": "rw,nosuid,nodev,size=512m,mode=1777",
            }
            _validate_container(details, image, workspace)

        cases = (
            ("privileged", {"Privileged": True}),
            ("capabilities", {"CapDrop": []}),
            (
                "seccomp",
                {
                    "SecurityOpt": [
                        "no-new-privileges=true",
                        "seccomp=unconfined",
                    ]
                },
            ),
            (
                "tmpfs flags",
                {
                    "Tmpfs": {
                        "/tmp": "rw,size=16777216,mode=1777",
                        "/var/tmp": "rw,nosuid,nodev,size=536870912,mode=1777",
                    }
                },
            ),
            (
                "extra tmpfs",
                {
                    "Tmpfs": {
                        "/tmp": "rw,nosuid,nodev,noexec,size=16777216,mode=1777",
                        "/var/tmp": "rw,nosuid,nodev,size=536870912,mode=1777",
                        "/var/cache": "rw,nosuid,nodev,size=536870912,mode=1777",
                    }
                },
            ),
            ("rootfs", {"ReadonlyRootfs": False}),
            ("network", {"NetworkMode": "bridge"}),
            ("pids", {"PidsLimit": 0}),
            ("memory", {"Memory": 0}),
            ("cpu", {"NanoCpus": 0}),
        )
        for label, change in cases:
            with self.subTest(label=label):
                workspace = Path("/tmp/workspace")
                details = self._valid_inspect(workspace)
                details["HostConfig"].update(change)
                with self.assertRaises(SandboxError):
                    _validate_container(
                        details, image_reference("x86_64")[0], workspace
                    )

    def test_inspect_rejects_extra_mounts_and_credential_environment(self):
        workspace = Path("/tmp/workspace")
        image, _ = image_reference("x86_64")
        details = self._valid_inspect(workspace)
        details["Mounts"].append({"Type": "bind", "Source": "/home/user"})
        with self.assertRaisesRegex(SandboxError, "somente o bind do workspace"):
            _validate_container(details, image, workspace)

        details = self._valid_inspect(workspace)
        details["Config"]["Env"].append("COPILOT_GITHUB_TOKEN=fake")
        with self.assertRaisesRegex(SandboxError, "Credencial"):
            _validate_container(details, image, workspace)

    def test_missing_docker_blocks_before_any_execution(self):
        with patch("scripts.factory_001_docker_sandbox.shutil.which", return_value=None):
            with DockerSandbox() as sandbox:
                with self.assertRaisesRegex(SandboxError, "sem fallback"):
                    sandbox.preflight()

    def test_invalid_daemon_endpoint_cleans_temporary_config(self):
        with patch(
            "scripts.factory_001_docker_sandbox.tempfile.TemporaryDirectory"
        ) as temporary_directory:
            temporary_directory.return_value.name = "/tmp/empty-docker-config"
            sandbox = DockerSandbox()
            with patch.dict(os.environ, {"DOCKER_HOST": "tcp://example.invalid:2375"}):
                with self.assertRaisesRegex(SandboxError, "socket Unix"):
                    sandbox.__enter__()

            temporary_directory.return_value.cleanup.assert_called_once()
            self.assertIsNone(sandbox._docker_config)


@unittest.skipUnless(
    os.environ.get("CH_FACTORY001_DOCKER_INTEGRATION") == "1",
    "A prova real exige daemon Docker Linux; habilitada no job dedicado de CI.",
)
class DockerSandboxIntegrationTests(unittest.TestCase):
    def test_official_cli_and_negative_sandbox_controls(self):
        from scripts.factory_001_docker_sandbox import run_acceptance
        import json

        fake = "FACTORY001-FAKE-CREDENTIAL-NOT-VALID"
        extra_environment = {
            name: fake
            for name in (
                "COPILOT_GITHUB_TOKEN",
                "GH_TOKEN",
                "GITHUB_TOKEN",
                "OPENAI_API_KEY",
            )
        }
        with DockerSandbox(extra_environment=extra_environment) as sandbox:
            evidence = run_acceptance(sandbox)

        print("FACTORY001_DOCKER_EVIDENCE " + json.dumps(evidence, sort_keys=True))
        self.assertEqual(evidence["status"], "PASS")
        self.assertFalse(evidence["credentials_used"])
        self.assertEqual(evidence["model_calls"], 0)
        self.assertTrue(evidence["timeout_container_removed"])
        self.assertTrue(evidence["cancelled_container_removed"])


if __name__ == "__main__":
    unittest.main()
