import pytest
from pathlib import Path
from unittest.mock import MagicMock
from dojo.emitter import NinjaEmitter
from dojo.config import Config

@pytest.fixture
def mock_emitter():
    """Provides a MagicMock specialized for NinjaEmitter."""
    return MagicMock(spec=NinjaEmitter)

@pytest.fixture
def minimal_config(tmp_path):
    """Provides a minimal valid Dojo configuration."""
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
                "outputs": [
                    {"id": "html", "extension": "html", "defaults": str(dummy_defaults)}
                ]
            }
        }
    )

@pytest.fixture
def sample_project_dir(tmp_path):
    """Creates a sample project directory structure."""
    project = tmp_path / "sample_project"
    project.mkdir()
    
    (project / "content").mkdir()
    (project / "content" / "index.md").write_text("# Home\n", encoding="utf-8")
    (project / "content" / "about.md").write_text("# About\n", encoding="utf-8")
    
    (project / "defaults").mkdir()
    (project / "defaults" / "page.yaml").write_text("standalone: true\n", encoding="utf-8")
    
    return project
