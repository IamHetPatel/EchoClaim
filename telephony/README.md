# Telephony bridge — Twilio SIP → LiveKit room → agent

An inbound phone number is wired into a LiveKit room that the agent worker listens on.

## Credentials → `.env`

Scoped API-Key credentials (preferred over a master Auth Token) map as:

| Credential | `.env` variable |
| --- | --- |
| `AccountSID` | `TWILIO_ACCOUNT_SID` |
| `APIKeySID` | `TWILIO_API_KEY_SID` |
| `APIKeySecret` | `TWILIO_API_KEY_SECRET` |
| phone number | `TWILIO_PHONE_NUMBER` |

Leave `TWILIO_AUTH_TOKEN` empty — `telephony/twilio_client.py` auto-detects API-Key mode
when `TWILIO_API_KEY_SID` is set. With a master-credential account instead, fill
`TWILIO_ACCOUNT_SID` + `TWILIO_AUTH_TOKEN` and leave the API-Key fields empty.

### Verify the credentials

```bash
python telephony/twilio_client.py
```

Fetches the account and lists phone numbers:

```
  Twilio: API-Key mode (scoped credential)
  ✓ authenticated as account '<account name>', status=active
  ✓ 1 phone number(s) on this account:
      +49xxxxxxxxxxx  →  voice URL: (none set)
```

`✗ HTTP 401` means the API-Key SID/Secret pair doesn't match the AccountSID.

## Wiring the number → LiveKit room

### Path A — provider-provisioned SIP (preferred)

1. Set `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` in `.env`. If you have an
   explicit SIP endpoint (e.g. `sip:<id>.sip.livekit.cloud`), set `LIVEKIT_SIP_URI` too.
2. Configure the SIP trunk in the LiveKit dashboard with that URI.
3. Run `python voice/livekit_agent.py`.
4. Place an inbound test call.

### Path B — Twilio Elastic SIP Trunk

1. Twilio Console → Elastic SIP Trunking → create a trunk.
2. Origination URI: `sip:<your-livekit-sip-uri>` from the LiveKit project page.
3. Add the number under the trunk's "Numbers" tab.
4. Run `python voice/livekit_agent.py` and call the number.

## Latency budget (target < 740ms total)

| Step | Budget |
| --- | --- |
| STT (Gradium / Whisper) | < 120ms |
| Gemini 2.5 Flash first token | < 220ms |
| Gradium TTS first audio (TTFT) | < 300ms |
| Network + jitter | < 100ms |

Any remaining gap is masked with filler audio (`fillers/manifest.json`): the moment a tool
call is dispatched, a short "let me just pull up the map…" clip plays, keeping perceived
latency below the ~500ms threshold.

## Multiplexing

A single WebSocket carries multiple `client_req_id` concurrent TTS streams — see
`voice/multiplex_demo.py`. This is the path for concurrent calls at production scale.

## Running without Twilio Console access

If you have API credentials but not dashboard login, the demo still works.

```bash
python telephony/setup_sip.py list   # LiveKit trunk + rule + SIP URI
python telephony/twilio_client.py    # Twilio credential check
```

The LiveKit side is wired; the only missing hop is Twilio → LiveKit's SIP URI. Three ways
to demo without it:

### Path 1 — Local laptop (zero infra)

```bash
python voice/livekit_agent.py console
```

Uses the machine's mic + speakers via `sounddevice`. Same agent code and bridge events as
production, without a LiveKit room or telephony.

### Path 2 — Browser caller via LiveKit Agents Playground

1. `python voice/livekit_agent.py start`
2. Open https://agents-playground.livekit.io
3. "Connect to a custom server" → URL `wss://<your-project>.livekit.cloud`, plus API Key
   and Secret from `.env`.
4. Connect → the worker auto-dispatches → talk to the agent in the browser.

Exercises the LiveKit project end to end and stands in for a phone caller.

### Path 3 — Programmatic Twilio config

```bash
python telephony/configure_twilio.py status   # current config
TWIML_URL=https://your-host/twiml.xml \
  python telephony/configure_twilio.py apply   # point the number at LiveKit
python telephony/configure_twilio.py revert    # undo
```

`apply` needs a public URL serving the TwiML payload the script prints (e.g.
`python -m http.server 5000` + a tunnel, a Cloudflare Worker, or a TwiML Bin).
