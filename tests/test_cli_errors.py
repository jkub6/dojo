"""Tests for Dojo CLI failure modes and error handling.

These tests ensure that the CLI handles invalid configurations, missing directories,
and other error conditions gracefully with appropriate exit codes and messages.
"""

from __future__ import annotations

from typing import TYPE_CHECKING


if TYPE_CHECKING:
    from pathlib import Path

import pytest
import yaml
from dojo.cli import main


class TestCLIErrors:
    """Tests for CLI error handling."""

    def test_missing_config_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Test error when specified config file doesn't exist."""
        monkeypatch.chdir(tmp_path)
        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", "nonexistent.yaml"])
        assert exc.value.code != 0

    def test_invalid_yaml_config(self, tmp_path: Path) -> None:
        """Test error when config file contains invalid YAML."""
        config_path = tmp_path / "bad.yaml"
        config_path.write_text("invalid: [unclosed bracket")

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path)])
        assert exc.value.code != 0

    def test_invalid_config_schema(self, tmp_path: Path) -> None:
        """Test error when config fails Pydantic validation."""
        config_path = tmp_path / "invalid_schema.yaml"
        # Missing required src_dir and other fields
        config_path.write_text("debug: true")

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path)])
        assert exc.value.code != 0

    def test_missing_source_directory(self, tmp_path: Path) -> None:
        """Test error when src_dir doesn't exist."""
        config_path = tmp_path / "dojo.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "src_dir": str(tmp_path / "missing_src"),
                    "output_dir": str(tmp_path / "site"),
                    "build_dir": str(tmp_path / "build"),
                    "default_type": "page",
                    "types": {"page": {"outputs": []}},
                }
            )
        )

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path)])
        assert exc.value.code != 0

    def test_duplicate_output_ids(self, tmp_path: Path) -> None:
        """Test error when multiple outputs in a type have the same ID."""
        src = tmp_path / "src"
        src.mkdir()
        defaults = tmp_path / "defaults.yaml"
        defaults.touch()

        config_path = tmp_path / "dojo.yaml"
        config_path.write_text(
            yaml.dump(
                {
                    "src_dir": str(src),
                    "output_dir": str(tmp_path / "site"),
                    "build_dir": str(tmp_path / "build"),
                    "default_type": "page",
                    "types": {
                        "page": {
                            "outputs": [
                                {"id": "out1", "extension": "html", "defaults": str(defaults)},
                                {"id": "out1", "extension": "pdf", "defaults": str(defaults)},
                            ]
                        }
                    },
                }
            )
        )

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path)])
        assert exc.value.code != 0

    def test_no_args_shows_help(self) -> None:
        """Test that running without args exits with 0 (standard help behavior)."""
        with pytest.raises(SystemExit) as exc:
            main([])
        assert exc.value.code == 0

    def test_invalid_command(self) -> None:
        """Test that unknown commands fail."""
        with pytest.raises(SystemExit) as exc:
            main(["nonexistent-command"])
        assert exc.value.code != 0

    def test_json_logging(self, tmp_path: Path) -> None:
        """Test that --json flag enables JSON logging."""
        config_path = tmp_path / "dojo.yaml"
        # Invalid config to trigger an error and see the log
        config_path.write_text("invalid: [")

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path), "--json"])
        assert exc.value.code != 0

    def test_verbose_error(self, tmp_path: Path) -> None:
        """Test that --verbose flag shows full traceback on error."""
        config_path = tmp_path / "dojo.yaml"
        config_path.write_text("invalid: [")

        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path), "--verbose"])
        assert exc.value.code != 0

    def test_json_logging_with_version(self) -> None:
        """Test that --json flag works with version command."""
        main(["--version", "--json"])
        # Should hit setup_cli_logging's json branch

    def test_verbose_check_error(self, tmp_path: Path) -> None:
        """Test that check command with --verbose hits error path."""
        config_path = tmp_path / "bad.yaml"
        config_path.write_text("invalid: [")

        with pytest.raises(SystemExit) as exc:
            main(["check", "-c", str(config_path), "--verbose"])
        assert exc.value.code != 0

    def test_version_subcommand(self) -> None:
        """Test the version subcommand."""
        main(["version"])

    def test_version_flag(self) -> None:
        """Test the --version flag."""
        main(["--version"])

    def test_main_internal_error(self, mocker) -> None:
        """Test that unhandled exceptions in main are caught and reported."""
        mocker.patch("dojo.cli.setup_cli_logging", side_effect=RuntimeError("Internal Crash"))
        # We need to catch sys.exit
        with pytest.raises(SystemExit) as exc:
            main(["--version"])
        assert exc.value.code == 1

    def test_build_unexpected_error(self, tmp_path, mocker) -> None:
        """Test that unexpected errors during build are reported."""
        config_path = tmp_path / "dojo.yaml"
        config_path.touch()
        mocker.patch("dojo.cli.load_config", side_effect=Exception("Build Failed"))
        with pytest.raises(SystemExit) as exc:
            main(["build", "-c", str(config_path)])
        assert exc.value.code == 1

    def test_check_unexpected_error(self, tmp_path, mocker) -> None:
        """Test that unexpected errors during check are reported."""
        config_path = tmp_path / "dojo.yaml"
        config_path.touch()
        mocker.patch("dojo.cli.load_config", side_effect=Exception("Check Failed"))
        with pytest.raises(SystemExit) as exc:
            main(["check", "-c", str(config_path)])
        assert exc.value.code == 1

    def test_init_unexpected_error(self, mocker) -> None:
        """Test that unexpected errors during init are reported."""
        mocker.patch("dojo.cli.Path.exists", side_effect=Exception("Init Failed"))
        with pytest.raises(SystemExit) as exc:
            main(["init"])
        assert exc.value.code == 1
