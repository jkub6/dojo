"""Asset processing stage: Dependency tracking and copying.

This module handles asset dependency discovery and copying for the
build pipeline, including scanning CSS and HTML files for referenced
resources.
"""

from __future__ import annotations

import logging
from collections import deque
from pathlib import Path

from dojo.constants import RuleName
from dojo.deps import resolve_glob_dependencies, scan_css_dependencies, scan_html_dependencies
from dojo.emitter import NinjaEmitter
from dojo.paths import ninja_quote, sanitize_path
from dojo.yaml_utils import extract_paths, get_frontmatter_assets, parse_frontmatter

logger = logging.getLogger(__name__)


class AssetProcessor:
    """Handles asset dependency tracking and copying.

    Discovers and copies assets referenced by content files, including
    recursive scanning of CSS and HTML for nested dependencies.

    Attributes:
        src: Path to source directory
        out_dir: Path to output directory
        emitter: Ninja file emitter
        copied_assets: Set tracking already-copied assets
        all_outputs: List tracking all final output paths

    """

    def __init__(
        self,
        src: Path,
        out_dir: Path,
        emitter: NinjaEmitter,
        copied_assets: set[Path],
        all_outputs: list[Path],
    ) -> None:
        """Initialize the asset processor.

        Args:
            src: Path to source directory
            out_dir: Path to output directory
            emitter: Ninja file emitter
            copied_assets: Shared set tracking already-copied assets
            all_outputs: Shared list tracking all final output paths

        """
        self.src = src
        self.out_dir = out_dir
        self.emitter = emitter
        self.copied_assets = copied_assets
        self.all_outputs = all_outputs

    def process_assets(self, md_path: Path) -> list[Path]:
        """Process and copy assets referenced by a Markdown file.

        Discovers assets from:
        - Frontmatter 'css' field
        - Frontmatter 'dependencies' glob patterns
        - Recursive CSS url() references
        - Recursive HTML src/href references

        Args:
            md_path: Absolute path to source Markdown file

        Returns:
            List of absolute paths to the copied/referenced assets in the output directory.

        """
        # 1. Get initial assets from frontmatter 'css'
        pending_assets = set(get_frontmatter_assets(md_path))

        # 2. Get assets from 'dependencies' glob patterns
        frontmatter = parse_frontmatter(md_path)
        if frontmatter and "dependencies" in frontmatter:
            dep_patterns = extract_paths(frontmatter, ["dependencies"])
            glob_assets = resolve_glob_dependencies(md_path.parent, dep_patterns)
            pending_assets.update(glob_assets)

        # 3. Recursive processing loop
        # We use a while loop to handle nested dependencies discovered during scanning
        queue = deque(pending_assets)
        processed_assets: set[Path] = set()
        output_assets: list[Path] = []

        while queue:
            asset = queue.popleft()

            # Avoid processing the same asset twice in this cycle
            if asset in processed_assets:
                continue
            processed_assets.add(asset)

            # Self-reference check: Don't copy the source markdown file itself
            if asset.resolve() == md_path.resolve():
                continue

            try:
                rel_asset = asset.relative_to(self.src)
            except ValueError:
                logger.warning(
                    "Referenced asset outside source directory, cannot auto-copy: %s",
                    asset,
                )
                continue

            final_path = sanitize_path(self.out_dir, rel_asset)
            output_assets.append(final_path)

            # Global deduplication: Only emit COPY rule once per build
            if final_path not in self.copied_assets:
                self.emitter.build(
                    outputs=final_path,
                    rule=RuleName.COPY.value,
                    inputs=asset,
                    variables={
                        "in_shell": ninja_quote(asset),
                        "out_shell": ninja_quote(final_path),
                    },
                )
                self.copied_assets.add(final_path)
                self.all_outputs.append(final_path)
                self.emitter.newline()

            # Smart Scanning: Look for nested dependencies
            if asset.suffix.lower() == ".css":
                new_deps = scan_css_dependencies(asset)
                queue.extend(dep for dep in new_deps if dep not in processed_assets)
            elif asset.suffix.lower() == ".html":
                new_deps = scan_html_dependencies(asset)
                queue.extend(dep for dep in new_deps if dep not in processed_assets)

        return output_assets

    def process_static_assets(self, static_dirs: list[str]) -> list[Path]:
        """Process and copy directories marked as static assets.

        Args:
            static_dirs: List of directory paths (relative to src or absolute)

        Returns:
            List of absolute paths to all discovered/copied files in the output directory.

        """
        static_outputs: list[Path] = []
        for static_dir in static_dirs:
            static_path = (
                (self.src / static_dir).resolve()
                if not Path(static_dir).is_absolute()
                else Path(static_dir).resolve()
            )
            if not static_path.exists():
                continue

            for file in static_path.rglob("*"):
                if not file.is_file():
                    continue

                try:
                    rel_file = file.relative_to(static_path)
                except ValueError:
                    continue

                if any(part.startswith(".") for part in rel_file.parts):
                    continue

                final_path = sanitize_path(self.out_dir, rel_file)
                static_outputs.append(final_path)

                if final_path not in self.copied_assets:
                    self.emitter.build(
                        outputs=final_path,
                        rule=RuleName.COPY.value,
                        inputs=file,
                        variables={
                            "in_shell": ninja_quote(file),
                            "out_shell": ninja_quote(final_path),
                        },
                    )
                    self.copied_assets.add(final_path)
                    self.all_outputs.append(final_path)

        return static_outputs
