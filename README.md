# HealthCare Voice Agent

Healthcare voice agent with a FastAPI backend and LiveKit-based voice
integration. Backend-specific code and dependencies live in
[`backend/`](./backend/).

## Initial setup

The project uses Python, FastAPI for the booking backend, and LiveKit Agents with
Gemini and Silero plugins for the voice agent.

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Install Ollama and pull the local model before running the voice agent:

```bash
ollama pull qwen2.5:7b
```

Fill in `OLLAMA_MODEL`, `OLLAMA_BASE_URL`, `ASSEMBLYAI_API_KEY`,
`CARTESIA_API_KEY`, `PATIENT_ID`, and the LiveKit credentials in `backend/.env`
before running the voice agent. The LLM now runs locally through Ollama; STT
and TTS still use AssemblyAI and Cartesia.
check Google's current pricing and rate limits before production use. Do not
commit `.env`.

## Booking backend

Start the backend from the `backend/` directory:

```bash
cd backend
.venv/bin/python -m uvicorn app:app --reload
```

The booking API provides:

- `GET /health` — backend health check
- `GET /slots` — available fake consultation slots
- `POST /appointments` — books a slot for a dummy patient

Example booking request:

```bash
curl -X POST http://127.0.0.1:8000/appointments \
  -H 'Content-Type: application/json' \
  -d '{"patient_id":"patient-001","slot_id":"slot-001"}'
```

## Console voice agent

With the booking backend running in one terminal, start the LiveKit room agent
from another terminal:

```bash
cd backend
.venv/bin/python voice_agent.py console
```

The agent reads the patient selected by `PATIENT_ID` from `patients.json`. Set
`BACKEND_URL` in `backend/.env` only when the booking backend is running at a
different URL. LiveKit BVC noise cancellation is enabled for microphone input.

## Outbound calls (LiveKit Telephony)

One-time setup in the LiveKit Cloud dashboard:

1. LiveKit-purchased numbers currently support inbound calls only, so outbound
   calls need a SIP carrier (for example Twilio or Telnyx). In the carrier's
   console, create an outbound SIP trunk and buy or verify a number.
2. In the LiveKit dashboard under Telephony, create an **outbound SIP trunk**
   using the carrier's SIP hostname (no `sip:` prefix), transport, credentials,
   and the carrier number as the caller ID. Copy its trunk ID (`ST_...`).
3. Set `SIP_OUTBOUND_TRUNK_ID` in `backend/.env`, along with `LIVEKIT_URL`,
   `LIVEKIT_API_KEY`, and `LIVEKIT_API_SECRET`.

The LLM is not configured in LiveKit. The agent worker runs on your machine and
calls Ollama directly, so Ollama must be running locally.

Run each in its own terminal from `backend/`:

```bash
.venv/bin/python -m uvicorn app:app --reload   # booking backend
.venv/bin/python voice_agent.py dev            # agent worker
.venv/bin/python make_call.py patient-001 +14155550123
```

`make_call.py` takes a patient ID and the test phone number (E.164) and places
exactly one call; there is no retry or batch dialing. The worker dials the
number, waits for it to be answered, and starts the conversation. Dial failures
(including the SIP status code) are logged in the worker terminal.

Only call phones whose owners know it is a test. Keep `patients.json` to dummy
data; do not commit real phone numbers. Use the patient's `phone` only as a
placeholder; the destination is whatever you pass to `make_call.py`.

If you see `CERTIFICATE_VERIFY_FAILED` with python.org Python on macOS, run
`export SSL_CERT_FILE=$(.venv/bin/python -c "import certifi;print(certifi.where())")`
in each terminal (or run the "Install Certificates.command" that ships with
Python).

## Call data

Each call (console or outbound) is saved to its own git-ignored folder,
`backend/calls/<room-name>/`:

- `audio.ogg`: stereo Opus recording, caller on the left channel and agent on
  the right.
- `call.json`: call metadata and variables (patient, phone number, biomarkers,
  start/end time), the live transcript, every tool call with its arguments and
  result, and the recording path.

The transcript is captured during the call from the agent's own speech-to-text
and replies, so no second transcription is needed. Later phases add
`analysis.json` to the same folder. The worker logs `Capturing call to …` at
the start and `Saved call data to …` at the end. Calls contain health
conversations, so use dummy patients and test callers only. A capture failure
is logged and never interrupts the call.
