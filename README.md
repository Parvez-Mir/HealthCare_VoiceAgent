# HealthCare Voice Agent

Healthcare appointment assistant that can call patients, hold a real-time
voice conversation, verify identity, check appointment slots, and book an
appointment. It includes an operations dashboard for Admin and Developer users.

The voice stack uses LiveKit Agents with AssemblyAI STT, Cartesia TTS, Silero VAD, and selectable native LiveKit LLM providers: Ollama, OpenAI, Google Gemini, and Anthropic Claude.

## Repository structure

```text
backend/
  app.py                  FastAPI API, authentication, dashboard endpoints
  voice_agent.py          LiveKit voice worker and conversation tools
  make_call.py            Manual outbound call command
  call_capture.py         Call transcript and audio capture
  post_call_analysis.py   Post-call outcome analysis
  opik_integration.py     Opik traces and evaluation scores
  patients.json           Dummy patient records
  slots.json              Dummy appointment slots
  agent_prompts.json      Versioned system prompts
  requirements.txt        Python dependencies
  .env.example            Runtime configuration template

frontend/
  src/                    React and TypeScript dashboard
  package.json            Frontend dependencies and scripts

docker-compose.yml        API, voice worker, and frontend services
specs/                    Project specifications
```

### Main technologies

- **Backend:** Python, FastAPI, Uvicorn
- **Voice:** LiveKit Agents, AssemblyAI, Cartesia, Silero
- **LLM:** Native LiveKit plugins for Ollama, OpenAI, Gemini, and Claude
- **Frontend:** React, TypeScript, Vite
- **Persistence:** JSON files and local call folders
- **Observability:** Opik and OpenTelemetry

## Configuration

Create the runtime configuration:

```bash
cp backend/.env.example backend/.env
```

The main LLM settings are:

```env
LLM_PROVIDER=ollama
LLM_MODEL=hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q8_0
LLM_BASE_URL=http://127.0.0.1:11434/v1
LLM_API_KEY=
```

Supported providers are `ollama`, `openai`, `google`, and `anthropic`.
Configure the relevant model, API key, LiveKit credentials, AssemblyAI key, Cartesia key, and SIP trunk ID in `backend/.env`.

Never commit `backend/.env`.

## Local setup without Docker

This setup runs the API, voice worker, and frontend in separate terminals.

### 1. Install backend dependencies

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
cp .env.example .env
```

Edit `backend/.env` with the required credentials.

For Ollama, install Ollama separately and download the configured model:

```bash
ollama pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q8_0
```

If you select OpenAI, Gemini, or Claude instead, configure its API key and
model in `backend/.env`; Ollama is not required.

### 2. Terminal 1: start the FastAPI backend

From the repository root:

```bash
cd backend
.venv/bin/python -m uvicorn app:app --reload
```

Verify it is running:

```bash
curl http://127.0.0.1:8000/health
```

### 3. Terminal 2: start the LiveKit voice worker

```bash
cd backend
.venv/bin/python voice_agent.py dev
```

Keep this terminal running. It receives LiveKit jobs and starts the
conversation for each call.

### 4. Terminal 3: start the frontend

```bash
cd frontend
npm install
npm run dev
```

Open <http://localhost:5173>.

Development login:

```text
Email:    admin@careline.dev
Password: careline-dev
```

The dashboard provides:

- **Admin:** patient details, biomarker information, slots, and outbound call dispatch
- **Developer:** LLM/provider settings, masked secrets, configuration checks, and prompt CRUD

### 5. Optional: place a manual outbound call

Configure LiveKit and an outbound SIP trunk in `backend/.env`, then run:

```bash
cd backend
.venv/bin/python make_call.py patient-001 +14155550123
```

Use E.164 test numbers only and keep patient data fictional.

## Local setup with Docker

Docker Compose starts the API, LiveKit worker, and production frontend.

### Important first-run note

The first setup can take several minutes. Ollama must download and store the
local model, which may be several gigabytes depending on the selected model.
The model download happens before the containers start.

Install and start Ollama on the host, then pull the model:

```bash
ollama serve
```

In another terminal:

```bash
ollama pull hf.co/LiquidAI/LFM2.5-1.2B-Instruct-GGUF:Q8_0
```

Create and configure the environment file:

```bash
cp backend/.env.example backend/.env
```

When using Ollama from Docker on macOS or Windows, set:

```env
LLM_PROVIDER=ollama
LLM_BASE_URL=http://host.docker.internal:11434/v1
```

Do not use `http://127.0.0.1:11434/v1` for the Docker worker. Inside a
container, `127.0.0.1` points to the container itself. If the worker cannot
connect to Ollama, verify connectivity from the container:

```bash
docker compose exec agent python -c \
"import urllib.request; print(urllib.request.urlopen('http://host.docker.internal:11434/api/tags').read().decode())"
```

If Ollama is only listening on the host loopback interface, restart it with:

```bash
OLLAMA_HOST=0.0.0.0:11434 ollama serve
```

For OpenAI, Gemini, or Claude, set the provider and API key instead. Then
start the stack:

```bash
docker compose up --build
```

Open:

- Frontend: <http://localhost:5173>
- API: <http://localhost:8000>
- Health check: <http://localhost:8000/health>

Useful commands:

```bash
docker compose logs -f api
docker compose logs -f agent
docker compose ps
docker compose down
```

The `backend/` directory is mounted into the containers, so patient data,
slots, prompts, configuration, and call output persist locally.

## Call output and observability

Each call is stored under:

```text
backend/calls/{UTC date}/{patient-id}/{room-name}/
```

The folder contains call metadata, transcript/tool activity, recording output,
and post-call analysis. Configuration snapshots identify the provider, model,
prompt, and voice used for that call without storing API keys.

Opik receives call traces, tool activity, analysis results, and application
scores for booking correctness and PII handling. Configure it through the
`OPIK_*` values in `backend/.env`.

## Development limitations

- Authentication is hard-coded for development.
- Patient and slot data are stored in JSON files.
- Booking state is in memory and resets when the backend restarts.
- Use dummy patient data and test callers only.
