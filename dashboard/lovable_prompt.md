# Dashboard specification

The dashboard contract. The single-file `index.html` in this folder implements it; this
spec is also the regeneration prompt for rebuilding the UI from scratch.

> Build a React dashboard for a real-time German motor-insurance FNOL (first-notice-of-loss)
> intake console, named **VORSICHT Claims · Live FNOL Console**.
>
> Connection: connects to a WebSocket at `ws://localhost:8765/ws` and receives JSON
> events. Each event has `type` and `ts`. The event types are:
> - `{type:"transcript", speaker:"jamie"|"caller", text:string}`
> - `{type:"entity", label:string, value:string, confidence:number}`
> - `{type:"fraud_signal", signal:string, severity:"low"|"medium"|"high", evidence:string}`
> - `{type:"emotional_state", state:"calm"|"distressed"|"noisy"}`
> - `{type:"tool_call", name:string, args:object}` and `{type:"tool_result", name:string, result:object}`
> - `{type:"call_start", crm:object}` and `{type:"call_end", claim_json:object}`
>
> Layout (3 columns × 2–3 rows, 14px gutter, full viewport, dark UI):
>
> 1. **Left (~40%)**: a large Live Transcript panel (caller bubbles left, agent bubbles
>    right with a subtle teal tint, auto-scroll), with a Tool Calls log below it.
> 2. **Middle (~30%)**: a Claim Pillars panel — a 15-item checklist that ticks off as
>    `entity` events arrive (injuries, accident_datetime, accident_location, road_type,
>    weather_conditions, how_it_happened, vehicle_drivable, other_party_involved,
>    other_party_plate, other_party_insurer, police_involved, police_case_number,
>    witnesses, fault_admission, settlement_preference). Below it, a Fraud Signals panel
>    with a 0–10 risk gauge (sum of severities: low=1, medium=2, high=4, capped at 10) and
>    a list of flagged signals.
> 3. **Right (~30%)**: an Emotional Mode panel (one large tinted word:
>    CALM/DISTRESSED/NOISY in green/red/amber), a Known Context panel (read-only JSON
>    viewer of the CRM from `call_start`), and a Final Claim JSON panel with a Copy button
>    (shown only after `call_end`).
>
> Header: "VORSICHT Claims · Live FNOL Console" with three pills on the right —
> connection status, "pillars X/15", "fraud risk N/10".
>
> Style: dark navy (`#0b1220` bg, `#111a2e` panels, `#1f2a44` borders, `#d6dee9` ink,
> `#5fb4ff` accent, `#4ade80` good, `#fbbf24` warn, `#f87171` bad). Inter font, 12px panel
> radius — an enterprise insurance-software look.
>
> Persist nothing in localStorage; all state lives in React.
