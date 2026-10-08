# Phase 4: Admin and developer dashboard

## Outcome

Build a minimal, professional web dashboard for the existing healthcare voice
agent. One hard-coded account can switch between two modules:

- **Admin** — manage dummy patients and appointment slots, inspect patient
  details, and place a single outbound call to a patient's associated Indian
  phone number.
- **Developer** — manage runtime configuration and versioned system prompts
  without editing files manually.

The dashboard is an operational frontend for the current backend. It must
preserve the existing dummy-data and one-call-at-a-time safety boundaries.

## Design direction

Use the supplied reference image as visual inspiration without copying its
branding:

- White workspace with generous spacing and a clean, restrained layout.
- Deep navy for primary text, navigation, and high-contrast surfaces.
- Bright sky blue for selected states, links, data highlights, and supporting
  accents.
- Warm orange for primary actions, call actions, and important attention
  states.
- Light blue backgrounds and subtle blue line/wave details only where they
  improve hierarchy; avoid decorative clutter.
- Rounded controls and cards, clear typography, visible focus states, and
  responsive layouts for desktop and tablet widths.

The shell should have a compact sidebar or top navigation, a clear module
switcher for **Admin** and **Developer**, a page title/breadcrumb area, and
consistent loading, empty, success, and error states.

## Decisions

- Keep Admin and Developer in one account and one dashboard shell; do not
  create separate login experiences.
- Use hard-coded authentication for this phase only. Make the limitation
  explicit in the UI and documentation; do not represent it as production
  security.
- Use the existing FastAPI service as the source of truth. Add JSON API
  endpoints rather than having the browser read or write local files directly.
- Keep the current dummy patient records, fake slots, and manual outbound-call
  guardrails. No batch, scheduled, or automatic dialing.
- Store prompt changes in `backend/agent_prompts.json` using the existing
  `id`, `description`, and `template` shape.
- Treat API keys, LiveKit credentials, SIP identifiers, and other environment
  values as secrets. Never return plaintext secrets to the browser after
  saving; display masked values and provide explicit save/test actions.
- Do not commit `backend/.env` or real patient information.

## Proposed implementation

Use a small TypeScript React frontend with a Vite-style development setup,
unless the repository gains an established frontend stack before
implementation. Keep the frontend API client, auth guard, shared layout, form
controls, tables, dialogs, and notifications reusable across both modules.

### Shared dashboard

1. Hard-coded sign-in screen with a documented development account.
2. Session state and protected routes for the dashboard.
3. Module switcher between Admin and Developer.
4. Responsive navigation and account menu with sign-out.
5. Shared confirmation dialogs, toast notifications, form validation, and
   explicit API error handling.
6. Accessible keyboard navigation, labels, focus treatment, semantic tables,
   and sufficient color contrast.

### Admin module

1. **Overview**
   - Patient count, available-slot count, and recent call/booking status where
     the backend can provide reliable data.
   - Quick links to patients, slots, and dispatching.
2. **Patients**
   - List/search patients by name, ID, or phone.
   - Create, view, edit, and delete patient records.
   - Patient detail view with identity fields and recorded biomarkers.
   - Confirm destructive deletion and show clear validation errors.
3. **Slots**
   - List available and booked slots with provider, start time, and duration.
   - Create, edit, and delete slots where the backend can safely support it.
   - Prevent deleting or editing a slot in a way that corrupts an existing
     appointment.
4. **Patient actions**
   - Show the patient's associated Indian number in a normalized, readable
     format.
   - Provide a dispatch-call form with an explicit confirmation step.
   - Dispatch exactly one call to the selected patient's associated number,
     show progress and the returned call/room identifier, and surface setup or
     telephony failures.
   - Do not allow arbitrary destination numbers or batch selection in this
     phase.

### Developer module

1. **Runtime configuration**
   - Form sections for every supported setting represented by
     `backend/.env.example`, including local-model, STT/TTS, LiveKit,
     outbound SIP, and Opik settings.
   - Distinguish secret fields from ordinary settings.
   - Mask stored secrets, allow intentional replacement, validate URLs and
     required formats, and show whether a value is configured without exposing
     it.
   - Save atomically with validation and report restart/reload requirements.
   - Add a safe configuration health/test action that reports provider
     connectivity without returning secret values.
2. **System prompts**
   - List prompts from `backend/agent_prompts.json`.
   - Create, view, edit, and delete prompts.
   - Validate unique IDs, required descriptions/templates, and supported
     template variables.
   - Show a preview using dummy patient values before saving.
   - Require confirmation for deletion and identify the currently selected
     `AGENT_PROMPT_ID`.
   - Preserve valid JSON and prevent partial writes or duplicate IDs.

## Backend/API work

Extend the FastAPI backend with authenticated dashboard endpoints, using the
hard-coded phase-4 account guard consistently:

- `POST /auth/login` and `POST /auth/logout` (or an equivalent small session
  mechanism).
- Patient CRUD endpoints backed by `patients.json`.
- Slot CRUD endpoints with booking-aware validation.
- Patient detail and dashboard summary endpoints.
- A single-call dispatch endpoint that accepts only a patient ID and uses the
  patient's associated phone number.
- Runtime configuration read/update/test endpoints with secret masking and
  server-side validation.
- Prompt list/create/update/delete/preview endpoints backed by
  `agent_prompts.json`.

Use file locking or an equivalent atomic read-modify-write strategy for JSON
files. Return structured validation and conflict errors. Keep provider calls
and file-write failures visible in logs and API responses; do not silently
fall back to success.

## Safety and privacy boundaries

- This phase continues to use dummy patient data only.
- Indian phone numbers must be validated and normalized before dispatch.
- A call requires explicit user confirmation and must produce one dispatch
  request only.
- Never log or display environment secret values, full API keys, or call
  credentials.
- The hard-coded login is not suitable for production; production
  authentication, authorization, audit logging, and secret storage are
  follow-up work.

## Verification plan

- Frontend type-check, lint, and production build.
- Backend API tests for auth, patient CRUD, slot conflict handling, call
  dispatch validation, masked configuration, and prompt CRUD/atomic writes.
- Component tests for module switching, protected routes, validation, delete
  confirmations, masked secrets, and call-dispatch confirmation.
- Manual responsive and accessibility pass at desktop and tablet widths.
- End-to-end smoke test:
  sign in, inspect a patient, edit and restore a dummy record, create and
  remove a test slot, preview and save a prompt, save a non-secret setting,
  and dispatch exactly one explicitly confirmed test call.

## Done when

- [ ] A hard-coded user can sign in and switch between Admin and Developer in
  one dashboard.
- [ ] The UI follows the navy, sky-blue, orange, and white visual direction
  with responsive and accessible states.
- [ ] Admin can CRUD dummy patients and safely inspect patient details.
- [ ] Admin can manage slots without corrupting booked appointments.
- [ ] Admin can dispatch one confirmed call to a patient's associated Indian
  number and see explicit success/failure feedback.
- [ ] Developer can view, validate, mask, save, and test all supported
  `.env.example` settings without exposing secrets.
- [ ] Developer can CRUD `agent_prompts.json` entries, preview variables, and
  select/identify the active prompt.
- [ ] JSON writes are atomic, errors are explicit, and existing voice-agent
  behavior remains intact.
- [ ] Tests, type-checking, linting, and the documented smoke test pass.

## Out of scope

- Production authentication, role-based access control, user management, or
  multi-tenant accounts.
- Real patient data, EHR integration, or real appointment scheduling.
- Batch, scheduled, automated, or arbitrary-number calling.
- Secret rotation, external vault integration, or exposing environment values
  in client-side storage.
- Call recording and Opik analysis redesign.
- Advanced analytics, billing, or general-purpose infrastructure monitoring.

## Progress tracking

### Current phase

**Phase 4 — Planned: Admin and developer dashboard**

### Completed

- Defined the shared dashboard, Admin module, and Developer module scope.
- Defined the visual direction from the supplied reference image.
- Defined backend API, secret-handling, calling, prompt, and verification
  boundaries.
- Added the React/TypeScript frontend foundation under `frontend/`.
- Added the responsive navy, sky-blue, orange, and white dashboard shell.
- Added the hard-coded development sign-in guard and shared Admin/Developer
  module switcher.
- Added FastAPI development login/logout sessions and CORS support for the
  local frontend.
- Added a protected dashboard summary endpoint and connected the frontend
  metric cards to live patient, slot, and prompt counts.
- Added protected patient list, detail, create, update, and delete endpoints
  with schema validation and atomic JSON writes.
- Added the Admin patient directory with search, patient detail biomarker
  display, create/edit forms, and delete confirmation.
- Added protected slot list, create, update, and delete endpoints with
  booked-slot safeguards and atomic JSON writes.
- Added the Admin slot manager with India timezone display, availability
  status, and booked-slot edit/delete protection.
- Added a confirmed single-patient call action that dispatches only to the
  selected patient's stored phone number and returns the LiveKit room.
- Added protected Developer configuration endpoints for all
  `.env.example` settings, masked secret handling, atomic `.env` updates, and
  non-secret configuration health checks.
- Added protected system-prompt CRUD, active-prompt selection, supported
  variable validation, and dummy-value preview endpoints.
- Added the Developer configuration and prompt editor UI with responsive
  provider sections, secret preservation behavior, health checks, prompt
  preview, and active/deletion safeguards.
- Verified the frontend production build with `npm run build`.
- Smoke-tested backend login and the protected dashboard summary endpoint.
- Smoke-tested the complete patient CRUD lifecycle with a temporary record.
- Smoke-tested the complete slot CRUD lifecycle with a temporary slot.
- Smoke-tested masked configuration output, configuration checks, prompt
  preview, prompt validation, and temporary prompt CRUD.

### Next

- Run an end-to-end manual pass across both modules and refine any UX issues.
- Add focused automated API/component tests for the completed Phase 4 flows.
