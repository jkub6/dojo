"""Publication membership and configuration identities survive warm builds."""

from __future__ import annotations

import os
import shutil

import pytest
from test_workflows import command, configure, project  # noqa: F401

from dojo.config import OutputConfig, order_outputs
from dojo.resources import clear_resource_cache, find_resource


def test_explicit_project_resources_are_not_shadowed_by_cwd(tmp_path, monkeypatch):
    root, other = tmp_path / "project", tmp_path / "other"
    for directory in (root, other):
        (directory / "defaults").mkdir(parents=True)
        (directory / "defaults/page.yaml").write_text("to: html\n")
    monkeypatch.chdir(other)
    clear_resource_cache()
    assert find_resource("defaults", "defaults/page.yaml", [root]) == root / "defaults/page.yaml"
    (root / "defaults/page.yaml").unlink()
    clear_resource_cache()
    assert find_resource("defaults", "defaults/page.yaml", [root]) is None


def test_anonymous_output_cannot_collide_with_explicit_id():
    anonymous = OutputConfig(extension="html", defaults="html.yaml")
    named = OutputConfig(id=".html", extension="pdf", defaults="pdf.yaml")
    assert order_outputs("page", [anonymous, named]) == [anonymous, named]


def test_old_static_sources_do_not_rebuild_on_every_invocation(project):  # noqa: F811
    (project / "content/index.md").write_text("# Stable")
    source = project / "static/old.txt"
    source.parent.mkdir()
    source.write_text("unchanged content")
    os.utime(source, ns=(1_000_000_000, 1_000_000_000))
    configure(project, lambda data: data.update(static_dirs=["static"]))
    configure(
        project,
        lambda data: data["types"]["page"]["outputs"][0].update(consumes_assets=True),
    )
    command(project, "build")
    output = project / "_site/index.html"
    before = output.stat().st_mtime_ns
    result = command(project, "build")
    assert "no work to do" in result.stdout
    assert output.stat().st_mtime_ns == before


def test_removed_static_assets_are_gone_before_rendering(project):  # noqa: F811
    (project / "content/index.md").write_text("# Assets")
    static = project / "static"
    static.mkdir()
    for name in ("one.txt", "two.txt"):
        (static / name).write_text(name)
    (project / "count.lua").write_text(
        "function Pandoc(doc) local count = 0; "
        'local site = pandoc.utils.stringify(doc.meta["dojo-project-root"]) .. "/_site"; '
        "for _, name in ipairs(pandoc.system.list_directory(site)) do "
        'if name:match("%.txt$") then count = count + 1 end end; '
        'doc.blocks:insert(pandoc.Para({pandoc.Str("count=" .. count)})); return doc end'
    )
    (project / "defaults.yaml").write_text("to: html\nfilters: [count.lua]\n")
    configure(project, lambda data: data.update(static_dirs=["static"]))
    configure(
        project,
        lambda data: data["types"]["page"]["outputs"][0].update(consumes_assets=True),
    )
    target = project / "_site/index.html"
    command(project, "build")
    assert "count=2" in target.read_text()
    # Existing installations recorded copies as ordinary publications.
    inventory = project / "_build/publication.json"
    inventory.write_text(inventory.read_text().replace('"role": "asset"', '"role": "publication"'))
    for name, remaining in (("two.txt", 1), ("one.txt", 0)):
        (static / name).unlink()
        command(project, "build")
        warm = target.read_bytes()
        assert f"count={remaining}" in warm.decode()
        # A warm build must be byte-for-byte equivalent to an isolated clean build.
        shutil.rmtree(project / "_site")
        shutil.rmtree(project / "_build")
        command(project, "build")
        assert target.read_bytes() == warm
    before = target.stat().st_mtime_ns
    command(project, "build")
    assert target.stat().st_mtime_ns == before


@pytest.mark.parametrize("name", ["dojo-publication.json", "provenance/custom.json"])
def test_static_assets_cannot_overwrite_release_metadata(project, name):  # noqa: F811
    path = project / "static" / name
    path.parent.mkdir(parents=True)
    path.write_text("author content")
    configure(project, lambda data: data.update(static_dirs=["static"]))
    result = command(project, "build", success=False)
    assert "Reserved publication path" in result.stdout + result.stderr
    assert not (project / "_site" / name).exists()
