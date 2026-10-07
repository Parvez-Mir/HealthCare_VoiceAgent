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
