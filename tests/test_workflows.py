"""Public workflows verified against real Pandoc/Ninja outputs."""

from __future__ import annotations

import base64
import io
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest
import yaml

from dojo.artifacts import MANIFEST_NAME, load_publication
from dojo.config import load_config
from dojo.core import NinjaGenerator
from dojo.crunch import crunch_file, decode_html, generate_payloads
from dojo.exceptions import ConfigFileNotFoundError, ConfigInvalidError
from dojo.validation import validate_output


@pytest.fixture
def project(tmp_path):
    root = tmp_path / "project with spaces"
    root.mkdir()
    (root / "content").mkdir()
    (root / "defaults.yaml").write_text("standalone: true\nto: html\n")
    (root / "dojo.yaml").write_text(
        yaml.safe_dump(
            {
                "src_dir": "content",
                "output_dir": "_site",
                "build_dir": "_build",
                "default_type": "page",
                "types": {
                    "page": {
                        "outputs": [
                            {
                                "id": "html",
                                "extension": "html",
                                "defaults": "defaults.yaml",
                            }
                        ]
                    }
                },
            }
        )
    )
    return root


def command(root: Path, *args: str, success: bool = True):
    env = {
        **os.environ,
        "PYTHONPATH": str(Path(__file__).resolve().parents[1] / "src")
        + os.pathsep
        + os.environ.get("PYTHONPATH", ""),
    }
    result = subprocess.run(
        [sys.executable, "-m", "dojo", *args, "-c", str(root / "dojo.yaml")],
        cwd=root.parent,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if success:
        assert result.returncode == 0, result.stdout + result.stderr
    else:
        assert result.returncode != 0
    return result


def configure(root: Path, mutate):
    path = root / "dojo.yaml"
    data = yaml.safe_load(path.read_text())
    mutate(data)
    path.write_text(yaml.safe_dump(data))


def test_partial_build_does_not_publish_a_complete_inventory(project):
    (project / "content/index.md").write_text("# Selected")
    command(project, "build", str(project / "_site/index.html"))
    assert (project / "_site/index.html").exists()
    assert not (project / "_site" / MANIFEST_NAME).exists()


def test_public_inventory_recovers_ownership_after_build_directory_removal(project):
    page = project / "content/obsolete.md"
    page.write_text("# Obsolete")
    (project / "content/index.md").write_text("# Keep")
    command(project, "build")
    (project / "_build").rename(project / "discarded-build")
    page.unlink()
    command(project, "build")
    assert not (project / "_site/obsolete.html").exists()
    assert (project / "_site/index.html").exists()


def test_dotted_names_arguments_and_config_root(project):
    (project / "content/chapter.v1.md").write_text("# First version")
    (project / "content/chapter.v2.md").write_text("# Second version")
    configure(
        project,
        lambda data: data["types"]["page"]["outputs"][0].update(
            args=["--metadata", "title=Title with spaces & quotes '"]
        ),
    )
    command(project, "build")
    assert "First version" in (project / "_site/chapter.v1.html").read_text()
    assert "Second version" in (project / "_site/chapter.v2.html").read_text()
    assert "Title with spaces" in (project / "_site/chapter.v2.html").read_text()
    assert (project / "_build/chapter.v1.json").is_file()
    assert (project / "_build/chapter.v2.json").is_file()


def test_filter_template_partial_and_image_edits_rebuild(project):
    data_dir = project / "pandoc"
    for folder in ("filters", "templates"):
        (data_dir / folder).mkdir(parents=True)
    filter_path = data_dir / "filters/change.lua"
    filter_path.write_text(
        'function Str(s) if s.text == "original" then return pandoc.Str("FIRST") end end'
    )
    template = data_dir / "templates/page.html"
    template.write_text(
        "<html><head><title>$title$</title></head><body>$part()$$body$</body></html>"
    )
    partial = data_dir / "templates/part.html"
    partial.write_text("<p>INITIAL PARTIAL</p>")
    (project / "defaults.yaml").write_text(
        "to: html\nstandalone: true\nembed-resources: true\ntemplate: page.html\nfilters: [change.lua]\n"
    )
    configure(project, lambda data: data.update(pandoc_data_dir="pandoc"))
    image = project / "content/picture.svg"
    image.write_text('<svg xmlns="http://www.w3.org/2000/svg"><text>FIRST IMAGE</text></svg>')
    (project / "content/index.md").write_text("original\n\n![test](picture.svg)")
    command(project, "build")
    target = project / "_site/index.html"
    before = target.read_bytes()
    filter_path.write_text(filter_path.read_text().replace("FIRST", "SECOND"))
    command(project, "build")
    assert b"SECOND" in target.read_bytes()
    partial.write_text("<p>REVISED PARTIAL</p>")
    command(project, "build")
    assert b"REVISED PARTIAL" in target.read_bytes()
    template.write_text(template.read_text().replace("<body>", '<body class="new">'))
    command(project, "build")
    assert b'class="new"' in target.read_bytes()
    current = target.read_bytes()
    image.write_text(image.read_text().replace("FIRST IMAGE", "SECOND IMAGE"))
    command(project, "build")
    assert target.read_bytes() != current != before


def test_owned_deletions_preserve_unowned_files_and_dot_assets_package(project):
    (project / "content/index.md").write_text("# Home\n\n![pixel](.well-known/pixel.svg)")
    (project / "content/removed.md").write_text("# Remove me")
    static = project / "public/.well-known"
    static.mkdir(parents=True)
    (static / "pixel.svg").write_text('<svg xmlns="http://www.w3.org/2000/svg"/>')
    configure(project, lambda data: data.update(static_dirs=["public"]))
    command(project, "build")
    (project / "_site/user.txt").write_text("Keep me")
    (project / "content/removed.md").unlink()
    command(project, "build")
    assert not (project / "_site/removed.html").exists()
    assert (project / "_site/user.txt").read_text() == "Keep me"
    archive = project / "release.txz"
    command(project, "package", "-o", str(archive))
    before = archive.read_bytes()
    command(project, "package", "-o", str(archive))
    assert archive.read_bytes() == before
    with tarfile.open(archive) as packed:
        assert ".well-known/pixel.svg" in packed.getnames()
        assert "removed.html" not in packed.getnames()
        assert "user.txt" not in packed.getnames()
        assert MANIFEST_NAME in packed.getnames()


def test_media_loss_repaired_and_pipeline_intermediates_stay_in_build(project):
    (project / "content/index.md").write_text("# Generated media")
    (project / "image.lua").write_text(
        "function Pandoc(doc) pandoc.mediabag.insert('generated.svg', 'image/svg+xml', "
        "'<svg xmlns=\"http://www.w3.org/2000/svg\"><text>hi</text></svg>'); "
        "table.insert(doc.blocks, pandoc.Para({pandoc.Image({}, 'generated.svg')})); return doc end"
    )
    (project / "defaults.yaml").write_text("standalone: true\nto: html\nfilters: [image.lua]\n")
    configure(
        project, lambda data: data["types"]["page"]["outputs"][0].update(post_process=["minify"])
    )
    command(project, "build")
    inventory = load_publication(project / "_site" / MANIFEST_NAME)
    media = [project / "_site" / item.path for item in inventory.artifacts if item.role == "media"]
    assert media
    assert list((project / "_build/render").rglob("*.html"))
    assert not list((project / "_site").rglob(".dojo-tmp-*"))
    media[0].unlink()
    command(project, "build")
    assert media[0].is_file()
    assert not validate_output(project / "_site")


def test_static_asset_edit_does_not_rebuild_unrelated_page(project):
    (project / "content/index.md").write_text("# Home")
    (project / "public").mkdir()
    (project / "public/style.css").write_text("body { color: red; }")
    configure(project, lambda data: data.update(static_dirs=["public"]))
    command(project, "build")
    before = (project / "_site/index.html").stat().st_mtime_ns
    (project / "public/style.css").write_text("body { color: blue; }")
    command(project, "build")
    assert (project / "_site/index.html").stat().st_mtime_ns == before
    assert "blue" in (project / "_site/style.css").read_text()


def test_dry_run_does_not_call_mutating_plugins_or_create_directories(project):
    (project / "plugin.py").write_text(
        'from dojo.plugins import PluginInterface\nclass Plugin(PluginInterface):\n def pre_generate(self, config, build_dir, **kwargs):\n  (build_dir / "MUTATED").write_text("bad")\n'
    )
    configure(project, lambda data: data.update(plugins=["plugin.py"], format_links=True))
    command(project, "build", "--dry-run")
    assert not (project / "_build").exists()
    assert not (project / "_site").exists()


def test_plugin_can_define_dataclasses_with_postponed_annotations(project):
    (project / "plugin.py").write_text(
        'from __future__ import annotations\nfrom dataclasses import dataclass\nfrom dojo.plugins import PluginInterface\n@dataclass\nclass Plugin(PluginInterface):\n value: str = "works"\n'
    )
    configure(project, lambda data: data.update(plugins=["plugin.py"]))
    config, path = load_config(str(project / "dojo.yaml"))
    NinjaGenerator(config, path).generate()


def test_failed_renderer_preserves_previous_output(project):
    (project / "content/index.md").write_text("# Good")
    command(project, "build")
    previous = (project / "_site/index.html").read_bytes()
    (project / "fail.lua").write_text('function Pandoc(doc) error("intentional failure") end')
    (project / "defaults.yaml").write_text("to: html\nfilters: [fail.lua]\n")
    command(project, "build", success=False)
    assert (project / "_site/index.html").read_bytes() == previous


def test_compressed_payload_and_embedded_styles_are_validated(project):

    page = project / "bad.html"
    content = '<p id="duplicate">a</p><p id="duplicate">b</p><link rel="stylesheet" href="data:text/css,body%7Bbackground:url(https://example.com/pixel)%7D">'
    page.write_text(content)
    compressed = project / "compressed.html"
    crunch_file(page, compressed)
    assert decode_html(compressed.read_text()) == content
    errors = validate_output(compressed, offline=True)
    assert any("duplicate HTML id" in error for error in errors)
    assert any("external resource" in error for error in errors)
    broken = compressed.read_text().replace('data-crunch="0:', 'data-crunch="1:', 1)
    compressed.write_text(broken)
    assert any("invalid compressed output" in error for error in validate_output(compressed))


def test_srcset_without_spaces_and_hidden_html_are_checked(project):
    output = project / "_site"
    output.mkdir()
    (output / "okay.svg").write_text("<svg/>")
    (output / ".hidden.html").write_text('<img srcset="okay.svg 1x,missing.svg 2x">')
    assert any("missing.svg" in error for error in validate_output(output))


def test_configuration_rejects_typos_pools_collisions_and_missing_explicit_file(project):

    with pytest.raises(ConfigFileNotFoundError):
        load_config(str(project / "absent.yaml"))
    original = (project / "dojo.yaml").read_text()
    for mutate in (
        lambda data: data.update(outpt_dir="typo"),
        lambda data: data.update(pools={"invalid": 0}),
        lambda data: data["types"]["page"]["outputs"].append(
            {"id": "second", "extension": "html", "defaults": "defaults.yaml"}
        ),
        lambda data: data["types"]["page"]["outputs"].append(
            {"id": "cycle", "extension": "pdf", "tool": "copy", "source": "cycle"}
        ),
    ):
        (project / "dojo.yaml").write_text(original)
        configure(project, mutate)
        with pytest.raises(ConfigInvalidError):
            load_config(str(project / "dojo.yaml"))


def test_embedded_assets_invalidate_only_consumers(project):
    public = project / "public"
    public.mkdir()
    style = public / "style.css"
    style.write_text("body { color: red; }")
    (project / "content/index.md").write_text("# Embedded style")
    (project / "embedded.yaml").write_text(
        "to: html\nstandalone: true\nembed-resources: true\ncss: [style.css]\n"
    )
    configure(project, lambda data: data.update(static_dirs=["public"]))
    configure(
        project,
        lambda data: data["types"]["page"]["outputs"].append(
            {
                "id": "embedded",
                "extension": "html",
                "suffix": "-embedded",
                "defaults": "embedded.yaml",
            }
        ),
    )
    command(project, "build")
    plain = project / "_site/index.html"
    embedded = project / "_site/index-embedded.html"
    before = embedded.read_bytes()
    untouched = plain.stat().st_mtime_ns
    style.write_text("body { color: blue; }")
    command(project, "build")
    assert embedded.read_bytes() != before
    assert plain.stat().st_mtime_ns == untouched


def test_frontmatter_bibliography_tracks_source_relative_files(project):
    source = project / "content/index.md"
    bibliography = project / "content/refs.json"
    bibliography.write_text('[{"id":"example", "title":"Initial title", "type":"book"}]')
    source.write_text("---\nbibliography: refs.json\n---\n\n[@example]")
    (project / "defaults.yaml").write_text("standalone: true\nto: html\nciteproc: true\n")
    command(project, "build")
    output = project / "_site/index.html"
    assert "Initial Title" in output.read_text()
    bibliography.write_text(bibliography.read_text().replace("Initial", "Revised"))
    command(project, "build")
    assert "Revised Title" in output.read_text()


def test_validation_keeps_embedded_svg_and_reveal_scopes_separate(tmp_path):
    svg = '<svg><defs><filter id="shadow"/></defs><path filter="url(#shadow)" style="filter:url(#shadow)"/></svg>'
    encoded = base64.b64encode(svg.encode()).decode()
    page = tmp_path / "index.html"
    page.write_text(
        f'<div class="reveal"><section id="slide"><a href="#/slide">Slide</a><img src="data:image/svg+xml;base64,{encoded}"></section></div>'
    )
    assert validate_output(page, links=True, offline=True) == []
    page.write_text(page.read_text().replace("#/slide", "#/missing"))
    assert any("missing anchor" in error for error in validate_output(page, links=True))


def test_browser_compression_window_is_bounded():
    with pytest.raises(ValueError, match="window_log"):
        list(generate_payloads(io.BytesIO(b"hello"), window_log=26))


@pytest.mark.browser
@pytest.mark.parametrize(("corrupt", "large"), [(False, False), (True, False), (False, True)])
def test_compressed_html_in_browser(tmp_path, corrupt, large):
    chrome = shutil.which("chromium") or shutil.which("chromium-browser")
    node = shutil.which("node")
    if not chrome or not node:
        pytest.skip("Chromium and Node.js are required for the browser integration test")
    source = tmp_path / "source.html"
    compressed = tmp_path / "compressed.html"
    source.write_text(
        '<html><body><main>Restored Unicode: \u03b1 東京</main><script>document.body.dataset.executed="yes";</script></body></html>'
    )
    if large:
        # Incompressible data forces multiple transport chunks and decoder blocks.
        source.write_text(source.read_text() + "<!--" + os.urandom(400_000).hex() + "-->")
    crunch_file(source, compressed)
    if large:
        assert compressed.read_text().count('type="application/octet-stream"') > 1
    if corrupt:
        compressed.write_text(
            compressed.read_text().replace('data-crunch="0:', 'data-crunch="1:', 1)
        )
    result = subprocess.run(
        [
            node,
            str(Path(__file__).parent / "browser/roundtrip.mjs"),
            chrome,
            str(tmp_path / "profile"),
            str(compressed),
            "corrupt" if corrupt else "success",
        ],
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert result.returncode == 0, result.stdout + result.stderr
