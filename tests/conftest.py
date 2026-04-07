import logging
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from dojo.config import Config
from dojo.emitter import NinjaEmitter


@pytest.fixture(autouse=True)
def enable_logging_propagation():
    """Enable logging propagation for 'dojo' logger during tests.

    This ensures that pytest's caplog fixture can capture logs even when
    the 'dojo' logger has propagate=False (the production default).
    """
    logger = logging.getLogger("dojo")
    previous_propagate = logger.propagate
    previous_level = logger.level
    previous_handlers = list(logger.handlers)

    logger.propagate = True
    logger.setLevel(logging.NOTSET)

    yield

    logger.propagate = previous_propagate
    logger.setLevel(previous_level)
    logger.handlers = previous_handlers


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
    import re

    def _normalize(content: str, project_root: Path, dojo_root: Path) -> str:
        # Normalize project root
        content = content.replace(str(project_root.resolve()), "[PROJECT_ROOT]")
        content = content.replace(str(project_root), "[PROJECT_ROOT]")

        content = content.replace(str(dojo_root.resolve()), "[DOJO_ROOT]")
        content = content.replace(str(dojo_root), "[DOJO_ROOT]")

        # Normalize the dynamic PATH env variable injected by Dojo
        content = re.sub(r"--path-env \S+", '--path-env "[TOOL_PATHS]"', content)
        content = re.sub(r'--path-env "[^"]+"', '--path-env "[TOOL_PATHS]"', content)

        # Normalize the dojo wrap prefix which includes sys.executable and wrap.py path
        # e.g. /path/to/python3 /path/to/dojo/wrap.py
        content = re.sub(r"\S*python\S* \S*dojo/wrap.py", "[DOJO_WRAP]", content)
         # Normalize the regenerate rule's python interpreter (which may vary with -env suffix)
        content = re.sub(
            r"/nix/store/\S*python\S*(?:-env)?/bin/python\S*", "[PYTHON_BIN]", content
        )
        # Normalize any Nix store hash to prevent snapshot drift
        content = re.sub(r"/nix/store/[a-z0-9]{32}-", "/nix/store/[HASH]-", content)

        # Normalize tool paths and commands
        content = re.sub(r"\S*pandoc {in_abs}", "[TOOL_PANDOC] {in_abs}", content)
        content = re.sub(r"\S*minify --html-keep", "[TOOL_MINIFY] --html-keep", content)
        content = re.sub(r"\S*gs -sDEVICE", "[TOOL_GS] -sDEVICE", content)
        content = re.sub(r"--copy -- ", "[PY_COPY] ", content)
        return re.sub(r"\S*decktape reveal", "[TOOL_DECKTAPE] reveal", content)

    return _normalize
