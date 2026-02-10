from __future__ import annotations

import pytest
import yaml

from dojo.config import Config, OutputConfig
from dojo.core import NinjaGenerator

# --- Config Tests ---


def test_format_links_defaults_to_false(tmp_path):
    """format_links should be disabled by default."""
    (tmp_path / "src").mkdir()
    cfg = Config(
        src_dir=str(tmp_path / "src"),
        output_dir=str(tmp_path / "site"),
        build_dir=str(tmp_path / "build"),
        default_type="page",
        types={"page": {"outputs": []}},
    )
    assert cfg.format_links is False


def test_format_links_can_be_enabled(tmp_path):
    """format_links can be explicitly set to True."""
    (tmp_path / "src").mkdir()
    cfg = Config(
        src_dir=str(tmp_path / "src"),
        output_dir=str(tmp_path / "site"),
        build_dir=str(tmp_path / "build"),
        default_type="page",
        types={"page": {"outputs": []}},
        format_links=True,
    )
    assert cfg.format_links is True


def test_output_config_label_defaults_to_none(tmp_path):
    """OutputConfig.label should default to None."""
    defaults = tmp_path / "d.yaml"
    defaults.touch()
    oc = OutputConfig(extension="html", defaults=str(defaults))
    assert oc.label is None


def test_output_config_label_accepts_value(tmp_path):
    """OutputConfig.label should accept a custom string."""
    defaults = tmp_path / "d.yaml"
    defaults.touch()
    oc = OutputConfig(extension="html", defaults=str(defaults), label="Web Page")
    assert oc.label == "Web Page"


# --- Format Link Defaults Generation Tests ---


@pytest.fixture
def multi_output_config(tmp_path):
    """Create a config with multiple outputs for format link testing."""
    src = tmp_path / "content"
    src.mkdir()
    (src / "test.md").write_text("---\ntype: note\n---\n# Test")

    defaults_html = tmp_path / "html.yaml"
    defaults_html.touch()
    defaults_slides = tmp_path / "slides.yaml"
    defaults_slides.touch()

    return {
        "src_dir": str(src),
        "output_dir": str(tmp_path / "site"),
        "build_dir": str(tmp_path / "build"),
        "default_type": "note",
        "format_links": True,
        "types": {
            "note": {
                "outputs": [
                    {"id": "html", "extension": "html", "defaults": str(defaults_html)},
                    {
                        "id": "slides",
                        "extension": "html",
                        "suffix": "-slides",
                        "defaults": str(defaults_slides),
                    },
                    {"id": "pdf", "extension": "pdf", "source": "slides", "tool": "decktape"},
                ],
            },
        },
    }


def test_generate_format_link_defaults(multi_output_config, tmp_path):
    """Generating with format_links=True should create defaults files."""
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)

    gen._generate_format_link_defaults()

    # Should generate defaults for standard renders only (html and slides, not pdf which is derived)
    assert ("note", "html") in gen._format_link_defaults
    assert ("note", "slides") in gen._format_link_defaults
    assert ("note", "pdf") not in gen._format_link_defaults


def test_format_link_defaults_file_content(multi_output_config, tmp_path):
    """Generated defaults files should contain correct filter and metadata."""
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)

    gen._generate_format_link_defaults()

    # Check the HTML output's defaults file
    html_defaults_path = gen._format_link_defaults[("note", "html")]
    assert html_defaults_path.exists()

    with open(html_defaults_path) as f:
        data = yaml.safe_load(f)

    # Should have filters referencing the bundled Lua filter
    assert "filters" in data
    assert len(data["filters"]) == 1
    assert data["filters"][0].endswith("format_links.lua")

    # Should have metadata with siblings
    assert "metadata" in data
    meta = data["metadata"]
    assert meta["dojo-current-suffix"] == ""  # HTML has no suffix

    siblings = meta["dojo-sibling-formats"]
    expected_sibling_count = 2  # slides + pdf
    assert len(siblings) == expected_sibling_count

    # Check sibling entries
    labels = {s["label"] for s in siblings}
    assert "SLIDES" in labels
    assert "PDF" in labels


def test_format_link_defaults_custom_label(tmp_path):
    """Custom labels on OutputConfig should appear in generated defaults."""
    src = tmp_path / "content"
    src.mkdir()

    defaults_html = tmp_path / "html.yaml"
    defaults_html.touch()
    defaults_pdf = tmp_path / "pdf.yaml"
    defaults_pdf.touch()

    cfg = Config(
        src_dir=str(src),
        output_dir=str(tmp_path / "site"),
        build_dir=str(tmp_path / "build"),
        default_type="page",
        format_links=True,
        types={
            "page": {
                "outputs": [
                    {"id": "html", "extension": "html", "defaults": str(defaults_html)},
                    {
                        "id": "pdf",
                        "extension": "pdf",
                        "defaults": str(defaults_pdf),
                        "label": "PDF Download",
                    },
                ],
            },
        },
    )
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)
    gen._generate_format_link_defaults()

    html_defaults_path = gen._format_link_defaults[("page", "html")]
    with open(html_defaults_path) as f:
        data = yaml.safe_load(f)

    siblings = data["metadata"]["dojo-sibling-formats"]
    assert siblings[0]["label"] == "PDF Download"


def test_format_link_defaults_single_output_skipped(tmp_path):
    """Types with only one output should not generate format link defaults."""
    src = tmp_path / "content"
    src.mkdir()

    defaults = tmp_path / "d.yaml"
    defaults.touch()

    cfg = Config(
        src_dir=str(src),
        output_dir=str(tmp_path / "site"),
        build_dir=str(tmp_path / "build"),
        default_type="page",
        format_links=True,
        types={
            "page": {
                "outputs": [{"id": "html", "extension": "html", "defaults": str(defaults)}],
            },
        },
    )
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)
    gen._generate_format_link_defaults()

    assert len(gen._format_link_defaults) == 0


def test_format_link_defaults_disabled(multi_output_config, tmp_path):
    """When format_links is False, no defaults should be generated."""
    multi_output_config["format_links"] = False
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)

    # generate() with format_links=False should not call _generate_format_link_defaults
    gen.generate()

    assert len(gen._format_link_defaults) == 0


# --- Apply Format Link Defaults Tests ---


def test_apply_format_link_defaults_prepends(multi_output_config, tmp_path):
    """_apply_format_link_defaults should prepend the generated defaults path."""
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)
    gen._generate_format_link_defaults()

    html_output = cfg.types["note"].outputs[0]
    modified = gen._apply_format_link_defaults(html_output, "note")

    # Defaults should now be a list with format link defaults first
    assert isinstance(modified.defaults, list)
    format_link_path = str(gen._format_link_defaults[("note", "html")])
    assert modified.defaults[0] == format_link_path


def test_apply_format_link_defaults_skips_derived(multi_output_config, tmp_path):
    """Derived outputs should not get format link defaults."""
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)
    gen._generate_format_link_defaults()

    pdf_output = cfg.types["note"].outputs[2]  # derived PDF
    modified = gen._apply_format_link_defaults(pdf_output, "note")

    # Should be unchanged (same object)
    assert modified is pdf_output


def test_apply_format_link_defaults_noop_when_disabled(multi_output_config, tmp_path):
    """When format links are not generated, apply should return config unchanged."""
    multi_output_config["format_links"] = False
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)

    html_output = cfg.types["note"].outputs[0]
    modified = gen._apply_format_link_defaults(html_output, "note")

    assert modified is html_output


# --- Full Pipeline Integration Test ---


def test_generate_with_format_links(multi_output_config, tmp_path):
    """Full generate() with format_links should include format link defaults in build edges."""
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)
    gen.generate()

    # Format link defaults should have been generated
    assert len(gen._format_link_defaults) > 0

    # Build file should contain the format link defaults path
    ninja_content = gen.ninja_file.read_text()
    for defaults_path in gen._format_link_defaults.values():
        # The defaults path should appear in the build edges (via -d flag)
        assert str(defaults_path) in ninja_content


def test_generate_with_format_links_slides_suffix(multi_output_config, tmp_path):
    """The slides output defaults should record its own suffix correctly."""
    cfg = Config(**multi_output_config)
    gen = NinjaGenerator(cfg, tmp_path / "dojo.yaml", quiet=True)
    gen._generate_format_link_defaults()

    slides_defaults_path = gen._format_link_defaults[("note", "slides")]
    with open(slides_defaults_path) as f:
        data = yaml.safe_load(f)

    assert data["metadata"]["dojo-current-suffix"] == "-slides"

    # Siblings should include html and pdf
    siblings = data["metadata"]["dojo-sibling-formats"]
    extensions = {s["extension"] for s in siblings}
    assert "html" in extensions
    assert "pdf" in extensions
