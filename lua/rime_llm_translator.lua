-- Asynchronous Rime translation candidate filter for IBus + librime-lua.
-- Network I/O is deliberately handled by a separate Python user service.
local M = {}
local home = os.getenv("HOME") or ""
local cfg = home .. "/.config/rime-llm-translator/config.ini"
local spool = home .. "/.cache/rime-llm-translator"
local function read_config()
  local data, section = {}, ""
  local f = io.open(cfg, "r")
  if not f then return data end
  for line in f:lines() do
    local sec = line:match("^%s*%[([^%]]+)%]")
    if sec then section = sec end
    local k, v = line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
    if k then data[section .. "." .. k] = v end
  end
  f:close()
  return data
end
local function hex_encode(s)
  return (s:gsub(".", function(c) return string.format("%02x", string.byte(c)) end))
end
local function hex_decode(s)
  if #s % 2 ~= 0 or s:find("[^%da-fA-F]") then return nil end
  return (s:gsub("(%x%x)", function(h) return string.char(tonumber(h,16)) end))
end
local function request_id(s)
  local a, b = 5381, 0
  for i=1,#s do
    local byte = s:byte(i)
    a = (a * 33 + byte) % 4294967296
    b = (b * 65599 + byte) % 4294967296
  end
  return string.format("%08x%08x", a, b)
end
local function utf8_length(s)
  local _, n = s:gsub("[^\128-\193]", "")
  return n
end
local function languages(raw)
  local result = {}
  for entry in (raw or "en:English,ja:Japanese"):gmatch("[^,]+") do
    local code = entry:match("^%s*([a-z][a-z%-]*):")
    if code then result[#result+1] = code end
  end
  return result
end
local function load_results(id)
  local f = io.open(spool .. "/results/" .. id .. ".res", "r")
  if not f then return {} end
  local results = {}
  for line in f:lines() do
    local lang, encoded = line:match("^([a-z%-]+)%s+([%da-fA-F]+)$")
    if lang and encoded then results[lang] = hex_decode(encoded) end
  end
  f:close()
  return results
end
local function enqueue(id, text)
  local path = spool .. "/latest.req"
  local old = io.open(path, "r")
  if old then
    local current = old:read("*l")
    old:close()
    if current == id then return end
  end
  local tmp = spool .. "/latest." .. tostring(os.time()) .. "." .. id .. ".tmp"
  local f = io.open(tmp, "w")
  if not f then return end -- Service/setup unavailable: retain normal Chinese input.
  f:write(id .. "\n" .. hex_encode(text) .. "\n")
  f:close()
  os.rename(tmp, path)
end
function M.filter(input, env)
  local iterator = input:iter()
  local first = iterator()
  if not first then return end
  yield(first)
  local opts = read_config()
  local active = (opts["translation.enabled"] or "true"):lower() == "true"
  local raw_lang = opts["translation.languages"] or "en:English,ja:Japanese"
  local minimum = tonumber(opts["translation.min_characters"]) or 3
  local text = first.text or ""
  if active and utf8_length(text) >= minimum and #text <= 600
    and text:match("[\228-\233][\128-\191][\128-\191]") then
    local identity = text .. "|" .. raw_lang .. "|" ..
      (opts["provider.model"] or "") .. "|" .. (opts["provider.base_url"] or "")
    local id = request_id(identity)
    local translated = load_results(id)
    local missing = false
    for _,lang in ipairs(languages(raw_lang)) do
      local value = translated[lang]
      if value and #value > 0 and value ~= text then
        yield(Candidate("llm_" .. lang, first.start, first._end,
              value, " 🌐 " .. lang:upper()))
      else
        missing = true
      end
    end
    if missing then enqueue(id, text) end
  end
  while true do
    local candidate = iterator()
    if not candidate then break end
    yield(candidate)
  end
end
return M.filter
