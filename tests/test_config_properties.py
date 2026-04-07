import contextlib
from unittest.mock import patch

from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st
from pydantic import ValidationError

from dojo.config import Config, CustomRule, OutputConfig, PipelineStep, ToolPaths, TypeConfig
from dojo.exceptions import DojoError

# Strategies for inner models
st_tool_paths = st.builds(ToolPaths)


@st.composite
def st_output_config(draw):
    """Generate a valid OutputConfig object."""
    id_val = draw(st.one_of(st.none(), st.text(min_size=1)))
    extension = draw(st.text(min_size=1))
    suffix = draw(st.text())
    args = draw(st.one_of(st.none(), st.lists(st.text())))
    label = draw(st.one_of(st.none(), st.text()))
    post_process = draw(st.lists(st.builds(PipelineStep, tool=st.text(min_size=1))))

    # Logic to satisfy OutputConfig model_validator:
    # - If source is present, tool must be present.
    # - If source is absent, defaults must be present.
    if draw(st.booleans()):
        # Case 1: Derived output - needs source and tool
        source = draw(st.one_of(st.text(min_size=1), st.lists(st.text(min_size=1), min_size=1)))
        tool = draw(st.text(min_size=1))
        defaults = draw(st.one_of(st.none(), st.text(), st.lists(st.text())))
    else:
        # Case 2: Primary output - needs defaults, source is None
        source = None
        tool = draw(st.one_of(st.none(), st.text()))
        defaults = draw(st.one_of(st.text(min_size=1), st.lists(st.text(min_size=1), min_size=1)))

    return OutputConfig(
        id=id_val,
        extension=extension,
        defaults=defaults,
        suffix=suffix,
        post_process=post_process,
        args=args,
        source=source,
        tool=tool,
        label=label,
    )


@st.composite
def st_type_config(draw):
    """Generate a valid TypeConfig object."""
    return TypeConfig(
        outputs=draw(st.lists(st_output_config(), min_size=1)),
        defaults=draw(st.one_of(st.none(), st.text(), st.lists(st.text()))),
    )


st_custom_rule = st.builds(CustomRule, name=st.text(min_size=1), command=st.text(min_size=1))


@st.composite
def st_config(draw):
    """Generate a Config-like dictionary with consistent default_type."""
    types = draw(st.dictionaries(st.text(min_size=1), st_type_config(), min_size=1))
    default_type = draw(st.sampled_from(list(types.keys())))

    # Return a dictionary that can be used to validate a Config object
    # This avoids running validators during draw when mocks aren't active
    return {
        "default_type": default_type,
        "types": {name: t.model_dump() for name, t in types.items()},
        "src_dir": draw(st.text(min_size=1)),
        "output_dir": draw(st.text(min_size=1)),
        "build_dir": draw(st.text(min_size=1)),
        "tools": draw(st_tool_paths).model_dump(),
        "custom_rules": [r.model_dump() for r in draw(st.lists(st_custom_rule))],
        "pools": draw(st.dictionaries(st.text(min_size=1), st.integers(min_value=1))),
    }


@settings(max_examples=20, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(st_config())
def test_config_robustness(config_dict):
    """Verify that validated config objects can at least be initialized without crashing if filesystem checks are bypassed."""
    # We mock the filesystem-dependent validators to focus on schema and cross-field logic
    with (
        patch("dojo.config.Config.validate_src_dir", side_effect=lambda v: v),
        patch("dojo.config.Config.validate_pandoc_data_dir", side_effect=lambda v: v),
        patch("dojo.config.Config._resolve_all_defaults", side_effect=lambda: None),
        patch("dojo.config.Config._validate_directories", side_effect=lambda: None),
        contextlib.suppress(ValidationError, DojoError),
    ):
        Config.model_validate(config_dict)


@given(st.dictionaries(st.text(), st.one_of(st.text(), st.integers(), st.lists(st.text()))))
def test_config_fuzz_random_dict(d):
    """Fuzz Config.model_validate with completely random dictionaries."""
    with (
        patch("dojo.config.Config.validate_src_dir", side_effect=lambda v: v),
        patch("dojo.config.Config.validate_pandoc_data_dir", side_effect=lambda v: v),
        patch("dojo.config.Config._resolve_all_defaults", side_effect=lambda: None),
        contextlib.suppress(ValidationError, DojoError, TypeError, KeyError),
    ):
        Config.model_validate(d)
        # No other exceptions (like RecursionError or Segfaults) should occur
