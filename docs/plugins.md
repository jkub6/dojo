# Plugins

A configured Python file exports one `PluginInterface` subclass. It may import the class from an
installed package; the configuration file is a thin adapter. Paths are relative to `dojo.yaml`.
Modules receive unique names and are registered before execution so dataclasses and normal Python
import behavior work.

```yaml
plugins:
  - tools/catalog_plugin.py
```

## Preparation contract (Dojo 0.2)

```python
from dojo.plugins import BuildContribution, BuildContext, PluginInterface, PreparedInput


class ExamplePlugin(PluginInterface):
    priority = 50

    def prepare(self, context: BuildContext) -> BuildContribution:
        prepared = []
        for source in context.sources:
            # Your package resolves domain inputs and writes its own cached products.
            settings = context.project_root / "catalog.yaml"
            prepared.append(PreparedInput(source=source, inputs=(settings,)))
        return BuildContribution(prepared=tuple(prepared))
```

`BuildContext` provides an isolated configuration snapshot, config/project/source/ build/output
paths, the already filtered source inventory, a refresh flag, and `ast_path(source)`. Do not
rediscover sources or reopen the configuration. Do not mutate `context.config`; the host rejects
such changes.

A `PreparedInput` declares a discovered source, input paths that invalidate its compile edge, string
metadata passed to Pandoc, and asset mappings from absolute source paths to publication-relative
destinations. Dojo emits the actual edges and checks output collisions. Plugins own the semantics
and integrity of their cached products; `refresh=True` requests recomputation.

`BuildContribution` contains prepared inputs, project-wide `assets` mappings, optional replacement
static roots, and durable provenance files. Only one plugin may select replacement static roots, and
only one may prepare any source. Provenance is copied into the successful publication and included
in its inventory and archive. Do not put credentials or private cache state in provenance intended
for publication.

Preparation runs on every `dojo build`, including warm incremental builds. Preserve mtime when
prepared bytes are unchanged. It does not run under `--dry-run`.

## Other hooks

| Hook                                                                                | Purpose                                                 |
| ----------------------------------------------------------------------------------- | ------------------------------------------------------- |
| `get_custom_rules() -> list[CustomRule]`                                            | Declare additional rules; names and pools are validated |
| `modify_compile_edge(source, rel_stem, target_ast, variables, implicit_deps)`       | Return updated variables and dependencies               |
| `modify_render_edge(source_ast, rel_stem, target_output, variables, implicit_deps)` | Return updated render variables and dependencies        |
| `modify_output_config(output_config, content_type)`                                 | Return a configuration for an output                    |
| `get_extra_assets(config, out_dir)`                                                 | Legacy destination-to-source asset mappings             |
| `post_process_ninja(ninja_content)`                                                 | Final textual graph extension                           |

Lower numerical priority runs first. Prefer declarative preparation and explicit rule/output
dependencies. Edge and textual hooks are escape hatches for consumers that need them; their authors
must preserve Ninja quoting and dependency semantics. Builtin wrapper argv placeholders include
`{in_abs}`, `{in_all}`, `{out_abs}`, `{publication_dir}`, and `{root_val}`. Custom rule commands are
trusted shell code; use quoted variables (`$in_shell`, `$out_shell`) when implementing them.

The legacy `pre_generate(config, build_dir, *, refresh, src_dir)` is called by the default `prepare`
implementation. It can still prepare files but cannot mutate host configuration. Migrate discovery,
static-root selection, metadata, assets, and provenance to `BuildContribution`. This change requires
Dojo 0.2 or newer.
