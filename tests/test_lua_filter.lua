-- Regression: Rime's input:iter() returns a function AND a state object.
-- Missing state caused an empty candidate menu although preedit was visible.
local filter = dofile("lua/rime_llm_translator.lua")

local function run(input_items)
  local emitted = {}
  _G.yield = function(cand) emitted[#emitted + 1] = cand end
  local state = { index = 0 }
  function state:iter()
    return function(s)
      assert(s == self, "Rime iterator lost its translation state")
      s.index = s.index + 1
      return input_items[s.index]
    end, self
  end
  filter(state, {})
  assert(#emitted == #input_items, "original Rime candidates must be preserved")
  for i, candidate in ipairs(input_items) do
    assert(emitted[i] == candidate, "candidate ordering / identity changed")
  end
end

run({{text="你好",start=0,_end=5}, {text="您好",start=0,_end=5}})
run({{text="你好世界",start=0,_end=10}, {text="你好",start=0,_end=5}})
run({})
print("PASS: Lua filter retains iterator state and Chinese candidates")
