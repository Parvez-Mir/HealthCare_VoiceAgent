# Phase 1: Talk to the agent from your terminal

**Outcome:** you start a FastAPI backend, run one command with a dummy patient, and have a spoken conversation with the agent in your terminal. It explains the patient's biomarkers and books a (fake) appointment.

## What to build

1. **Project setup**: Python env, dependencies (`livekit-agents`, plugins for your STT/LLM/TTS and VAD, `fastapi`, `uvicorn`), `.env` and `.env.example`.
2. **Dummy patient data**: a local `patients.json` file with a few patients (id, name, phone, biomarkers like glucose and HbA1c). The agent reads it directly; no API call for patient data.
3. **FastAPI backend** (booking only):
   - `GET /slots` returns a few fake appointment slots.
   - `POST /appointments` "books" a slot and returns a confirmation ID.
4. **Voice agent** using the LiveKit Agents SDK:
   - A system prompt built from the patient's entry in `patients.json`.
   - Two function tools, `check_available_slots` and `book_appointment`, which call the FastAPI endpoints.
   - A conversation flow: greet, confirm identity, explain biomarkers, offer a consultation, book, close.
5. **Terminal run**: LiveKit's `console` mode runs the agent locally and uses your mic and speakers, so you talk to it right in the terminal. The command takes a patient ID, and the agent loads that patient from `patients.json`.

## Done when

- [x] `uvicorn` starts the backend and both endpoints work.
- [X] One command starts the agent in console mode for a given patient ID from `patients.json`.
- [X] The agent greets the patient by name and reads out the correct biomarker values.
- [X] You can say "yes, book me in", and the agent calls the booking tool and confirms the slot.
- [X] If you decline, the agent ends politely without booking.
- [X] You can see the tool calls and results in the terminal logs.

## Out of scope for Phase 1

- SIP and real phone calls
- Recording
- Post-call analysis
- Opik (tracing and evaluation)
- Serving patient data through the API (can be added later, e.g., alongside a `POST /calls` endpoint in Phase 2)

## Design choice

Patient data comes from a local JSON file, and FastAPI handles only the booking side. This keeps Phase 1 simple while still giving you a real backend to extend later.

## Progress tracking

### Current phase

**Phase 1 — Complete.** Work continues in [phase2.md](./phase2.md).

### Completed

- Selected Gemini as the initial provider for the STT/LLM/TTS integration.
- Added the Python dependency list for FastAPI, Uvicorn, LiveKit Agents, the Google/Gemini plugin, the Silero VAD plugin, and environment loading.
- Added `.env.example` with placeholders for Gemini and LiveKit credentials.
- Added `.gitignore` to keep virtual-environment files, local environment secrets, and Python artifacts out of version control.
- Added initial setup instructions to the project README.
- Created `.venv`, installed the declared dependencies successfully, and verified the key package imports.
- Moved backend dependencies and environment configuration into `backend/` so the repository can add a frontend independently.
- Added three dummy patient records to `backend/patients.json`.
- Added fake appointment slots to `backend/slots.json` and load them from the file at backend startup.
- Added the FastAPI booking service with `GET /slots`, `POST /appointments`, and `GET /health`.
- Added the Gemini Live console agent with patient-specific instructions and booking tools.
- Simplified the agent around LiveKit's standard `AgentServer` and `@server.rtc_session()` room-worker pattern, with AssemblyAI STT, Gemini LLM, Cartesia TTS, and Silero VAD components.
- Reduced Gemini failure impact with short responses and one bounded LLM retry using Gemini's minimum ten-second request deadline.
- Replaced the remote Gemini LLM with a local Ollama model through LiveKit's OpenAI-compatible plugin.
- Disabled preemptive generation and assistant barge-in so spoken responses finish before the next turn.
- Added LiveKit BVC noise cancellation to the room microphone input.
- Configured VAD-based barge-in with a 150 ms threshold so patient speech stops assistant playback promptly.
