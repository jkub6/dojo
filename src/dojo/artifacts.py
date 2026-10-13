"""Publication ownership, recovery, and deterministic archive creation."""

from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import tarfile
import tempfile
from pathlib import Path

from pydantic import BaseModel, ConfigDict, Field

from .io import write_changed
from .paths import sanitize_path
from .validation import validate_output

MANIFEST_NAME = "dojo-publication.json"


class Artifact(BaseModel):
    """One owned file, with enough information to detect modification or loss."""

    model_config = ConfigDict(extra="forbid")
    path: str
    sha256: str
    role: str = "publication"
    producer: str | None = None


class Publication(BaseModel):
    """Versioned inventory; never infer ownership from arbitrary output files."""

    model_config = ConfigDict(extra="forbid")
    schema_version: int = 1
    artifacts: list[Artifact] = Field(default_factory=list)


def checksum(path: Path) -> str:
    """Hash a file without loading large publications into memory."""
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def load_publication(path: Path) -> Publication:
    """Load supported ownership records, refusing unknown schemas."""
    result = Publication.model_validate_json(path.read_text()) if path.is_file() else Publication()
    if result.schema_version != 1:
        message = f"Unsupported publication schema: {result.schema_version}"
        raise ValueError(message)
    return result


def import_legacy_publication(output: Path, ninja_file: Path) -> Publication:
    """Adopt only outputs declared by the previous Dojo graph during migration."""
    if not ninja_file.is_file() or not (ninja := shutil.which("ninja")):
        return Publication()
    result = subprocess.run(  # noqa: S603 - resolved executable and explicit argv
        [ninja, "-f", str(ninja_file), "-t", "targets", "all"],
        capture_output=True,
        text=True,
        check=True,
    )
    records = []
    for line in result.stdout.splitlines():
        name, _, _rule = line.rpartition(": ")
        path = Path(name)
        if path.is_absolute() and path.is_relative_to(output) and path.is_file():
            records.append(
                Artifact(
                    path=path.relative_to(output).as_posix(), sha256=checksum(path), role="legacy"
                )
            )
    # The old engine reserved .dojo-tmp-* for its pipelines. Retain their ownership
    # even if a generate-only invocation has already replaced the previous graph.
    owned = {item.path for item in records}
    for temporary in output.rglob(".dojo-tmp-*"):
        match = re.fullmatch(r"\.dojo-tmp-(.+)\.\d+\.[^.]+", temporary.name)
        if match:
            for candidate in (temporary, temporary.with_name(match[1])):
                relative = candidate.relative_to(output).as_posix()
                if candidate.is_file() and relative not in owned:
                    records.append(
                        Artifact(path=relative, sha256=checksum(candidate), role="legacy")
                    )
                    owned.add(relative)
    return Publication(artifacts=records)


def repair_media(output: Path, build: Path, previous: Publication) -> None:
    """Invalidate a producer when one of its extracted products is lost/corrupt."""
    for item in previous.artifacts:
        if item.role != "media" or not item.producer:
            continue
        path = sanitize_path(output, Path(item.path))
        if not path.is_file() or checksum(path) != item.sha256:
            producer = Path(item.producer).resolve()
            if not (
                producer.is_relative_to(build.resolve())
                or producer.is_relative_to(output.resolve())
            ):
                message = f"Invalid media producer outside build roots: {producer}"
                raise ValueError(message)
            producer.unlink(missing_ok=True)


def check_publication_paths(output: Path, outputs: list[Path]) -> None:
    """Reserve engine-owned metadata before any publication files are replaced."""
    for path in outputs:
        relative = path.relative_to(output)
        if (
            not relative.parts
            or relative == Path(MANIFEST_NAME)
            or relative.parts[0] == "provenance"
        ):
            message = f"Reserved publication path: {relative}"
            raise ValueError(message)


def reconcile_outputs(output: Path, outputs: list[Path], previous: Publication) -> None:
    """Remove obsolete owned graph products before consumers observe stale resources.

    Older inventories did not distinguish assets from rendered publications.
    Dynamic media and provenance are reconciled separately during finalization.
    """
    current = {path.relative_to(output).as_posix() for path in outputs}
    for old in previous.artifacts:
        if old.role in {"asset", "publication", "legacy"} and old.path not in current:
            path = sanitize_path(output, Path(old.path))
            if path.is_file() and checksum(path) == old.sha256:
                path.unlink()


def finalize_publication(  # noqa: PLR0913 - the publication transaction names its roots and products
    output: Path,
    build: Path,
    outputs: list[Path],
    media: dict[Path, Path],
    previous: Publication,
    *,
    provenance: tuple[Path, ...] = (),
    assets: set[Path] | None = None,
) -> Publication:
    """Record successful outputs and reconcile only previously owned files."""
    check_publication_paths(output, outputs)
    records = {}
    for path in outputs:
        relative_path = path.relative_to(output)
        records[str(relative_path)] = Artifact(
            path=relative_path.as_posix(),
            sha256=checksum(path),
            role="asset" if assets and path in assets else "publication",
        )
    for directory, producer in media.items():
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                relative = path.relative_to(output).as_posix()
                records[relative] = Artifact(
                    path=relative, sha256=checksum(path), role="media", producer=str(producer)
                )
    for index, path in enumerate(provenance):
        provenance_path = Path("provenance") / f"{index:04d}-{path.name}"
        destination = sanitize_path(output, provenance_path)
        write_changed(destination, path.read_bytes())
        records[provenance_path.as_posix()] = Artifact(
            path=provenance_path.as_posix(), sha256=checksum(destination), role="provenance"
        )
    publication = Publication(artifacts=[records[key] for key in sorted(records)])
    # Never delete an independently modified file. It remains outside the inventory.
    for old in previous.artifacts:
        path = sanitize_path(output, Path(old.path))
        if old.path not in records and path.is_file() and checksum(path) == old.sha256:
            path.unlink()
    serialized = publication.model_dump_json(indent=2) + "\n"
    public = publication.model_copy(deep=True)
    for artifact in public.artifacts:
        artifact.producer = None
    write_changed(
        output / MANIFEST_NAME, public.model_dump_json(indent=2, exclude_none=True) + "\n"
    )
    write_changed(build / "publication.json", serialized)
    return publication


def _verify_inventory(output: Path, publication: Publication) -> None:
    for item in publication.artifacts:
        path = sanitize_path(output, Path(item.path))
        if not path.is_file() or checksum(path) != item.sha256:
            message = f"Publication changed since its successful build: {item.path}"
            raise ValueError(message)


def package_publication(
    output: Path, archive: Path, *, links: bool = False, offline: bool = False
) -> None:
    """Validate and atomically archive exactly the inventoried publication."""
    manifest = output / MANIFEST_NAME
    if not manifest.is_file():
        message = "Build the publication before packaging; its inventory is missing"
        raise ValueError(message)
    publication = load_publication(manifest)
    paths = [item.path for item in publication.artifacts]
    _verify_inventory(output, publication)
    paths.append(MANIFEST_NAME)
    archive.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="dojo-package-", dir=archive.parent) as temporary:
        staging = Path(temporary)
        packed = staging / "release.txz"
        with tarfile.open(packed, "w:xz", preset=9) as tar:
            for name in sorted(paths):
                path = sanitize_path(output, Path(name))
                info = tar.gettarinfo(str(path), arcname=name)
                info.uid = info.gid = info.mtime = 0
                info.uname = info.gname = ""
                info.mode = 0o644
                # Dereference publication symlinks; no link may point outside the archive.
                info.type = tarfile.REGTYPE
                info.linkname = ""
                info.size = path.stat().st_size
                with path.open("rb") as stream:
                    tar.addfile(info, stream)
        extracted = staging / "extracted"
        with tarfile.open(packed) as tar:
            tar.extractall(extracted, filter="data")
        # Validate the bytes actually archived, including a concurrently changed manifest.
        if load_publication(extracted / MANIFEST_NAME) != publication:
            message = "Publication inventory changed while packaging"
            raise ValueError(message)
        _verify_inventory(extracted, publication)
        errors = (
            validate_output(extracted, links=links, offline=offline)
            if any(extracted.rglob("*.html"))
            else []
        )
        if errors:
            raise ValueError("\n".join(errors))
        packed.replace(archive)
    write_changed(
        archive.with_name(archive.name + ".sha256"), checksum(archive) + "  " + archive.name + "\n"
    )
