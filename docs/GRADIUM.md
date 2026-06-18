# Gradium integration

Gradium provides the STT and TTS for the voice loop. This project integrates it at three
tiers and tunes several less-obvious parameters that matter for naturalness in a
phone-call setting.

## Integration tiers

| Tier | Where | Purpose |
|---|---|---|
| Gradbot (zero-config) | [voice/gradbot_quickstart.py](../voice/gradbot_quickstart.py) | Minimal voice loop for quick local iteration |
| Direct SDK (`GradiumClient`) | [voice/multiplex_demo.py](../voice/multiplex_demo.py) | Raw WebSocket; multiple concurrent TTS streams over one connection |
| `livekit-plugins-gradium` | [voice/livekit_agent.py](../voice/livekit_agent.py) | Production stack: Gradium STT + TTS inside `AgentSession` with Silero VAD |

The direct-SDK tier multiplexes concurrent callers over a single WebSocket: each gets a
unique `client_req_id` with `close_ws_on_eos=False`.

## Voice cloning

[scripts/clone_voice.py](../scripts/clone_voice.py) wraps
`client.voice_create(audio_file=Path, name=..., start_s=...)`, turning a ~10-second clean
sample into a new `voice_id`:

```bash
python scripts/clone_voice.py jamie_sample.wav
# copy the printed voice_id into .env as GRADIUM_VOICE_ID, restart
```

## Custom pronunciation dictionary

Insurance and German domain terms (FNOL, DSGVO, IBAN, Vollkasko, HUK-Coburg) are
mispronounced by default TTS. Gradium exposes a `/api/pronunciations/` endpoint that is
not surfaced in the SDK; it is used directly:

```python
POST https://eu.api.gradium.ai/api/pronunciations/
{
  "name": "jamie-fnol",
  "language": "en",
  "rules": [
    {"original": "FNOL", "rewrite": "eff-noll"},
    {"original": "DSGVO", "rewrite": "Day-Es-Gay-Fau-Oh"},
    {"original": "Vollkasko", "rewrite": "Foll-kass-ko"}
    // 26 rules total
  ]
}
```

The returned `uid` is passed to `gradium.TTS(pronunciation_id=uid)`. The full 26-rule
dictionary (insurance acronyms, German Kasko terms, insurer names, Autobahn names, common
cities) is in [scripts/setup_pronunciations.py](../scripts/setup_pronunciations.py).
Rerunning the script replaces the existing `jamie-fnol` dictionary, so iterating is one
command.

## Tone tuning via `json_config`

```python
tts_kwargs["json_config"] = {
    "temp": 0.85,          # natural variation (0.7 default sounds flatter)
    "padding_bonus": 0.3,  # slightly slower, more deliberate pace
    "cfg_coef": 2.2,       # voice consistency turn-to-turn
    "rewrite_rules": "en", # English number/date pronunciation
}
```

All four are env-overridable (`GRADIUM_TEMP`, `GRADIUM_PADDING`, `GRADIUM_CFG`,
`GRADIUM_LANGUAGE`), so they can be tuned without a redeploy.

## STT noise robustness

Default STT speculatively produces words from ambient noise (phantom transcripts such as
"Marama", "Englishman"). Setting `gradium.STT(temperature=0.0)` forces conservative
transcription and largely eliminates these, which is what makes the highway-background
case usable.
