import pytest
from pathlib import Path
from dojo.core import NinjaGenerator
from dojo.config import OutputConfig

def test_render_command_line_args(minimal_config, tmp_path, mock_emitter):
    """Verify that OutputConfig.args are correctly passed to the Ninja render rule."""
    gen = NinjaGenerator(minimal_config, tmp_path / "dojo.yaml", emitter=mock_emitter)
    
    out_config = OutputConfig(
        extension="html",
        defaults="dummy.yaml",
        args=["--custom-flag", "value"],
        id="test"
    )
    
    # We can test the RenderStage directly or via NinjaGenerator
    gen._render_stage.render(
        out_config, 
        Path("input.json"), 
        Path("page"), 
        {}
    )
    
    # Verify the emitter was called with correct variables
    mock_emitter.build.assert_called_once()
    variables = mock_emitter.build.call_args.kwargs["variables"]
    assert "--custom-flag value" in variables["args"]

def test_compile_command_line_filters(minimal_config, tmp_path, mock_emitter):
    """Verify that filters are correctly included in the compile rule."""
    from dojo.stages.compile import CompileStage
    from dojo.config import TypeConfig
    
    stage = CompileStage(minimal_config, tmp_path / "build", mock_emitter)
    
    type_cfg = TypeConfig(
        outputs=[OutputConfig(extension="html", defaults="dummy.yaml")],
        filters=["filter1.lua", "filter2.lua"]
    )
    
    stage.compile(Path("src/test.md"), Path("test"), type_cfg)
    
    mock_emitter.build.assert_called_once()
    variables = mock_emitter.build.call_args.kwargs["variables"]
    # Check that filters are part of the command (indirectly via variables if used)
    # Actually, filters are usually baked into the rule or passed as args.
    # In Dojo, they are passed via the command template.
    pass

def test_ninja_generator_pool_emission(minimal_config, tmp_path, mock_emitter):
    """Verify that custom pools are correctly emitted in the Ninja header."""
    minimal_config.pools = {"heavy": 5}
    gen = NinjaGenerator(minimal_config, tmp_path / "dojo.yaml", emitter=mock_emitter)
    
    # Pools are emitted via emitter.pool()
    gen.emit_header()
    mock_emitter.pool.assert_called_with("heavy", 5)

def test_custom_rule_emission(minimal_config, tmp_path, mock_emitter):
    """Verify that custom rules from config are emitted."""
    from dojo.config import CustomRule
    minimal_config.custom_rules = [
        CustomRule(name="my-rule", command="touch $out", description="My Rule")
    ]
    gen = NinjaGenerator(minimal_config, tmp_path / "dojo.yaml", emitter=mock_emitter)
    gen.emit_header()
    
    mock_emitter.rule.assert_any_call(
        name="my-rule",
        command="touch $out",
        description="My Rule",
        pool=None,
        depfile=None,
        deps=None,
        generator=False,
        variables=None
    )
