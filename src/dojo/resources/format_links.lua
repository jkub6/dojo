--- format_links.lua
--- Computes cross-format sibling links from dojo-injected metadata.
---
--- This filter reads 'dojo-sibling-formats' metadata (injected by dojo's
--- generated defaults files) and uses PANDOC_STATE.output_file to compute
--- relative hrefs to sibling output formats for the same source document.
---
--- The result is injected as 'format-links' metadata, which custom Pandoc
--- templates can consume with $for(format-links)$ ... $endfor$.
---
--- Internal dojo-* metadata keys are cleaned up so they don't leak to output.

--- Extract the filename (basename) from a file path.
--- Falls back to string manipulation if pandoc.path is unavailable.
local function get_basename(filepath)
  -- Try pandoc.path.split first (available in Pandoc >= 2.12)
  if pandoc.path and pandoc.path.split then
    local _, base = pandoc.path.split(filepath)
    if base and base ~= "" then
      return base
    end
  end

  -- Fallback: use string pattern matching
  -- Match everything after the last / or \ separator
  local base = filepath:match("[/\\]([^/\\]+)$")
  if base then
    return base
  end

  -- No separator found: the whole string is the filename
  return filepath
end

function Pandoc(doc)
  local siblings = doc.meta["dojo-sibling-formats"]
  if not siblings then return end

  -- Get the output file path from Pandoc state
  -- PANDOC_STATE.output_file may be nil if no -o flag was used,
  -- or may be a non-string type in some Pandoc versions.
  local raw_output = PANDOC_STATE and PANDOC_STATE.output_file
  if raw_output == nil then return end

  -- Ensure we have a plain Lua string
  local output = tostring(raw_output)
  if output == "" or output == "nil" then return end

  -- Extract just the filename from the output path
  local base = get_basename(output)
  if not base or base == "" then return end

  -- Remove extension to get the stem
  local stem = base:match("^(.+)%.[^.]+$") or base

  -- Strip the current output's suffix to recover the "pure" document stem
  -- e.g., "article-slides" with suffix "-slides" → "article"
  local my_suffix = pandoc.utils.stringify(doc.meta["dojo-current-suffix"] or "")
  if my_suffix ~= "" and stem:sub(-#my_suffix) == my_suffix then
    stem = stem:sub(1, -(#my_suffix + 1))
  end

  -- Build format link entries for template consumption
  local links = pandoc.List()
  for _, fmt in ipairs(siblings) do
    local label = pandoc.utils.stringify(fmt.label or "")
    local suffix = pandoc.utils.stringify(fmt.suffix or "")
    local ext = pandoc.utils.stringify(fmt.extension or "")

    if label ~= "" and ext ~= "" then
      links:insert(pandoc.MetaMap({
        label = pandoc.MetaString(label),
        href = pandoc.MetaString(stem .. suffix .. "." .. ext),
      }))
    end
  end

  if #links > 0 then
    doc.meta["format-links"] = pandoc.MetaList(links)
  end

  -- Clean up internal metadata so it doesn't leak to output
  doc.meta["dojo-sibling-formats"] = nil
  doc.meta["dojo-current-suffix"] = nil

  return doc
end
