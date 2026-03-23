import time

from dojo.cli import main

PERF_THRESHOLD_SECONDS = 2.0


def test_generation_performance_large_project(tmp_path):
    """Verify that Ninja generation remains fast even for larger projects.

    Target: 100 source files generated in < 1 second.
    """
    project = tmp_path / "large_project"
    project.mkdir()

    src = project / "src"
    src.mkdir()

    # Create 100 markdown files
    for i in range(100):
        (src / f"page_{i}.md").write_text(
            f"---\ntitle: Page {i}\n---\n# Content {i}\n", encoding="utf-8"
        )

    config_path = project / "dojo.yaml"
    config_path.write_text(
        f"""
src_dir: "{src}"
output_dir: "{project / "_site"}"
build_dir: "{project / "_build"}"
default_type: page
types:
  page:
    outputs:
      - id: html
        extension: html
        defaults: []
""",
        encoding="utf-8",
    )

    start_time = time.perf_counter()

    main(["--quiet", "build", "-c", str(config_path)])

    end_time = time.perf_counter()
    duration = end_time - start_time

    # Threshold: 100 files should easily be processed in under 1 second on modern hardware.
    # We use 2.0s as a conservative CI-friendly threshold.
    assert duration < PERF_THRESHOLD_SECONDS, f"Ninja generation took too long: {duration:.2f}s"
