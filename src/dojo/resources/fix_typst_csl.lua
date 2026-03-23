-- fix_typst_csl.lua
-- This filter shipped by Dojo resolves the Pandoc relative path escaping bug for Typst outputs.
-- It dynamically adjusts CSL and bibliography file paths to root-relative paths, calculated seamlessly 
-- via metadata variables (`dojo-rel-src-dir` and `dojo-data-dir`) injected by the Dojo build module.

local function rewrite_path(p, meta)
  local path_str = pandoc.utils.stringify(p)
  -- If it's already root-relative or an absolute URL, leave it alone
  if path_str:match("^/") or path_str:match("^http") then return p end

  -- Resolve dynamic metadata from dojo/rules.py
  local rel_src_dir = meta["dojo-rel-src-dir"] and pandoc.utils.stringify(meta["dojo-rel-src-dir"]) or ""
  local data_dir = meta["dojo-data-dir"] and pandoc.utils.stringify(meta["dojo-data-dir"]) or ""

  -- Determine if the path is a CSL by checking common extensions or keywords
  -- Dojo by default resolves CSLs against the data_dir via citeproc, so we mirror that for Typst natively.
  if path_str:match("%.csl$") or path_str:match("chicago%-notes%-bibliography") then
    local filename = path_str:match("([^/]+)$") or path_str
    local csl_prefix = data_dir ~= "" and ("/" .. data_dir .. "/csl/") or "/csl/"
    -- Remove double slashes just in case
    csl_prefix = csl_prefix:gsub("//+", "/")
    return csl_prefix .. filename
  end

  -- For standard bibliography paths (or other assets), resolve relative to the original source doc
  local src_prefix = rel_src_dir ~= "" and ("/" .. rel_src_dir .. "/") or "/"
  src_prefix = src_prefix:gsub("//+", "/")
  return src_prefix .. path_str
end

function Meta(meta)
  if FORMAT == "typst" then
    if meta.csl then
      meta.csl = rewrite_path(meta.csl, meta)
    end
    if meta.bibliography then
      local bib = meta.bibliography
      if type(bib) == "table" or type(bib) == "userdata" then
        if bib.t == "MetaList" then
          local new_bib = pandoc.MetaList({})
          for i, v in ipairs(bib) do
            new_bib:insert(rewrite_path(v, meta))
          end
          meta.bibliography = new_bib
        else
          meta.bibliography = rewrite_path(meta.bibliography, meta)
        end
      else
        meta.bibliography = rewrite_path(meta.bibliography, meta)
      end
    end
  end
  return meta
end
