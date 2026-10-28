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


def get_packaging_builder() -> str | None:
    """Detecta ferramenta de construção de wheels disponível ('uv' ou 'pip')."""
    if shutil.which("uv") is not None:
        return "uv"
    res = subprocess.run(
        [sys.executable, "-m", "pip", "--version"],
        capture_output=True,
        check=False,
    )
    if res.returncode == 0:
        return "pip"
    return None


class TestPackagingWheelAudit(unittest.TestCase):
    """Bateria de testes de integridade de empacotamento para a missão AUD-GERAL-P0-02."""

    @classmethod
    def setUpClass(cls) -> None:
        cls.repo_root = Path(__file__).resolve().parent.parent
        cls.control_center_root = cls.repo_root / "apps" / "control-center"
        cls.sentinela_root = cls.repo_root / "apps" / "bootstrap" / "sentinela"

    def _require_packaging_builder(self) -> str:
        """Retorna o builder ou falha estritamente em ambiente de CI."""
        builder = get_packaging_builder()
        if not builder:
            is_ci = bool(os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS"))
            if is_ci:
                self.fail(
                    "FALHA ESTRITA CI: Nenhuma ferramenta de build/empacotamento ('uv' ou 'pip') "
                    "foi encontrada no PATH ou no interpretador ativo. "
                    "O teste de empacotamento não pode ser ignorado silenciosamente no CI."
                )
            self.skipTest(
                "Ambiente local sem 'uv' ou 'pip' disponível no interpretador para build de wheel."
            )
        return builder

    def _build_wheel(self, source_path: Path, output_dir: Path, builder: str) -> Path:
        """Constrói o wheel de um pacote especificado usando o builder detectado."""
        if builder == "uv":
            res = subprocess.run(
                ["uv", "build", "--wheel", "-o", str(output_dir), str(source_path)],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, f"Falha ao construir wheel com uv ({source_path}): {res.stderr}")
        elif builder == "pip":
            res = subprocess.run(
                [sys.executable, "-m", "pip", "wheel", "--no-deps", "-w", str(output_dir), str(source_path)],
                cwd=str(self.repo_root),
                capture_output=True,
                text=True,
                check=False,
            )
            self.assertEqual(res.returncode, 0, f"Falha ao construir wheel com pip ({source_path}): {res.stderr}")
        else:
            self.fail(f"Builder desconhecido: {builder}")

        wheels = list(output_dir.glob("*.whl"))
        self.assertTrue(len(wheels) >= 1, f"Nenhum wheel gerado em {output_dir} para {source_path}")
        return max(wheels, key=lambda p: p.stat().st_mtime)

    def test_symlinks_portability_and_preservation(self) -> None:
        """Comprova a portabilidade e a preservação dos links simbólicos introduzidos."""
        # 1. Symlink da raiz: templates -> src/chdevflow/templates
        link_templates = self.repo_root / "templates"
        self.assertTrue(link_templates.is_symlink(), "templates na raiz deve ser link simbólico")
        target_templates = os.readlink(link_templates)
        self.assertFalse(
            os.path.isabs(target_templates),
            f"Alvo do symlink de templates deve ser estritamente relativo: {target_templates}",
        )
        self.assertEqual(target_templates, "src/chdevflow/templates")

        # 2. Diretório canônico real dos templates
        canonical_templates = self.repo_root / "src" / "chdevflow" / "templates"
        self.assertTrue(canonical_templates.is_dir(), "Diretório canônico de templates deve existir")
        self.assertFalse(canonical_templates.is_symlink(), "Diretório canônico de templates não deve ser symlink")

        # 3. Symlink do Control Center: fixtures -> src/ch_control_center/fixtures
        link_fixtures = self.control_center_root / "fixtures"
        self.assertTrue(link_fixtures.is_symlink(), "control-center/fixtures deve ser link simbólico")
        target_fixtures = os.readlink(link_fixtures)
        self.assertFalse(
            os.path.isabs(target_fixtures),
            f"Alvo de fixtures deve ser relativo: {target_fixtures}",
        )
        self.assertEqual(target_fixtures, "src/ch_control_center/fixtures")
        canonical_fixtures = self.control_center_root / "src" / "ch_control_center" / "fixtures"
        self.assertTrue(canonical_fixtures.is_dir())
        self.assertFalse(canonical_fixtures.is_symlink())

        # 4. Symlink do Control Center: profiles -> src/ch_control_center/profiles
        link_profiles = self.control_center_root / "profiles"
        self.assertTrue(link_profiles.is_symlink(), "control-center/profiles deve ser link simbólico")
        target_profiles = os.readlink(link_profiles)
        self.assertFalse(
            os.path.isabs(target_profiles),
            f"Alvo de profiles deve ser relativo: {target_profiles}",
        )
        self.assertEqual(target_profiles, "src/ch_control_center/profiles")
        canonical_profiles = self.control_center_root / "src" / "ch_control_center" / "profiles"
        self.assertTrue(canonical_profiles.is_dir())
        self.assertFalse(canonical_profiles.is_symlink())

        # 5. Resolução de runtime não depende do symlink da raiz
        resolved_tpl = get_templates_dir()
        self.assertEqual(
            resolved_tpl.resolve(),
            canonical_templates.resolve(),
            "get_templates_dir deve resolver para o diretório canônico interno do pacote",
        )

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
        builder = self._require_packaging_builder()

        with tempfile.TemporaryDirectory() as tmp_dist:
            dist_path = Path(tmp_dist)

            # 1. Constrói wheel do chdevflow
            self._build_wheel(self.repo_root, dist_path, builder)

            # 2. Constrói wheel do ch-control-center
            self._build_wheel(self.control_center_root, dist_path, builder)

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

    def test_clean_environment_wheel_installation_and_execution(self) -> None:
        """Instala os wheels em ambiente virtual limpo isolado e testa comandos CLI e Control Center."""
        builder = self._require_packaging_builder()

        with tempfile.TemporaryDirectory() as tmp_base:
            base_path = Path(tmp_base)
            dist_path = base_path / "dist"
            dist_path.mkdir()
            venv_path = base_path / "venv"
            work_dir = base_path / "workdir"
            work_dir.mkdir()

            # 1. Constrói wheels locais dos 3 pacotes
            self._build_wheel(self.sentinela_root, dist_path, builder)
            self._build_wheel(self.repo_root, dist_path, builder)
            self._build_wheel(self.control_center_root, dist_path, builder)

            # 2. Cria venv isolado
            if builder == "uv":
                res_venv = subprocess.run(["uv", "venv", str(venv_path)], capture_output=True, text=True, check=False)
                self.assertEqual(res_venv.returncode, 0, f"Falha ao criar venv com uv: {res_venv.stderr}")
            else:
                res_venv = subprocess.run([sys.executable, "-m", "venv", str(venv_path)], capture_output=True, text=True, check=False)
                self.assertEqual(res_venv.returncode, 0, f"Falha ao criar venv: {res_venv.stderr}")

            venv_python = venv_path / "bin" / "python"
            venv_ch = venv_path / "bin" / "ch"
            venv_sent = venv_path / "bin" / "ch-sentinela"

            # 3. Instala os wheels no venv
            if builder == "uv":
                res_inst = subprocess.run(
                    [
                        "uv", "pip", "install",
                        "--python", str(venv_python),
                        "--find-links", str(dist_path),
                        "chdevflow", "ch-control-center",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            else:
                res_inst = subprocess.run(
                    [
                        str(venv_python), "-m", "pip", "install",
                        "--find-links", str(dist_path),
                        "chdevflow", "ch-control-center",
                    ],
                    capture_output=True,
                    text=True,
                    check=False,
                )
            self.assertEqual(res_inst.returncode, 0, f"Falha na instalação dos wheels: {res_inst.stderr}")

            # 4. Ambiente estritamente limpo: sem PYTHONPATH
            clean_env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

            # Teste CLI: ch --help
            res_help = subprocess.run([str(venv_ch), "--help"], cwd=str(work_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_help.returncode, 0)
            self.assertIn("chdevflow", res_help.stdout.lower())

            # Teste CLI: ch new ProjetoLimpo
            res_new = subprocess.run([str(venv_ch), "new", "ProjetoLimpo"], cwd=str(work_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_new.returncode, 0, f"Erro em ch new: {res_new.stderr}")
            proj_dir = work_dir / "ProjetoLimpo"
            self.assertTrue(proj_dir.is_dir())
            for doc in ESSENTIAL_DOCS:
                self.assertTrue((proj_dir / doc).is_file(), f"Documento essencial '{doc}' ausente na instalação limpa")

            # Teste CLI: ch status --strict
            res_status = subprocess.run([str(venv_ch), "status", "--strict", "--path", str(proj_dir)], cwd=str(work_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_status.returncode, 0)

            # Teste CLI: ch doctor
            res_doc = subprocess.run([str(venv_ch), "doctor", "--path", str(proj_dir)], cwd=str(work_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_doc.returncode, 0)

            # Teste Sentinela: ch-sentinela --help e demo --fake-worker
            res_s_help = subprocess.run([str(venv_sent), "--help"], cwd=str(work_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_s_help.returncode, 0)

            res_s_demo = subprocess.run([str(venv_sent), "demo", "--fake-worker"], cwd=str(work_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_s_demo.returncode, 0)
            self.assertIn("AWAITING_PO", res_s_demo.stdout)

            # Teste CLI: ch watch --once --dry-run
            res_watch = subprocess.run([str(venv_ch), "watch", "--once", "--dry-run"], cwd=str(proj_dir), env=clean_env, capture_output=True, text=True)
            self.assertEqual(res_watch.returncode, 0, f"Erro em ch watch: {res_watch.stderr}")

            # Teste Control Center: carregamento autossuficiente de perfis, fixtures e rotas
            test_cc_code = (
                "from ch_control_center.services.project_service import ProjectService\n"
                "from ch_control_center.services.mission_service import MissionService\n"
                "from ch_control_center.app import create_app\n"
                "ps = ProjectService()\n"
                "keys = [p['project_key'] for p in ps.listar_perfis()]\n"
                "assert 'chdevflow' in keys and 'hallancraft' in keys, f'Chaves invalidas: {keys}'\n"
                "ms = MissionService()\n"
                "snapshot, modo = ms.obter_snapshot_ativo()\n"
                "assert modo == 'DEMO_OFFLINE', f'Modo invalido: {modo}'\n"
                "assert snapshot.get('totalCount', 0) > 0\n"
                "app = create_app()\n"
                "assert app.title == 'CHDevFlow Control Center'\n"
                "print('CONTROL_CENTER_WHEEL_OK')\n"
            )
            res_cc = subprocess.run(
                [str(venv_python), "-c", test_cc_code],
                cwd=str(work_dir),
                env=clean_env,
                capture_output=True,
                text=True,
            )
            self.assertEqual(res_cc.returncode, 0, f"Erro no Control Center no venv limpo: {res_cc.stderr}")
            self.assertIn("CONTROL_CENTER_WHEEL_OK", res_cc.stdout)


if __name__ == "__main__":
    unittest.main()
