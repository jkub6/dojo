"""Plugin contributions and configuration errors fail before replacing the graph."""

from __future__ import annotations

import io
from pathlib import Path

import pytest
import yaml
from test_workflows import project  # noqa: F401

from dojo.config import CustomRule, OutputConfig, load_config, order_outputs
from dojo.core import NinjaGenerator
from dojo.defaults import materialize_defaults
from dojo.emitter import NinjaEmitter
from dojo.exceptions import ConfigInvalidError
from dojo.plugins import BuildContribution, PluginInterface, PreparedInput
from dojo.stages._defaults import consumes_assets, resolve_stage_dependencies
from dojo.stages.assets import AssetProcessor
from dojo.yaml_utils import get_recursive_yaml_deps, resolve_input, template_dependencies


class Contribution(PluginInterface):
    def prepare(self, context):
        source = context.sources[0]
        assert context.ast_path(source).name == "index.json"
        return BuildContribution(
            prepared=(
                PreparedInput(
                    source,
                    inputs=(context.project_root / "settings.txt",),
                    metadata={"title": "Contributed title"},
                    assets={context.project_root / "image.svg": Path("image.svg")},
                ),
            ),
            static_dirs=(),
        )


def test_preparation_products_are_declared_without_host_mutation(project):  # noqa: F811
    (project / "content/index.md").write_text("# Prepared")
    (project / "settings.txt").write_text("settings")
    (project / "image.svg").write_text("<svg/>")
    config, path = load_config(str(project / "dojo.yaml"))
    generator = NinjaGenerator(config, path, plugins=[Contribution()])
    generator.generate()
    graph = (project / "_build/build.ninja").read_text()
    assert "settings.txt" in graph
    assert "title=Contributed" in graph
    assert "image.svg" in graph
    assert config.static_dirs == []
    with pytest.raises(ValueError, match="Multiple plugins prepare"):
        NinjaGenerator(config, path, plugins=[Contribution(), Contribution()]).generate()


class Mutating(PluginInterface):
    def prepare(self, context):
        context.config.exclude.append("*.md")
        return BuildContribution()


class StaticSelector(PluginInterface):
    def prepare(self, context):
        return BuildContribution(static_dirs=())


class ConflictingRules(PluginInterface):
    def get_custom_rules(self):
        return [CustomRule(name="copy", command="true")]


class InvalidPool(PluginInterface):
    def get_custom_rules(self):
        return [CustomRule(name="custom", command="true", pool="absent")]


@pytest.mark.parametrize(
    ("plugins", "message"),
    [
        ([Mutating()], "mutated config"),
        ([StaticSelector(), StaticSelector()], "Only one plugin"),
        ([ConflictingRules()], "Conflicting build rule"),
        ([InvalidPool()], "undefined pool"),
    ],
)
def test_invalid_plugin_contract_preserves_previous_graph(project, plugins, message):  # noqa: F811
    config, path = load_config(str(project / "dojo.yaml"))
    build = project / "_build"
    build.mkdir()
    graph = build / "build.ninja"
    graph.write_text("# previous graph\n")
    with pytest.raises(ValueError, match=message):
        NinjaGenerator(config, path, plugins=plugins).generate()
    assert graph.read_text() == "# previous graph\n"


def test_defaults_execution_and_dependency_resolution_agree(tmp_path):
    defaults = tmp_path / "defaults.yaml"
    nested = tmp_path / "nested.yaml"
    filter_path = tmp_path / "filter.lua"
    filter_path.write_text("return {}")
    nested.write_text("standalone: true\n")
    defaults.write_text(
        yaml.safe_dump(
            {
                "defaults": "nested.yaml",
                "filters": [{"type": "lua", "path": "filter.lua"}, {"type": "citeproc"}],
                "template": "html",
                "bibliography": ["https://example.invalid/refs.json"],
                "metadata-files": [],
            }
        )
    )
    generated = materialize_defaults(defaults, tmp_path, None, tmp_path / "build")
    data = yaml.safe_load(generated.read_text())
    assert Path(data["defaults"]).is_file()
    assert data["filters"][0]["path"] == str(filter_path)
    assert filter_path in get_recursive_yaml_deps(defaults, root=tmp_path)
    assert data["bibliography"] == ["https://example.invalid/refs.json"]
    assert resolve_input("bibliography", "https://example.invalid/refs.json", tmp_path, []) is None
    assert resolve_input("filters", "definitely-missing-executable", tmp_path, []) is None
    assert resolve_input("filters", "pandoc", tmp_path, []).is_file()


@pytest.mark.parametrize(
    ("contents", "message"),
    [
        ("defaults: defaults.yaml", "Cyclic defaults"),
        ("[not, a, mapping]", "Invalid or missing defaults"),
        ("filters: [missing.lua]", "Missing filters"),
        ("defaults: absent", "Missing defaults"),
    ],
)
def test_invalid_defaults_do_not_produce_execution_file(tmp_path, contents, message):
    defaults = tmp_path / "defaults.yaml"
    defaults.write_text(contents)
    with pytest.raises((ValueError, FileNotFoundError), match=message):
        materialize_defaults(defaults, tmp_path, None, tmp_path / "build")
    assert not (tmp_path / "build").exists()


def test_templates_follow_builtin_partials_and_detect_missing_ones(tmp_path):
    template = tmp_path / "template.html"
    template.write_text("$styles.html()$")
    assert template_dependencies(template)
    assert template_dependencies(template, {template}) == []
    template.write_text("$missing-partial()$")
    with pytest.raises(FileNotFoundError, match="Missing template partial"):
        template_dependencies(template)


@pytest.mark.parametrize(
    "change",
    [
        {"custom_rules": [{"name": "custom", "command": "true", "pool": "missing"}]},
        {"pools": {"valid": 1}, "rule_pools": {"unknown": "valid"}},
    ],
)
def test_invalid_rule_pools_are_diagnosed(project, change):  # noqa: F811
    path = project / "dojo.yaml"
    data = yaml.safe_load(path.read_text())
    data.update(change)
    path.write_text(yaml.safe_dump(data))
    with pytest.raises((ValueError, ConfigInvalidError), match=r"pool|rules"):
        NinjaGenerator(*load_config(str(path)))


def test_unknown_types_tools_and_unsafe_output_paths_fail_early(project):  # noqa: F811
    config, path = load_config(str(project / "dojo.yaml"))
    (project / "content/index.md").write_text("---\ntype: typo\n---\nBody")
    with pytest.raises(ValueError, match="unknown content type"):
        NinjaGenerator(config, path).generate()
    config.types["page"].outputs[0].tool = "missing"
    with pytest.raises(ValueError, match="Unknown output tool"):
        NinjaGenerator(config, path)
    with pytest.raises(ValueError, match="path separators"):
        order_outputs("page", [OutputConfig(extension="../html", defaults="defaults.yaml")])


def test_output_resource_policy_is_explicit(tmp_path):
    assert consumes_assets(OutputConfig(extension="html", defaults=[], consumes_assets=True))
    assert not consumes_assets(OutputConfig(extension="pdf", defaults=[], consumes_assets=False))
    assert consumes_assets(OutputConfig(extension="pdf", defaults=[]))
    assert consumes_assets(OutputConfig(extension="html", defaults=[], args=["--embed-resources"]))
    assert not consumes_assets(OutputConfig(extension="html", defaults=[]))
    cache = {}
    defaults = tmp_path / "empty.yaml"
    defaults.write_text("{}")
    resolve_stage_dependencies(str(defaults), cache=cache)
    assert resolve_stage_dependencies(str(defaults), cache=cache)[1] == [defaults]
    assert resolve_stage_dependencies(str(defaults))[1] == [defaults]
    stylesheet = tmp_path / "style.css"
    stylesheet.write_text("body { color: blue; }")
    defaults.write_text("css: style.css\n")
    assert not consumes_assets(
        OutputConfig(extension="html", defaults=str(defaults)), project_root=tmp_path
    )
    defaults.write_text("template: true")
    generated = materialize_defaults(defaults, tmp_path, None, tmp_path / "build")
    assert yaml.safe_load(generated.read_text())["template"] is True


def test_custom_rule_with_pool_and_bare_tool_names_loads(project):  # noqa: F811
    path = project / "dojo.yaml"
    data = yaml.safe_load(path.read_text())
    data.update(
        pools={"serial": 1},
        custom_rules=[{"name": "custom", "command": "true", "pool": "serial"}],
        tools={"pandoc": "pandoc"},
    )
    path.write_text(yaml.safe_dump(data))
    config, _ = load_config(str(path))
    assert config.custom_rules[0].pool == "serial"


def test_duplicate_asset_and_output_ownership_are_rejected(tmp_path):

    emitter = NinjaEmitter(io.StringIO())
    assets = AssetProcessor(tmp_path, tmp_path / "site", emitter, set(), [])
    assets.copy_assets({tmp_path / "first": Path("same.svg")})
    with pytest.raises(ValueError, match="Conflicting asset"):
        assets.copy_assets({tmp_path / "second": Path("same.svg")})
    with pytest.raises(ValueError, match="Multiple build rules"):
        emitter.build(tmp_path / "site/same.svg", "render")
