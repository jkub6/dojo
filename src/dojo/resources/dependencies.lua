-- dependencies.lua
-- Tracks dependencies for Ninja build system
-- 1. Finds images in the document
-- 2. Reads 'dependencies' from metadata (supporting files and directories)
-- 3. Writes a Makefile-formatted .d file

local system = pandoc.system
local path = pandoc.path

-- Set of unique dependencies
local dependencies = {}
local target = nil
local depfile = nil

-- Helper to escape filenames for Makefile format
local function escape_makefile(s)
  return s:gsub(" ", "\\ ")
end

-- Add a path to dependencies if it exists (or just add it blindly for Ninja to complain/check)
local function add_dep(p)
  if p and p ~= "" then
    table.insert(dependencies, p)
  end
end

-- Recursive function to add folder contents
local function add_folder_recursive(dir)
  -- Add the directory itself (best effort for mtime updates)
  add_dep(dir)

  local ok, entries = pcall(system.list_directory, dir)
  if not ok or not entries then
    return
  end

  for _, entry in ipairs(entries) do
    if entry ~= "." and entry ~= ".." then
      local full_path = path.join({ dir, entry })
      -- Check if it's a directory by trying to list it
      -- This is a bit hacky but standard Lua/Pandoc check
      local is_dir_ok, _ = pcall(system.list_directory, full_path)

      if is_dir_ok then
        add_folder_recursive(full_path)
      else
        add_dep(full_path)
      end
    end
  end
end

function Pandoc(doc)
  -- 1. Get configuration
  if doc.meta.depfile then
    depfile = pandoc.utils.stringify(doc.meta.depfile)
  end

  if not depfile then
    -- If no depfile specified, we can't write output.
    -- In rigorous builds, we might warn, but here we just exit silently.
    return
  end

  -- Target is the output file (usually .json), which Ninja expects to match the rule output
  -- We assume the user passed -M target=$out or implicit assumption
  -- Actually, strict depfiles usually allow "target: source dep1 dep2"
  -- The $out is the target.

  if doc.meta.target then
    target = pandoc.utils.stringify(doc.meta.target)
  else
    -- Fallback: try to deduce from depfile?
    -- If depfile is "foo.json.d", target likely "foo.json"
    if depfile:match("%.d$") then
      target = depfile:sub(1, -3)
    else
      target = "output"
    end
  end

  -- 2. Walk AST for Images
  doc:walk({
    Image = function(img)
      add_dep(img.src)
    end,
  })

  -- 3. Check Metadata dependencies
  if doc.meta.dependencies then
    for _, item in ipairs(doc.meta.dependencies) do
      local item_path = pandoc.utils.stringify(item)
      -- Strip trailing slash if present (Pandoc list_directory doesn't like it)
      if item_path:sub(-1) == "/" or item_path:sub(-1) == "\\" then
        item_path = item_path:sub(1, -2)
      end

      -- Check if directory (heuristic: try to list it)
      local is_dir_ok, entries = pcall(system.list_directory, item_path)

      if is_dir_ok then
        add_folder_recursive(item_path)
      else
        add_dep(item_path)
      end
    end
  end

  -- 4. Write depfile
  local content = {}
  table.insert(content, escape_makefile(target) .. ":")

  -- Deduplicate
  local seen = {}
  table.sort(dependencies)

  for _, dep in ipairs(dependencies) do
    if not seen[dep] then
      -- Skip remote URLs
      if not dep:match("^https?://") and not dep:match("^data:") then
        table.insert(content, " " .. escape_makefile(dep))
        seen[dep] = true
      end
    end
  end

  local file = io.open(depfile, "w")
  if file then
    file:write(table.concat(content))
    file:write("\n")
    file:close()
  else
    io.stderr:write("Error: Could not write depfile to " .. depfile .. "\n")
  end
end
