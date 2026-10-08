# Phase 2: Outbound calling with LiveKit Telephony

## Outcome

Manually place one outbound test call through LiveKit Telephony. Use the
LiveKit-purchased number as caller ID and an explicitly supplied test phone as
the destination. The call connects to the existing patient-specific voice
agent, which explains the dummy patient's biomarkers and can book a simulated
consultation.

## Decisions

- Use LiveKit Telephony with an outbound SIP trunk for outbound calling.
  LiveKit-purchased numbers currently support inbound calls only, so the trunk
  points at an external SIP carrier and uses the carrier's number as caller ID.
- Call a separate test phone number supplied for each manual call.
- Support manual, one-at-a-time test calls only. No automated or batch dialing.
- Reuse the existing agent, dummy patient records, and simulated appointment
  backend.
- Defer recording, post-call analysis, and Opik tracing/evaluation to a later
  phase.

## Prerequisites to confirm

Before implementation, verify the purchased number's LiveKit configuration and
the account's outbound-call prerequisites, including the SIP trunk, credentials,
and agent/room dispatch configuration. Use existing LiveKit resources; do not
add another paid provider or service.

Keep credentials and other secrets in `backend/.env`. Do not commit `.env` or
real patient data. Only use dummy patient records and a test destination.

## What to build

1. **Manual call trigger**: Provide one documented command or API operation that
   accepts a dummy patient ID and an explicitly supplied destination phone
   number, then initiates exactly one outbound call.
2. **LiveKit call path**: Place the call through LiveKit Telephony, use the
   purchased LiveKit number as caller ID, and connect the callee to the existing
   voice agent.
3. **Conversation and booking**: Preserve the existing identity confirmation,
   patient-specific biomarker values, and simulated booking flow. An affirmative
   response can book an available fake slot; declining must not book.
4. **Failure handling**: Report invalid configuration, call setup, and
   connection failures explicitly. Do not retry indefinitely or start
   additional calls automatically.
5. **Documentation**: Document the required LiveKit configuration, safe test
   procedure, invocation, and common setup/call failures.

## Done when

- [x] A documented manual invocation places one outbound call to an explicitly
  supplied test number through LiveKit Telephony.
- [x] The carrier number configured on the outbound trunk is used as caller ID.
- [x] The call reaches the agent with the selected dummy patient's identity and
  exact recorded biomarker values.
- [x] Accepting a consultation offer uses the existing fake slots and booking
  API, and the agent confirms the booking result.
- [x] Declining ends politely without creating a booking.
- [x] Missing or invalid call configuration and call setup failures are reported
  clearly; there is no batch dialing or unbounded automatic retry.
- [x] README setup and usage instructions support a fresh configuration using
  the required LiveKit settings without exposing secrets.

## Out of scope

- Automated, scheduled, or batch calls
- Real patient data or production patient outreach
- Call recording
- Post-call analysis
- Opik tracing and evaluation
- Real appointment scheduling or EHR integration

## Progress tracking

### Current phase

**Phase 2 — Outbound calling with LiveKit Telephony**

### Completed

- Added `backend/make_call.py`, which dispatches exactly one call for a patient
  ID and an E.164 destination.
- The agent worker dials through the outbound SIP trunk, waits for the answer,
  and runs the existing conversation and booking flow with telephony noise
  cancellation. Dial failures are logged with the SIP status code.
- Verified manual test calls end to end.

### Next

- Phase 3: recording, post-call analysis, and Opik tracing/evaluation.
