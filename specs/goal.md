# Goal

## Objective
A working LiveKit outbound voice agent that calls a patient, explains their health biomarkers, books a doctor consultation via a tool call, and logs the full call with a post-call analysis and online evaluation to Opik.

## Repo Context
- New (greenfield) Python project; no existing code to preserve.
- Stack: LiveKit Agents (voice pipeline + outbound SIP calling), Opik (tracing and online evaluation).
- Folder layout is not fixed yet and will be decided as we build. One rule: all Opik code lives in a single standalone file (`opik_integration.py`) that plugs into the agent with minimal changes.
- Secrets (LiveKit, SIP, LLM/STT/TTS, Opik keys) come from `.env`; ship a `.env.example`.

## Requirements
- Trigger an outbound call with variables: name, phone number, biomarkers (e.g., blood glucose, HbA1c).
- Agent tells the patient their metrics and tries to schedule a doctor consultation.
- Appointment booking is simulated through a function/tool call.
- After the call ends, analyze the conversation and determine the outcome, including whether an appointment was booked.
- Send to Opik: call metadata and variables, transcript, recording/audio reference, tool calls and results, post-call analysis.
- Implement at least one online evaluation in Opik for the completed call.
- README with setup and usage instructions.

## Metrics / Definition of Done
- [ ] One command places a real outbound call to a test number.
- [ ] Agent states the correct patient name and biomarker values (no invented numbers).
- [ ] Booking tool is called and its result is reflected in the conversation.
- [ ] Post-call analysis outputs a clear `appointment_booked` true/false that matches the tool result.
- [ ] One Opik trace per call containing all five data items listed above.
- [ ] At least one online evaluation rule runs automatically and shows a score on the trace.
- [ ] Opik integration is in one file and wired in with only a few lines in the agent code.
- [ ] A fresh setup following the README works end to end.
- [ ] Demo covers the full flow: call, post-call analysis, Opik trace, evaluation.

## Boundaries & Guardrails
- Use dummy patient data only; no real health information.
- Never commit secrets or `.env`.
- Opik logging must never block or crash a live call (failures are caught and logged).
- Appointment booking stays simulated; no real scheduling or EHR systems.
- Don't spread Opik logic into the core agent files beyond the integration call.

## Exit Conditions / Stop Rules
- Stop and report if the SIP trunk or outbound call can't connect after 3 attempts; don't keep retrying.
- Stop and report if Opik credentials or API calls fail repeatedly, rather than working around them.
- Pause and ask before adding a new paid service or provider not already listed.
- If a requirement can't be met as written, report what blocked it instead of silently changing scope.