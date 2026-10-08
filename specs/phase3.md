# Phase 3: Recording, post-call analysis, and Opik

## Outcome

After each outbound call ends, the system produces a post-call analysis with a
clear `appointment_booked` true/false, and sends one Opik trace per call that
contains the call metadata and variables, transcript, recording reference, tool
calls and results, and the analysis. At least one online evaluation in Opik
scores each completed call automatically.

## Decisions

- All Opik code lives in one standalone file, `backend/opik_integration.py`,
  wired into the agent with only a few lines.
- Opik logging must never block or crash a live call. Failures are caught and
  logged.
- `appointment_booked` comes from the actual booking tool result, not only from
  the transcript, so the analysis can be checked against it.
- Store each call in one folder, `backend/calls/<room>/`, containing
  `audio.ogg` and `call.json` (metadata, transcript, tool calls); the analysis
  step adds `analysis.json`. The trace stores the audio path as the recording
  reference. `calls/` is git-ignored.
- Capture the transcript live from the session's conversation items and tool
  events instead of transcribing the recording afterwards.
  Cloud storage (for example S3 with LiveKit egress) is a possible later step.
- Keep the existing providers (Ollama, AssemblyAI, Cartesia). Opik is already
  part of the project stack; do not add any other new paid service without
  asking.
- Model speed, voice quality, and agent persona tuning are deferred and are not
  part of this phase.

## Open items to confirm before building

- **Analysis model:** use the local Ollama model for the post-call analysis, or
  another model already in the stack.
- **Evaluation:** choose the online evaluation rule, for example "booking claim
  matches tool result" or "biomarker values stated match the patient record".

## What to build

1. **Call data capture**: collect, per call, the metadata and variables
   (patient ID, name, destination, biomarkers, room, start/end time), the
   transcript, and every tool call with its arguments and result.
2. **Recording**: record each call's audio to a local file and keep its path as
   the recording reference. A recording failure is caught and logged and never
   interrupts the call.
3. **Post-call analysis**: after the call ends, analyze the transcript and tool
   results and output structured JSON that includes `appointment_booked`
   (true/false), the outcome, and a short summary. `appointment_booked` must
   match the booking tool's result.
4. **Opik integration** (`opik_integration.py`): send one trace per call
   containing the five data items: call metadata and variables, transcript,
   recording reference, tool calls and results, and the analysis.
5. **Online evaluation**: configure at least one Opik online evaluation rule
   that runs automatically on completed calls and shows a score on the trace.
6. **Documentation**: README setup for Opik credentials, recording, and a demo
   walkthrough from call to trace and evaluation score. Add Opik settings to
   `.env.example`.

## Done when

- [ ] Each call produces a local recording file with its path stored as the
  reference.
- [ ] Post-call analysis outputs `appointment_booked` true/false that matches
  the booking tool result for accepted and declined calls.
- [ ] One Opik trace per call contains all five data items.
- [ ] At least one online evaluation rule runs automatically and shows a score
  on the trace.
- [ ] Opik code is only in `opik_integration.py`, wired into the agent with a
  few lines.
- [ ] An Opik outage or invalid credentials does not interrupt a call; the
  error is logged.
- [ ] A fresh setup following the README works end to end without exposing
  secrets.
- [ ] A demo covers the full flow: call, post-call analysis, Opik trace,
  evaluation.

## Out of scope

- Model, latency, and audio-quality optimization
- Agent persona changes
- Automated, scheduled, or batch calls
- Cloud recording storage
- Real patient data, real appointment scheduling, or EHR integration

## Exit conditions

- If Opik credentials or API calls fail repeatedly, stop and report instead of
  working around them.
- If a requirement can't be met as written, report what blocked it instead of silently changing scope.

## Progress tracking

### Current phase

**Phase 3 — Recording, post-call analysis, and Opik**

### Completed

- Added `backend/call_capture.py`, which saves each call's audio, transcript,
  and tool calls under `backend/calls/<room>/` and is started from the agent
  session. Verified with simulated events; a live call still needs checking.
- Added `backend/post_call_analysis.py`. It writes `analysis.json` per call in a
  detached process (LiveKit's shutdown window is only 10 seconds). It sets
  `appointment_booked` from the booking tool result and uses the local Ollama
  model for `outcome`, `summary`, and whether the agent claimed a booking,
  flagging mismatches in `claim_matches_tool_result`. Verified on simulated
  booked, declined, undecided, interested, false-claim, and no-answer calls and
  on a real call; the booked path still needs a live call.

- Added `backend/opik_integration.py`. It sends one trace per call (variables,
  transcript, recording path, tool calls as spans, analysis) plus the scores
  `appointment_booked`, `booking_claim_matches_tool_result`, and
  `PII_handling`. It runs after the analysis with a three-line hook in
  `post_call_analysis.py`. Verified by
  reading traces back from Opik for a real and a simulated call.
- Added a PII handling evaluation field to `analysis.json`. It checks that
  identity is confirmed before patient-specific details are shared and that no
  unnecessary personal or health information is disclosed. Booking results
  include provider and appointment time.

- Added live OpenTelemetry export of LiveKit's spans (STT, LLM, TTS timings) to
  Opik via `setup_live_tracing`; verified spans arriving in the Opik project.
  Latency is read from these spans rather than stored in `call.json`.
- Switched the LLM to LFM2.5-1.2B-Instruct (Ollama) and the TTS voice to
  Cartesia "Fiona". Vobiz-side recordings are not used; the local recording
  is the source of truth.

### Next

- Configure the online evaluation rule in the Opik dashboard and confirm its
  score appears on a trace.
- Check a live accepted and a live declined call against `analysis.json`.
- Check that an invalid Opik key does not interrupt a call.
- Run the demo walkthrough and tick the checklist above.
