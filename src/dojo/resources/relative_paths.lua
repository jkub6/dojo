-- relative_paths.lua
-- Automates relative path resolution for Dojo static sites.
-- Converts paths starting with / to be relative to the site root using the $root$ metadata.

local root = ""

function Meta(meta)
    if meta.root then
        root = pandoc.utils.stringify(meta.root)
        -- Ensure root ends with / if not empty
        if root ~= "" and root:sub(-1) ~= "/" then
            root = root .. "/"
        end
    end

    -- Adjust CSS paths in metadata
    if meta.css then
        if meta.css.t == "MetaList" then
            for i, v in ipairs(meta.css) do
                local path = pandoc.utils.stringify(v)
                if path:sub(1, 1) == "/" then
                    meta.css[i] = root .. path:sub(2)
                end
            end
        elseif meta.css.t == "MetaInlines" or meta.css.t == "MetaString" then
            local path = pandoc.utils.stringify(meta.css)
            if path:sub(1, 1) == "/" then
                meta.css = root .. path:sub(2)
            end
        end
    end

    -- Adjust scripts in metadata if present (Custom variable)
    if meta.scripts then
        if meta.scripts.t == "MetaList" then
            for i, v in ipairs(meta.scripts) do
                local path = pandoc.utils.stringify(v)
                if path:sub(1, 1) == "/" then
                    meta.scripts[i] = root .. path:sub(2)
                end
            end
        end
    end

    return meta
end

function Image(img)
    if img.src:sub(1, 1) == "/" then
        img.src = root .. img.src:sub(2)
    end
    return img
end

function Link(lnk)
    -- Only modify internal links (starting with /)
    if lnk.target:sub(1, 1) == "/" then
        lnk.target = root .. lnk.target:sub(2)
    end
    return lnk
end

function Script(el)
    if el.src and el.src:sub(1, 1) == "/" then
        el.src = root .. el.src:sub(2)
    end
    return el
end
