"""Failure recovery must preserve publications and reject incomplete archives."""

from __future__ import annotations

import os
import sys

import pytest

from dojo.artifacts import (
    MANIFEST_NAME,
    Artifact,
    Publication,
    finalize_publication,
    import_legacy_publication,
    load_publication,
    package_publication,
    repair_media,
)
from dojo.locking import build_lock
from dojo.wrap import _publish_media, run_wrap


def test_finalization_exports_portable_provenance_and_preserves_modified_files(tmp_path):
    output, build = tmp_path / "site", tmp_path / "build"
    output.mkdir()
    build.mkdir()
    page = output / "index.html"
    page.write_text("<h1>Published</h1>")
    stale = output / "stale.html"
    stale.write_text("author's independent edit")
    previous = Publication(artifacts=[Artifact(path="stale.html", sha256="different")])
    provenance = build / "source.manifest.json"
    provenance.write_text('{"source":"source.md"}')
    media = output / "media"
    media.mkdir()
    (media / "asset.svg").write_text("<svg/>")
    finalize_publication(output, build, [page], {media: page}, previous, provenance=(provenance,))
    assert stale.read_text() == "author's independent edit"
    public = (output / MANIFEST_NAME).read_text()
    assert str(tmp_path) not in public
    assert '"role": "provenance"' in public
    assert load_publication(build / "publication.json").artifacts[1].producer is not None
    (build / "future.json").write_text('{"schema_version":99}')
    with pytest.raises(ValueError, match="Unsupported"):
        load_publication(build / "future.json")


def test_failed_package_keeps_previous_archive_and_checksum(tmp_path):
    output = tmp_path / "site"
    output.mkdir()
    archive = tmp_path / "release.txz"
    archive.write_bytes(b"previous release")
    sidecar = archive.with_name("release.txz.sha256")
    sidecar.write_text("previous checksum")
    with pytest.raises(ValueError, match="inventory is missing"):
        package_publication(output, archive)
    page = output / "index.html"
    page.write_text('<img src="missing.png">')
    finalize_publication(output, tmp_path / "build", [page], {}, Publication())
    with pytest.raises(ValueError, match="missing local resource"):
        package_publication(output, archive)
    page.write_text("changed after publication")
    with pytest.raises(ValueError, match="changed since"):
        package_publication(output, archive)
    assert archive.read_bytes() == b"previous release"
    assert sidecar.read_text() == "previous checksum"


def test_repair_rejects_producer_outside_owned_roots(tmp_path):
    records = Publication(
        artifacts=[
            Artifact(
                path="lost.svg", role="media", sha256="missing", producer=str(tmp_path / "unowned")
            )
        ]
    )
    with pytest.raises(ValueError, match="outside build roots"):
        repair_media(tmp_path / "site", tmp_path / "build", records)


def test_legacy_adoption_recognizes_reserved_temps_only(tmp_path):
    output = tmp_path / "site"
    output.mkdir()
    (output / ".dojo-tmp-index.html.0.html").write_text("temporary")
    (output / "index.html").write_text("final")
    (output / ".dojo-tmp-independent").write_text("unowned")
    ninja = tmp_path / "build.ninja"
    ninja.write_text(f"rule example\n  command = true\nbuild {output / 'index.html'}: example\n")
    result = import_legacy_publication(output, ninja)
    assert {item.path for item in result.artifacts} == {".dojo-tmp-index.html.0.html", "index.html"}


def test_media_replacement_rolls_back_on_failure(tmp_path, monkeypatch):
    source = tmp_path / "incoming"
    source.mkdir()
    destination = tmp_path / "published"
    destination.mkdir()
    (destination / "previous.svg").write_text("last working image")

    def fail(*args, **kwargs):
        message = "disk full"
        raise OSError(message)

    monkeypatch.setattr("dojo.wrap.shutil.copytree", fail)
    with pytest.raises(OSError, match="disk full"):
        _publish_media(source, destination)
    assert (destination / "previous.svg").read_text() == "last working image"
    with pytest.raises(OSError, match="disk full"):
        _publish_media(source, tmp_path / "new")


def test_atomic_copy_and_multi_input_execution(tmp_path):
    first, second, output = (tmp_path / name for name in ("first file", "second file", "combined"))
    first.write_text("one")
    second.write_text("two")
    with pytest.raises(SystemExit) as result:
        run_wrap(
            [
                "--atomic",
                "--in-file",
                str(first),
                "--additional-in-file",
                str(second),
                "--out-file",
                str(output),
                "--",
                sys.executable,
                "-c",
                "import sys;from pathlib import Path;Path(sys.argv[1]).write_text(''.join(Path(p).read_text() for p in sys.argv[2:]))",
                "{out_abs}",
                "{in_all}",
            ]
        )
    assert result.value.code == 0
    assert output.read_text() == "onetwo"
    with pytest.raises(SystemExit) as result:
        run_wrap(["--atomic", "--out-file", str(output), "--copy", "--", str(first), "{out_abs}"])
    assert result.value.code == 0
    assert output.read_text() == "one"


def test_lock_restores_previous_environment_even_on_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("DOJO_BUILD_LOCK", "another project")
    message = "failure"
    with pytest.raises(RuntimeError), build_lock(tmp_path):
        raise RuntimeError(message)
    assert os.environ["DOJO_BUILD_LOCK"] == "another project"


def test_atomic_media_publication_replaces_only_its_owned_directory(tmp_path):
    source = tmp_path / "input.json"
    source.write_text("{}")
    build = tmp_path / "build"
    build.mkdir()
    publication = tmp_path / "site/nested/index.html"
    publication.parent.mkdir(parents=True)
    output = build / "intermediate.html"
    media = publication.parent / "media/owned"
    media.mkdir(parents=True)
    (media / "obsolete.svg").write_text("obsolete")
    program = "import sys;from pathlib import Path;Path('media/owned').mkdir(parents=True);Path('media/owned/new.svg').write_text('<svg/>');Path(sys.argv[1]).write_text(sys.argv[2])"
    with pytest.raises(SystemExit) as result:
        run_wrap(
            [
                "--atomic",
                "--in-file",
                str(source),
                "--out-file",
                str(output),
                "--out-dir",
                str(tmp_path / "site"),
                "--build-dir",
                str(build),
                "--publication-file",
                str(publication),
                "--media-dir",
                "media/owned",
                "--cwd",
                "{publication_dir}",
                "--",
                sys.executable,
                "-c",
                program,
                "{out_abs}",
                "{root_val}",
            ]
        )
    assert result.value.code == 0
    assert output.read_text() == ".."
    assert (media / "new.svg").exists()
    assert not (media / "obsolete.svg").exists()
