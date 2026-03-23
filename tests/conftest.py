from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dojo.config import Config
from dojo.emitter import NinjaEmitter


@pytest.fixture
def mock_emitter():
    """Provide a MagicMock specialized for NinjaEmitter."""
    return MagicMock(spec=NinjaEmitter)


@pytest.fixture
def mock_config():
    """Provide a mocked Config object with standard paths."""
    config = MagicMock(spec=Config)
    config.src_dir = Path("/src")
    config.output_dir = Path("/out")
    config.build_dir = Path("/build")
    config.pandoc_data_dir = None
    return config


@pytest.fixture
def minimal_config(tmp_path):
    """Provide a minimal valid Dojo configuration."""
    src = tmp_path / "src"
    src.mkdir()
    out = tmp_path / "out"
    out.mkdir()
    build = tmp_path / "build"
    build.mkdir()

    (tmp_path / "defaults").mkdir(exist_ok=True)
    dummy_defaults = tmp_path / "defaults" / "html.yaml"
    dummy_defaults.write_text("standalone: true\n", encoding="utf-8")

    return Config(
        src_dir=str(src),
        output_dir=str(out),
        build_dir=str(build),
        default_type="page",
        types={
            "page": {
                "outputs": [{"id": "html", "extension": "html", "defaults": str(dummy_defaults)}]
            }
        },
    )


@pytest.fixture
def sample_project_dir(tmp_path):
    """Create a sample project directory structure."""
    project = tmp_path / "sample_project"
    project.mkdir()

    (project / "content").mkdir()
    (project / "content" / "index.md").write_text("# Home\n", encoding="utf-8")
    (project / "content" / "about.md").write_text("# About\n", encoding="utf-8")

    (project / "defaults").mkdir()
    (project / "defaults" / "page.yaml").write_text("standalone: true\n", encoding="utf-8")

    return project


@pytest.fixture
def normalize_ninja():
    """Provide a function to normalize Ninja output for snapshots.

    Replaces absolute project and dojo paths with placeholders to keep
    snapshots stable across different environments.
    """

    def _normalize(content: str, project_root: Path, dojo_root: Path) -> str:
        # Normalize project root
        content = content.replace(str(project_root.resolve()), "[PROJECT_ROOT]")
        content = content.replace(str(project_root), "[PROJECT_ROOT]")

        content = content.replace(str(dojo_root), "[DOJO_ROOT]")

        return content.replace(str(dojo_root.resolve()), "[DOJO_ROOT]")

    return _normalize
