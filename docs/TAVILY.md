# Real-time grounding (Tavily)

Tavily gives the agent live, retrieved facts to reference during a call: current weather
and road conditions at an accident location, nearby 24h towing, and basic address checks.
The agent references a fact that is actually true, retrieved a few hundred milliseconds
before it speaks, instead of making one up.

## Lookup surfaces

[`tools/tavily_lookup.py`](../tools/tavily_lookup.py) exposes five primitives:

| Function | API call | Use case |
|---|---|---|
| `lookup_weather(location)` | `search` + `topic=news, time_range=day, country=germany, include_answer=advanced` | Current weather and road conditions at the scene |
| `lookup_traffic(location)` | same, different query | Live road closures or accidents in the last 24h |
| `lookup_towing(location)` | `search` + `country=germany` | Nearest 24h Abschleppdienst |
| `lookup_address(query)` | `search` + `country=germany` | Check an address resolves to a real place |
| `lookup_qa(question)` | `qna_search` | Direct one-line fact-check |

All five fall back to a stub when `TAVILY_API_KEY` is unset, so the demo runs offline.

## How it fires during a call

LLM-driven path (any provider with reliable function-calling): the primitives are
registered as `@function_tool` callables on `JamieAgent`. The model decides when to call
them from the transcript and the docstrings. See `build_agent()` in
[voice/livekit_agent.py](../voice/livekit_agent.py).

Heuristic path (small local models that mangle tool-call JSON): a keyword trigger fires
the lookups directly. Any mention of an Autobahn (A1 to A10) or a major German city queues
`lookup_weather` and `lookup_traffic` in parallel. See `_location_keywords()` and
`on_user_turn_completed`. Results fold into the next
`build_jamie_system_prompt(tool_results=...)`, so the model sees them on its next turn.

Either way the dashboard receives the same `tool_call` and `tool_result` events.

## Why topic=news, time_range=day, country=germany

Without these filters Tavily returns generic knowledge-graph hits that are stale or
irrelevant. The filters narrow the funnel:

- `topic="news"`: current reporting, not knowledge graphs.
- `time_range="day"`: only the last 24h, so the agent does not quote last week's weather
  as "this morning".
- `country="germany"`: geographic relevance for German locations.
- `include_answer="advanced"`: Tavily synthesises a one-paragraph answer across the top
  results, which is what the agent quotes. That is faster and more consistent than feeding
  it raw results to summarise.

When no fresh result exists, Tavily returns a "sources don't contain..." style answer
rather than inventing one. The system prompt tells the agent not to quote those and to
fall back to a generic acknowledgement.

## Composition with the rest of the stack

GLiNER extracts the location from the transcript, Tavily fires on that location, the
result folds into the next system prompt, and the bridge publishes `tool_call` and
`tool_result` events for the dashboard. The loop is invisible to the caller.
