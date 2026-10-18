-- Rime offline-first MT + opt-in AI corrections.
-- Every Rime candidate is yielded unchanged before any optional enrichment.
-- Python worker performs translation out-of-process. No API calls in Lua.

local home = os.getenv("HOME") or ""
local config_file = home .. "/.config/rime-llm-translator/config.ini"
local cache_dir = home .. "/.cache/rime-llm-translator"

local function config()
  local result, section = {}, ""
  local f = io.open(config_file, "r")
  if not f then return result end
  for line in f:lines() do
    local s = line:match("^%s*%[([^%]]+)%]")
    if s then section = s end
    local k,v = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
    if k then result[section .. "." .. k] = v end
  end
  f:close()
  return result
end

local function encode(text)
  return (text:gsub(".", function(c) return string.format("%02x", c:byte()) end))
end

local function decode(hex)
  if #hex % 2 ~= 0 or hex:find("[^%x]") then return nil end
  return (hex:gsub("%x%x", function(p) return string.char(tonumber(p,16)) end))
end

local function identifier(text, langs, opts)
  local data = text .. "|" .. langs .. "|" ..
      (opts["provider.model"] or "") .. "|" ..
      (opts["provider.base_url"] or "") .. "|" ..
      (opts["translation.source_language"] or "auto")
  local a,b = 5381,0
  for i=1,#data do
    local n = data:byte(i)
    a=(a*33+n)%4294967296
    b=(b*65599+n)%4294967296
  end
  return string.format("%08x%08x",a,b)
end

local function translations(path)
  local found = {}
  local f = io.open(path,"r")
  if not f then return found end
  for line in f:lines() do
    local lang, value = line:match("^([a-z%-]+)%s+([%da-fA-F]+)$")
    if lang and value then found[lang] = decode(value) end
  end
  f:close()
  return found
end

local function request(filename, id, text)
  local file = cache_dir .. "/" .. filename
  local old = io.open(file,"r")
  if old then
    local last = old:read("*l")
    old:close()
    if last == id then return end
  end
  local tmp = cache_dir .. "/" .. filename .. "." .. id .. ".tmp"
  local f = io.open(tmp,"w")
  if not f then return end
  f:write(id .. "\n" .. encode(text) .. "\n")
  f:close()
  os.rename(tmp, file)
end

local function current_source(first, env)
  if env and env.engine and env.engine.context then
    local ctx = env.engine.context
    if ctx:get_property("rime_llm_source_input") == ctx.input then
      local text = ctx:get_property("rime_llm_source")
      if text ~= "" then
        return {text=text, start=first.start, _end=first._end}
      end
    end
  end
  return first
end

local function enrich(first, env)
  if not home or home == "" then return end
  local opts = config()
  if (opts["translation.enabled"] or "false"):lower() ~= "true" then return end
  local source = current_source(first,env)
  local text = source.text or ""
  local _,len = text:gsub("[^\128-\193]","")
  local threshold = tonumber(opts["translation.min_characters"]) or 1
  if len < threshold or #text > 1200 or
      not text:match("[\228-\233][\128-\191][\128-\191]") then
    return
  end
  local langs = opts["translation.languages"] or "en:English,ja:Japanese"
  local id = identifier(text,langs,opts)
  if env and env.engine and env.engine.context then
    env.engine.context:set_property("rime_llm_id", id)
  end
  local mt = translations(cache_dir .. "/results-mt/" .. id .. ".res")
  local ai = translations(cache_dir .. "/results-ai/" .. id .. ".res")
  local missing_mt = false
  for entry in langs:gmatch("[^,]+") do
    local lang = entry:match("^%s*([a-z][a-z%-]*):")
    if lang then
      -- AI is shown only if the user explicitly requested it. An existing AI
      -- correction supersedes its offline machine translation for this source.
      local value = ai[lang] or mt[lang]
      local origin = ai[lang] and "AI" or "MT"
      if value and value ~= "" and value ~= text then
        local comment = origin == "AI" and " ✦ AI · " or " 🌐 MT · "
        local ok, candidate = pcall(Candidate,
          "llm_" .. origin:lower() .. "_" .. lang,
          source.start, source._end,
          value, comment .. lang:upper())
        if ok and candidate then yield(candidate) end
      else
        missing_mt=true
      end
    end
  end
  if missing_mt and (opts["translation.offline_enabled"] or "true"):lower() == "true" then
    request("latest.req", id, text)
  end
end

return function(input, env)
  local first = true
  for candidate in input:iter() do
    yield(candidate) -- Native Chinese candidates must never depend on translation.
    if first then
      first = false
      pcall(enrich,candidate,env)
    end
  end
end
