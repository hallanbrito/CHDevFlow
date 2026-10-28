"""Testes de validação de empacotamento, wheel autossuficiente e dependências (AUD-GERAL-P0-02).

Garante que os pacotes chdevflow, ch-sentinela e ch-control-center distribuem todos
os recursos estáticos, templates, fixtures, profiles e dependências declaradas,
eliminando dependências incidentais da árvore-fonte ou hacks de PYTHONPATH.
"""
from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
import zipfile

# Garante acesso aos pacotes mesmo em execução direta
_SRC = Path(__file__).resolve().parent.parent / "src"
_CC_SRC = Path(__file__).resolve().parent.parent / "apps" / "control-center" / "src"
_SENT_SRC = Path(__file__).resolve().parent.parent / "apps" / "bootstrap" / "sentinela" / "src"
for p in (_SRC, _CC_SRC, _SENT_SRC):
    if p.is_dir() and str(p) not in sys.path:
        sys.path.insert(0, str(p))

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib  # type: ignore

from chdevflow.core.init import get_templates_dir, run_init
from chdevflow.core.project import create_project
from chdevflow.core.status import ESSENTIAL_DOCS


class TestPackagingWheelAudit(unittest.TestCase):
    """Bateria de testes de integridade de empacotamento para a missão AUD-GERAL-P0-02."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.control_center_root = cls.repo_root / "apps" / "control-center"
        cls.sentinela_root = cls.repo_root / "apps" / "bootstrap" / "sentinela"

    def test_chdevflow_pyproject_dependencies_and_package_data(self) -> None:
        """Comprova que pyproject.toml raiz inclui ch-sentinela e package-data com templates."""
        pyproj_path = self.repo_root / "pyproject.toml"
        self.assertTrue(pyproj_path.is_file(), "pyproject.toml raiz deve existir")

        with open(pyproj_path, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        dependencies = project.get("dependencies", [])
        self.assertTrue(
            any("ch-sentinela" in dep for dep in dependencies),
            f"ch-sentinela deve estar declarado em dependencies do chdevflow: {dependencies}",
        )

        setuptools_cfg = data.get("tool", {}).get("setuptools", {})
        self.assertTrue(
            setuptools_cfg.get("include-package-data", False),
            "include-package-data deve estar ativo em tool.setuptools",
        )
        pkg_data = setuptools_cfg.get("package-data", {}).get("chdevflow", [])
        self.assertTrue(
            any("templates" in pattern for pattern in pkg_data),
            f"Templates devem estar declarados em package-data: {pkg_data}",
        )

    def test_control_center_pyproject_dependencies_and_package_data(self) -> None:
        """Comprova que pyproject.toml do Control Center declara dependência de ch-sentinela e recursos."""
        pyproj_path = self.control_center_root / "pyproject.toml"
        self.assertTrue(pyproj_path.is_file(), "pyproject.toml do control-center deve existir")

        with open(pyproj_path, "rb") as f:
            data = tomllib.load(f)

        project = data.get("project", {})
        dependencies = project.get("dependencies", [])
        self.assertTrue(
            any("ch-sentinela" in dep for dep in dependencies),
            f"ch-sentinela deve constar em dependencies do ch-control-center: {dependencies}",
        )

        setuptools_cfg = data.get("tool", {}).get("setuptools", {})
        self.assertTrue(
            setuptools_cfg.get("include-package-data", False),
            "include-package-data deve estar ativo no control center",
        )
        pkg_data = setuptools_cfg.get("package-data", {}).get("ch_control_center", [])
        self.assertTrue(
            any("templates" in p for p in pkg_data),
            f"Templates devem estar em package-data do control center: {pkg_data}",
        )
        self.assertTrue(
            any("static" in p for p in pkg_data),
            f"Static deve estar em package-data do control center: {pkg_data}",
        )
        self.assertTrue(
            any("fixtures" in p for p in pkg_data),
            f"Fixtures devem estar em package-data do control center: {pkg_data}",
        )
        self.assertTrue(
            any("profiles" in p for p in pkg_data),
            f"Profiles devem estar em package-data do control center: {pkg_data}",
        )

    def test_chdevflow_templates_accessible_and_complete(self) -> None:
        """Garante que get_templates_dir resolve diretório canônico contendo todos os modelos essenciais."""
        tpl_dir = get_templates_dir()
        self.assertTrue(tpl_dir.is_dir(), f"Diretório de templates deve ser válido: {tpl_dir}")

        # Verifica presença de arquivos fundamentais
        self.assertTrue((tpl_dir / "AGENTS.md").is_file(), "AGENTS.md deve existir nos templates")
        self.assertTrue((tpl_dir / "docs" / "PROJETO.md").is_file(), "docs/PROJETO.md deve existir")
        self.assertTrue((tpl_dir / "docs" / "STATUS.md").is_file(), "docs/STATUS.md deve existir")
        self.assertTrue((tpl_dir / "docs" / "CH" / "DECISOES.md").is_file(), "DECISOES.md deve existir")
        self.assertTrue((tpl_dir / "docs" / "CH" / "PROTOCOLO_AGENTES.md").is_file(), "PROTOCOLO_AGENTES.md deve existir")
        self.assertTrue((tpl_dir / "docs" / "CH" / "RELATORIO-UNIVERSAL-CH.md").is_file(), "RELATORIO-UNIVERSAL-CH.md deve existir")
        self.assertTrue(
            (tpl_dir / ".github" / "ISSUE_TEMPLATE" / "fatia-w.md").is_file(),
            "fatia-w.md deve existir nos templates",
        )
        self.assertTrue(
            (tpl_dir / ".github" / "PULL_REQUEST_TEMPLATE.md").is_file(),
            "PULL_REQUEST_TEMPLATE.md deve existir nos templates",
        )

    def test_run_init_in_clean_directory_creates_all_essential_docs(self) -> None:
        """Verifica que create_project opera com sucesso a partir de templates empacotados."""
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = create_project("NovoProjeto", base_dir=Path(tmpdir))

            for doc in ESSENTIAL_DOCS:
                doc_path = dest / doc
                self.assertTrue(
                    doc_path.is_file(),
                    f"Documento essencial '{doc}' deve ter sido criado em instalação limpa",
                )

    def test_control_center_package_resources_resolution(self) -> None:
        """Comprova que ch_control_center resolve templates, static, fixtures e profiles."""
        cc_pkg = self.control_center_root / "src" / "ch_control_center"
        tpl_dir = cc_pkg / "templates"
        static_dir = cc_pkg / "static"
        fixtures_dir = cc_pkg / "fixtures"
        profiles_dir = cc_pkg / "profiles"

        self.assertTrue(tpl_dir.is_dir(), f"Templates do painel devem existir: {tpl_dir}")
        self.assertTrue((tpl_dir / "dashboard.html").is_file(), "dashboard.html deve existir")
        self.assertTrue((tpl_dir / "missions.html").is_file(), "missions.html deve existir")
        self.assertTrue((tpl_dir / "graph.html").is_file(), "graph.html deve existir")
        self.assertTrue((tpl_dir / "student.html").is_file(), "student.html deve existir")

        self.assertTrue(static_dir.is_dir(), f"Static do painel deve existir: {static_dir}")
        self.assertTrue((static_dir / "css" / "styles.css").is_file(), "styles.css deve existir")
        self.assertTrue((static_dir / "js" / "app.js").is_file(), "app.js deve existir")

        self.assertTrue(fixtures_dir.is_dir(), f"Fixtures do painel devem existir: {fixtures_dir}")
        self.assertTrue(
            (fixtures_dir / "demo_project_snapshot.json").is_file(),
            "demo_project_snapshot.json deve existir nas fixtures empacotadas",
        )

        self.assertTrue(profiles_dir.is_dir(), f"Profiles do painel devem existir: {profiles_dir}")
        self.assertTrue((profiles_dir / "chdevflow.json").is_file(), "chdevflow.json profile deve existir")
        self.assertTrue((profiles_dir / "hallancraft.json").is_file(), "hallancraft.json profile deve existir")

        # Se dependências web estiverem no ambiente, valida execução dos serviços
        try:
            import fastapi  # noqa: F401
            has_fastapi = True
        except ModuleNotFoundError:
            has_fastapi = False

        if has_fastapi:
            from ch_control_center.services.mission_service import MissionService
            from ch_control_center.services.project_service import ProjectService

            ps = ProjectService()
            perfis = ps.listar_perfis()
            chaves_perfis = [p["project_key"] for p in perfis]
            self.assertIn("chdevflow", chaves_perfis)
            self.assertIn("hallancraft", chaves_perfis)

            ms = MissionService()
            snapshot, modo = ms.obter_snapshot_ativo()
            self.assertEqual(modo, "DEMO_OFFLINE")
            self.assertGreater(snapshot.get("totalCount", 0), 0)

    def test_wheel_inspection_contains_all_runtime_artifacts(self) -> None:
        """Constrói os wheels em diretório temporário e inspeciona se todos os artefatos estão empacotados."""
        if shutil.which("uv") is None:
            self.skipTest("Binário 'uv' não disponível para construção de wheel")

        with tempfile.TemporaryDirectory() as tmp_dist:
            dist_path = Path(tmp_dist)

            # 1. Constrói wheel do chdevflow
            res = subprocess.run(
                ["uv", "build", "--wheel", "-o", str(dist_path)],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, f"Falha ao construir wheel chdevflow: {res.stderr}")

            # 2. Constrói wheel do ch-control-center
            res_cc = subprocess.run(
                ["uv", "build", "--wheel", "-o", str(dist_path), "apps/control-center"],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res_cc.returncode, 0, f"Falha ao construir wheel control-center: {res_cc.stderr}")

            # 3. Inspeciona conteúdo do wheel chdevflow
            chdevflow_wheels = list(dist_path.glob("chdevflow-*.whl"))
            self.assertTrue(len(chdevflow_wheels) >= 1, "Wheel chdevflow deve ter sido gerado")
            with zipfile.ZipFile(chdevflow_wheels[0], "r") as z:
                names = z.namelist()
                self.assertIn("chdevflow/templates/AGENTS.md", names)
                self.assertIn("chdevflow/templates/docs/PROJETO.md", names)
                self.assertIn("chdevflow/templates/docs/STATUS.md", names)
                self.assertIn("chdevflow/templates/docs/CH/DECISOES.md", names)
                self.assertIn("chdevflow/templates/docs/CH/RELATORIO-UNIVERSAL-CH.md", names)
                self.assertIn("chdevflow/templates/.github/ISSUE_TEMPLATE/fatia-w.md", names)
                self.assertIn("chdevflow/templates/.github/PULL_REQUEST_TEMPLATE.md", names)

                # Confere dependência de ch-sentinela nos metadados
                meta_names = [n for n in names if n.endswith("METADATA")]
                self.assertTrue(len(meta_names) >= 1)
                meta_content = z.read(meta_names[0]).decode("utf-8")
                self.assertIn("Requires-Dist: ch-sentinela", meta_content)

            # 4. Inspeciona conteúdo do wheel ch-control-center
            cc_wheels = list(dist_path.glob("ch_control_center-*.whl"))
            self.assertTrue(len(cc_wheels) >= 1, "Wheel ch-control-center deve ter sido gerado")
            with zipfile.ZipFile(cc_wheels[0], "r") as z:
                names = z.namelist()
                self.assertIn("ch_control_center/templates/dashboard.html", names)
                self.assertIn("ch_control_center/templates/missions.html", names)
                self.assertIn("ch_control_center/templates/graph.html", names)
                self.assertIn("ch_control_center/templates/student.html", names)
                self.assertIn("ch_control_center/static/css/styles.css", names)
                self.assertIn("ch_control_center/static/js/app.js", names)
                self.assertIn("ch_control_center/fixtures/demo_project_snapshot.json", names)
                self.assertIn("ch_control_center/profiles/chdevflow.json", names)
                self.assertIn("ch_control_center/profiles/hallancraft.json", names)

                # Confere dependência de ch-sentinela nos metadados
                meta_names = [n for n in names if n.endswith("METADATA")]
                self.assertTrue(len(meta_names) >= 1)
                meta_content = z.read(meta_names[0]).decode("utf-8")
                self.assertIn("Requires-Dist: ch-sentinela", meta_content)


if __name__ == "__main__":
    unittest.main()
