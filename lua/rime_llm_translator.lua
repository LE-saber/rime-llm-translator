-- Fail-open asynchronous multilingual candidate filter (IBus / librime-lua).
-- Crucial invariant: every upstream Rime candidate must be yielded unchanged.
-- No network activity. Translation cache failures must never interrupt typing.

local function hex(s)
  return (s:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

local function unhex(s)
  if #s % 2 ~= 0 or s:find("[^%x]") then return nil end
  return (s:gsub("%x%x", function(pair) return string.char(tonumber(pair, 16)) end))
end

local function id_for(s)
  local a, b = 5381, 0
  for i=1,#s do
    local n = s:byte(i)
    a = (a * 33 + n) % 4294967296
    b = (b * 65599 + n) % 4294967296
  end
  return string.format("%08x%08x", a, b)
end

local function config_at(path)
  local result, section = {}, ""
  local f = io.open(path, "r")
  if not f then return result end
  for line in f:lines() do
    local new_section = line:match("^%s*%[([^%]]+)%]")
    if new_section then section = new_section end
    local key, value = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
    if key then result[section .. "." .. key] = value end
  end
  f:close()
  return result
end

local function read_results(path)
  local results = {}
  local f = io.open(path, "r")
  if not f then return results end
  for line in f:lines() do
    local code, encoded = line:match("^([a-z%-]+)%s+([%da-fA-F]+)$")
    if code and encoded then results[code] = unhex(encoded) end
  end
  f:close()
  return results
end

local function queue_request(spool, id, text)
  local target = spool .. "/latest.req"
  local old = io.open(target, "r")
  if old then
    local previous = old:read("*l")
    old:close()
    if previous == id then return end
  end
  local temp = spool .. "/latest." .. id .. ".tmp"
  local f = io.open(temp, "w")
  if not f then return end -- Service not installed: normal input continues.
  f:write(id .. "\n" .. hex(text) .. "\n")
  f:close()
  os.rename(temp, target)
end

local function enrich(first)
  local home = os.getenv("HOME")
  if not home or home == "" then return {} end
  local cfg = config_at(home .. "/.config/rime-llm-translator/config.ini")
  if (cfg["translation.enabled"] or "false"):lower() ~= "true" then
    return {}
  end
  local text = first.text or ""
  local _, length = text:gsub("[^\128-\193]", "")
  local minimum = tonumber(cfg["translation.min_characters"]) or 3
  if length < minimum or #text > 600 or
      not text:match("[\228-\233][\128-\191][\128-\191]") then
    return {}
  end
  local languages = cfg["translation.languages"] or "en:English,ja:Japanese"
  local identity = text .. "|" .. languages .. "|" ..
    (cfg["provider.model"] or "") .. "|" .. (cfg["provider.base_url"] or "")
  local id = id_for(identity)
  local spool = home .. "/.cache/rime-llm-translator"
  local results = read_results(spool .. "/results/" .. id .. ".res")
  local found, incomplete = {}, false
  for entry in languages:gmatch("[^,]+") do
    local code = entry:match("^%s*([a-z][a-z%-]*):")
    if code then
      local translation = results[code]
      if translation and translation ~= "" and translation ~= text then
        found[#found+1] = { code=code, text=translation }
      else
        incomplete = true
      end
    end
  end
  if incomplete then queue_request(spool, id, text) end
  return found
end

local function safe_enrichment(first)
  local ok, translated = pcall(enrich, first)
  if not ok or type(translated) ~= "table" then return end
  for _, item in ipairs(translated) do
    -- Candidate construction can also fail on older librime versions.
    local built, candidate = pcall(Candidate, "llm_" .. item.code,
       first.start, first._end, item.text, " 🌐 " .. item.code:upper())
    if built and candidate then yield(candidate) end
  end
end

-- Prefer the idiomatic Rime iterator protocol; do not call iter() without state.
return function(input, env)
  local is_first = true
  for candidate in input:iter() do
    -- Yield original candidate BEFORE doing anything that can fail.
    yield(candidate)
    if is_first then
      is_first = false
      -- AI-related failures cannot stop subsequent upstream candidates.
      safe_enrichment(candidate)
    end
  end
end
