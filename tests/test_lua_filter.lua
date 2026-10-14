-- Fail-open regression: upstream Chinese candidates must always be emitted,
-- even if the config, filesystem, or Candidate constructor fails.
local filter = dofile("lua/rime_llm_translator.lua")

local function run(input_items)
  local emitted = {}
  _G.yield = function(cand) emitted[#emitted+1] = cand end
  local state = {index=0}
  function state:iter()
    return function(s)
      assert(s == self, "Rime iterator lost state")
      s.index=s.index+1
      return input_items[s.index]
    end, self
  end
  filter(state,{})
  assert(#emitted == #input_items, "unexpected number of candidate(s)")
  for i,c in ipairs(input_items) do
    assert(c == emitted[i], "original candidate missing or reordered")
  end
end

local inputs={{text="你好",start=0,_end=5},{text="您好",start=0,_end=5}}
run(inputs)
run({})
-- Simulate privacy/service failure: config file can't be read.
local original_io_open = io.open
io.open = function(...) error("simulated read error") end
run(inputs)
io.open = original_io_open
-- Simulate missing HOME, a common daemon/test environment issue.
local original_getenv = os.getenv
os.getenv = function(name) if name == "HOME" then return nil end return original_getenv(name) end
run(inputs)
os.getenv = original_getenv
print("PASS: no AI failure can swallow regular Chinese candidate results")
