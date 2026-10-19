-- Only the configured shortcut dispatches a cloud AI request.
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
    (o["provider.model"] or "").."|"..(o["provider.base_url"] or "").."|"..
    (o["translation.source_language"] or "auto").."|"..
    (o["translation.offline_revision"] or "bergamot-v1")
  local a,b=5381,0
  for i=1,#s do
    local n=s:byte(i)
    a=(a*33+n)%4294967296
    b=(b*65599+n)%4294967296
  end
  return string.format("%08x%08x",a,b)
end
local function dispatch(env,o)
  local ctx=env.engine.context
  if not ctx:is_composing() or not ctx:has_menu() then return false end
  local candidate=ctx:get_selected_candidate()
  if not candidate or not candidate.text or candidate.text=="" then return false end
  if candidate.type and tostring(candidate.type):match("^llm_") then
    return false
  end
  local text=candidate.text
  if #text > 1200 then return false end
  if (o["translation.enabled"] or "false"):lower() ~= "true" then return false end
  local langs=o["translation.languages"] or "en:English,ja:Japanese"
  local id=id_for(text,langs,o)
  ctx:set_property("rime_llm_source_input", ctx.input)
  ctx:set_property("rime_llm_source", text)
  ctx:set_property("rime_llm_id", id)
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

local function double_alt(key,env,o)
  local ctx=env.engine.context
  local now=tonumber(ctx:get_property("rime_llm_key_time_ms")) or 0
  local epoch=ctx:get_property("rime_llm_key_epoch")
  local candidate=ctx:get_selected_candidate()
  local is_alt=key.keycode==0xffe9 or key.keycode==0xffea
  if not is_alt or key:ctrl() or key:shift() or key:super() or now<=0
      or not ctx:is_composing() or not ctx:has_menu() or not candidate
      or tostring(candidate.type):match("^llm_")
      or (o["translation.enabled"] or "false"):lower()~="true" then
    env.alt_tap=nil
    return nil
  end
  local state=env.alt_tap
  if not state or state.epoch~=epoch or state.input~=ctx.input or state.text~=candidate.text then
    state={epoch=epoch,input=ctx.input,text=candidate.text}
    env.alt_tap=state
  end
  if key:release() then
    if state.invalid or state.down~=key.keycode or now-state.down_at>400 then
      env.alt_tap=nil
      return nil,true
    end
    state.down=nil
    if state.first and state.key==key.keycode and now-state.first<=400 then
      env.alt_tap=nil
      return o
    end
    state.first=now
    state.key=key.keycode
  else
    if state.down then
      -- Autorepeat/holding Alt is not a second tap.
      state.invalid=true
      return nil,true
    end
    if state.first and (now-state.first>400 or state.key~=key.keycode) then state.first=nil end
    state.down=key.keycode
    state.down_at=now
  end
  -- Reserve pure Alt only while composing; Alt+other-key still passes through.
  return nil,true
end

local function matching_config(key,env)
  local o=config()
  if o["translation.ai_hotkey"]=="DoubleAlt" then return double_alt(key,env,o) end
  env.alt_tap=nil
  if key:release() then return nil end
  local shortcut=KeyEvent(o["translation.ai_hotkey"] or "Control+Shift+Return")
  -- Require an explicit modifier, never intercept ordinary Chinese typing.
  if not (shortcut:ctrl() or shortcut:alt() or shortcut:super()) then return nil end
  local function letter(code)
    if code >= 65 and code <= 90 then return code+32 end
    return code
  end
  if letter(key.keycode) ~= letter(shortcut.keycode) then return nil end
  if key:ctrl() ~= shortcut:ctrl() or key:shift() ~= shortcut:shift()
      or key:alt() ~= shortcut:alt() or key:super() ~= shortcut:super() then return nil end
  return o
end

return function(key, env)
  if not key then return 2 end
  -- Private in-process refresh from our IBus frontend's GLib main loop.
  -- No OS key is injected, and no translation request is generated here.
  if key.keycode == 0xffffff then
    pcall(function()
      local ctx=env.engine.context
      if ctx:is_composing() then ctx:refresh_non_confirmed_composition() end
    end)
    return 1
  end
  if not (key:ctrl() or key:alt() or key:super() or key.keycode==0xffe9 or key.keycode==0xffea) then
    env.alt_tap=nil
    return 2
  end
  -- Invalid config or an unreadable file must never swallow input or dispatch AI.
  local matched,o,pending=pcall(matching_config,key,env)
  if not matched then env.alt_tap=nil; return 2 end
  if not o then return pending and 1 or 2 end
  if os.getenv("RIME_LLM_TEST_DIAGNOSTICS") == "1" then
    io.stderr:write("Rime AI hotkey matched; dispatching\n")
  end
  local ok, consumed=pcall(dispatch,env,o)
  if os.getenv("RIME_LLM_TEST_DIAGNOSTICS") == "1" then
    io.stderr:write("Rime AI hotkey result: "..tostring(ok)..", "..tostring(consumed).."\n")
  end
  if ok and consumed then return 1 end
  return 2
end
