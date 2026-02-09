"""Tests for JSON Schema generation."""

from __future__ import annotations

import json

import pytest


class TestSchemaGeneration:
    """Tests for the schema module."""

    def test_generate_schema_returns_dict(self) -> None:
        """Test that generate_schema returns a valid dict."""
        from dojo.schema import generate_schema

        schema = generate_schema()

        assert isinstance(schema, dict)
        assert "$defs" in schema or "properties" in schema
        assert "title" in schema

    def test_schema_has_expected_properties(self) -> None:
        """Test that schema contains expected configuration properties."""
        from dojo.schema import generate_schema

        schema = generate_schema()
        props = schema.get("properties", {})

        # Core config properties should be present
        expected = ["src_dir", "output_dir", "build_dir", "default_type", "types"]
        for prop in expected:
            assert prop in props, f"Missing property: {prop}"

    def test_write_schema_returns_json_string(self) -> None:
        """Test that write_schema returns valid JSON."""
        from dojo.schema import write_schema

        schema_json = write_schema()

        # Should be valid JSON
        parsed = json.loads(schema_json)
        assert isinstance(parsed, dict)

    def test_write_schema_pretty_formatting(self) -> None:
        """Test that pretty=True adds indentation."""
        from dojo.schema import write_schema

        pretty_json = write_schema(pretty=True)
        compact_json = write_schema(pretty=False)

        # Pretty should have newlines
        assert "\n" in pretty_json
        # Pretty should be longer due to indentation
        assert len(pretty_json) > len(compact_json)

    def test_write_schema_to_file(self, tmp_path) -> None:
        """Test writing schema to file."""
        from dojo.schema import write_schema

        output_file = tmp_path / "schema.json"
        write_schema(output_file)

        assert output_file.exists()
        content = output_file.read_text()
        parsed = json.loads(content)
        assert "title" in parsed

    def test_schema_validates_valid_config(self) -> None:
        """Test that generated schema can validate a valid config."""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        from dojo.schema import generate_schema

        schema = generate_schema()

        # Create a minimal valid config
        valid_config = {
            "src_dir": "content",
            "output_dir": "_site",
            "build_dir": "_build",
            "default_type": "page",
            "types": {"page": {"outputs": []}},
        }

        # This should not raise
        jsonschema.validate(valid_config, schema)

    def test_schema_rejects_invalid_config(self) -> None:
        """Test that generated schema rejects invalid config."""
        try:
            import jsonschema
        except ImportError:
            pytest.skip("jsonschema not installed")

        from dojo.schema import generate_schema

        schema = generate_schema()

        # Missing required field
        invalid_config = {
            "src_dir": "content",
            # missing other required fields
        }

        with pytest.raises(jsonschema.ValidationError):
            jsonschema.validate(invalid_config, schema)


class TestSchemaCliCommand:
    """Tests for the schema CLI command."""

    def test_schema_command_stdout(self, capsys) -> None:
        """Test that schema command prints to stdout."""
        from dojo.cli import main

        main(["schema"])

        captured = capsys.readouterr()
        output = captured.out

        # Should be valid JSON
        parsed = json.loads(output)
        assert "title" in parsed

    def test_schema_command_with_output_file(self, tmp_path, capsys) -> None:
        """Test schema command with -o flag."""
        from dojo.cli import main

        output_file = tmp_path / "test-schema.json"
        main(["schema", "-o", str(output_file)])

        # Should have written file
        assert output_file.exists()

        # Should print confirmation
        captured = capsys.readouterr()
        assert "Schema written to" in captured.out

        # File should contain valid schema
        content = output_file.read_text()
        parsed = json.loads(content)
        assert "properties" in parsed or "$defs" in parsed
