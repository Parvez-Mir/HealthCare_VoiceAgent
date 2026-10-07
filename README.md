# HealthCare Voice Agent

This project is being built incrementally according to the Phase 1 specification.
Backend-specific code and dependencies live in [`backend/`](./backend/).

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

Fill in `GOOGLE_API_KEY` and the LiveKit credentials in `backend/.env` before
running the voice agent. Gemini API access is quota-limited on its free tier;
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
