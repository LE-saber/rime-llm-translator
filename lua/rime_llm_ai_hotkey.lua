-- Only Control+Shift+Return dispatches a DeepSeek request.
-- A nonmatching key is never consumed. The active candidate is not committed.
local home = os.getenv("HOME") or ""
local function config()
  local o, section={}, ""
  local f=io.open(home.."/.config/rime-llm-translator/config.ini","r")
  if not f then return o end
  for line in f:lines() do
    local s=line:match("^%s*%[([^%]]+)%]")
    if s then section=s end
    local k,v=line:match("^%s*([%w_]+)%s*=%s*(.-)%s*$")
    if k then o[section.."."..k]=v end
  end
  f:close()
  return o
end
local function id_for(text,langs,o)
  local s=text.."|"..langs.."|"..
    (o["provider.model"] or "").."|"..(o["provider.base_url"] or "")
  local a,b=5381,0
  for i=1,#s do
    local n=s:byte(i)
    a=(a*33+n)%4294967296
    b=(b*65599+n)%4294967296
  end
  return string.format("%08x%08x",a,b)
end
local function dispatch(env)
  local ctx=env.engine.context
  if not ctx:is_composing() or not ctx:has_menu() then return false end
  local candidate=ctx:get_selected_candidate()
  if not candidate or not candidate.text or candidate.text=="" then return false end
  if candidate.type and tostring(candidate.type):match("^llm_") then
    return false
  end
  local text=candidate.text
  if #text > 1200 then return false end
  local o=config()
  if (o["translation.enabled"] or "false"):lower() ~= "true" then return false end
  local langs=o["translation.languages"] or "en:English,ja:Japanese"
  local id=id_for(text,langs,o)
  local folder=home.."/.cache/rime-llm-translator"
  local target=folder.."/ai.req"
  -- Reuse the result if the same text was already corrected.
  local already=io.open(folder.."/results-ai/"..id..".res","r")
  if already then
    already:close()
    ctx:refresh_non_confirmed_composition()
    return true
  end
  local tmp=folder.."/ai."..id..".tmp"
  local f=io.open(tmp,"w")
  if not f then return false end
  f:write(id.."\n"..(text:gsub(".",function(c) return string.format("%02x",c:byte()) end)).."\n")
  f:close()
  local ok=os.rename(tmp,target)
  return ok and true or false
end

return function(key, env)
  if not key then return 2 end
  -- Test modifiers independently; Rime may render Control+Shift or Shift+Control.
  if not (key:ctrl() and key:shift() and not key:release()
      and key.keycode == 0xff0d) then return 2 end
  if os.getenv("RIME_LLM_TEST_DIAGNOSTICS") == "1" then
    io.stderr:write("Rime AI hotkey matched; dispatching\n")
  end
  local ok, consumed=pcall(dispatch,env)
  if os.getenv("RIME_LLM_TEST_DIAGNOSTICS") == "1" then
    io.stderr:write("Rime AI hotkey result: "..tostring(ok)..", "..tostring(consumed).."\n")
  end
  if ok and consumed then return 1 end
  return 2
end
