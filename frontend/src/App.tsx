import { type FormEvent, useEffect, useMemo, useState } from "react";
import { AuthProvider, LoginPage, useAuth } from "./auth";
import {
  ApiError,
  createPatient,
  createPrompt,
  createSlot,
  deletePrompt,
  deletePatient,
  deleteSlot,
  dispatchPatientCall,
  getDashboardSummary,
  getDeveloperConfig,
  getPatients,
  getPrompts,
  getSlots,
  previewPrompt,
  testDeveloperConfig,
  type Patient,
  type Slot,
  type ConfigSetting,
  type SystemPrompt,
  updateDeveloperConfig,
  updatePatient,
  updatePrompt,
  updateSlot,
} from "./api";

type Module = "admin" | "developer";

const moduleContent: Record<Module, {
  label: string;
  title: string;
  description: string;
  cards: Array<{ label: string; value: string; detail: string; tone?: string }>;
}> = {
  admin: {
    label: "Admin",
    title: "Patient operations",
    description: "Keep patient records, appointment capacity, and outreach in sync.",
    cards: [
      { label: "Patients", value: "—", detail: "Connect the patient directory" },
      { label: "Open slots", value: "—", detail: "Connect appointment availability", tone: "blue" },
      { label: "Calls today", value: "—", detail: "Call activity will appear here", tone: "orange" },
    ],
  },
  developer: {
    label: "Developer",
    title: "Agent workspace",
    description: "Configure providers and shape the assistant’s conversation safely.",
    cards: [
      { label: "Configuration", value: "—", detail: "Environment settings are next" },
      { label: "Active prompt", value: "—", detail: "Prompt version will appear here", tone: "blue" },
      { label: "Service health", value: "—", detail: "Runtime checks are next", tone: "orange" },
    ],
  },
};

function Dashboard() {
  const { userName, signOut } = useAuth();
  const [activeModule, setActiveModule] = useState<Module>("admin");
  const [summary, setSummary] = useState<Awaited<ReturnType<typeof getDashboardSummary>> | null>(null);
  const [summaryError, setSummaryError] = useState("");
  const content = moduleContent[activeModule];

  useEffect(() => {
    getDashboardSummary()
      .then(setSummary)
      .catch((error: unknown) => {
        if (error instanceof ApiError && error.status === 401) {
          void signOut();
          return;
        }
        setSummaryError("Dashboard data could not be loaded.");
      });
  }, [signOut]);

  const cards = activeModule === "admin"
    ? [
        { label: "Patients", value: summary ? String(summary.patient_count) : "—", detail: "Records in the local directory" },
        { label: "Open slots", value: summary ? String(summary.open_slot_count) : "—", detail: "Available consultation capacity", tone: "blue" },
        { label: "Calls today", value: "—", detail: "Call activity will appear here", tone: "orange" },
      ]
    : [
        { label: "Configuration", value: "—", detail: "Environment settings are next" },
        { label: "Active prompt", value: summary ? "Ready" : "—", detail: summary?.active_prompt_id ?? "Prompt version will appear here", tone: "blue" },
        { label: "Saved prompts", value: summary ? String(summary.prompt_count) : "—", detail: "Versioned prompts in the workspace", tone: "orange" },
      ];

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-mark" aria-hidden="true"><span>c</span></div>
          <div>
            <strong>careline</strong>
            <span>operations</span>
          </div>
        </div>
        <div className="workspace-label">Workspace</div>
        <nav className="module-nav" aria-label="Dashboard modules">
          <button
            className={`module-link ${activeModule === "admin" ? "active" : ""}`}
            onClick={() => setActiveModule("admin")}
            type="button"
          >
            <span className="nav-icon" aria-hidden="true">⌂</span>
            <span>Admin</span>
            <span className="nav-arrow" aria-hidden="true">→</span>
          </button>
          <button
            className={`module-link ${activeModule === "developer" ? "active" : ""}`}
            onClick={() => setActiveModule("developer")}
            type="button"
          >
            <span className="nav-icon" aria-hidden="true">&lt;/&gt;</span>
            <span>Developer</span>
            <span className="nav-arrow" aria-hidden="true">→</span>
          </button>
        </nav>
        <div className="sidebar-footer">
          <div className="status-dot"><span /> Local workspace</div>
          <p>Built for safe, focused care operations.</p>
        </div>
      </aside>

      <main className="main-content">
        <header className="topbar">
          <div className="mobile-brand">
            <div className="brand-mark" aria-hidden="true"><span>c</span></div>
            <strong>careline</strong>
          </div>
          <div className="topbar-actions">
            <span className="user-name">{userName}</span>
            <button className="user-avatar" aria-label="Sign out" onClick={signOut} type="button">CO</button>
          </div>
        </header>

        <div className="content-wrap">
          <div className="breadcrumb"><span>Workspace</span><span>/</span><strong>{content.label}</strong></div>
          <section className="page-heading">
            <div>
              <p className="eyebrow">{content.label} module</p>
              <h1>{content.title}</h1>
              <p>{content.description}</p>
            </div>
            <div className="module-switcher" role="group" aria-label="Switch module">
              {(Object.keys(moduleContent) as Module[]).map((module) => (
                <button
                  className={activeModule === module ? "selected" : ""}
                  key={module}
                  onClick={() => setActiveModule(module)}
                  type="button"
                >
                  {moduleContent[module].label}
                </button>
              ))}
            </div>
          </section>

          {summaryError && <p className="form-error dashboard-error" role="alert">{summaryError}</p>}
          <section className="metric-grid" aria-label={`${content.label} summary`}>
            {cards.map((card) => (
              <article className={`metric-card ${card.tone ?? ""}`} key={card.label}>
                <div className="metric-card-top"><span>{card.label}</span><span className="metric-dot" /></div>
                <strong>{card.value}</strong>
                <p>{card.detail}</p>
              </article>
            ))}
          </section>

          {activeModule === "admin" ? (
            <>
              <PatientDirectory onPatientChange={() => void getDashboardSummary().then(setSummary)} />
              <SlotManager />
            </>
          ) : (
            <DeveloperWorkspace onSummaryRefresh={() => void getDashboardSummary().then(setSummary)} />
          )}
        </div>
      </main>
    </div>
  );
}

const EMPTY_PATIENT: Patient = {
  id: "",
  name: "",
  phone: "+91",
  biomarkers: { glucose_mg_dl: 0, hba1c_percent: 0 },
};

function PatientDirectory({ onPatientChange }: { onPatientChange: () => void }) {
  const { signOut } = useAuth();
  const [patients, setPatients] = useState<Patient[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [search, setSearch] = useState("");
  const [form, setForm] = useState<Patient>(EMPTY_PATIENT);
  const [isEditing, setIsEditing] = useState(false);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [isCalling, setIsCalling] = useState(false);

  function loadPatients() {
    setIsLoading(true);
    getPatients()
      .then((result) => {
        setPatients(result);
        if (result.length && !selectedId) {
          setSelectedId(result[0].id);
          setForm(result[0]);
        }
      })
      .catch((requestError: unknown) => {
        if (requestError instanceof ApiError && requestError.status === 401) {
          void signOut();
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Patients could not be loaded.");
      })
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    loadPatients();
  }, []);

  const filteredPatients = useMemo(() => {
    const query = search.trim().toLowerCase();
    if (!query) return patients;
    return patients.filter((patient) =>
      [patient.id, patient.name, patient.phone].some((value) => value.toLowerCase().includes(query)),
    );
  }, [patients, search]);

  function selectPatient(patient: Patient) {
    setSelectedId(patient.id);
    setForm(patient);
    setIsEditing(false);
    setError("");
    setNotice("");
  }

  function startCreate() {
    setSelectedId("");
    setForm(EMPTY_PATIENT);
    setIsEditing(true);
    setError("");
    setNotice("");
  }

  function updateField(field: keyof Patient, value: string) {
    setForm((current) => ({ ...current, [field]: value }));
  }

  function updateBiomarker(field: "glucose_mg_dl" | "hba1c_percent", value: string) {
    setForm((current) => ({
      ...current,
      biomarkers: { ...current.biomarkers, [field]: Number(value) },
    }));
  }

  async function savePatient(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setNotice("");
    try {
      const saved = selectedId ? await updatePatient(form) : await createPatient(form);
      setPatients((current) => selectedId
        ? current.map((patient) => patient.id === saved.id ? saved : patient)
        : [...current, saved]);
      setSelectedId(saved.id);
      setForm(saved);
      setIsEditing(false);
      setNotice("Patient record saved.");
      onPatientChange();
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        void signOut();
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "Patient could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function removePatient() {
    if (!selectedId || !window.confirm(`Delete the record for ${form.name}? This cannot be undone.`)) return;
    setError("");
    setNotice("");
    try {
      await deletePatient(selectedId);
      const remaining = patients.filter((patient) => patient.id !== selectedId);
      setPatients(remaining);
      if (remaining[0]) selectPatient(remaining[0]);
      else startCreate();
      setNotice("Patient record deleted.");
      onPatientChange();
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Patient could not be deleted.");
    }

  }

  async function dispatchCall() {
    if (!selectedId || !window.confirm(`Place one call to ${form.name} at ${form.phone}?`)) return;
    setError("");
    setNotice("");
    setIsCalling(true);
    try {
      const result = await dispatchPatientCall(selectedId);
      setNotice(`Call dispatched to ${result.phone_number}. Room: ${result.room}`);
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Call could not be dispatched.");
    } finally {
      setIsCalling(false);
    }
  }

  return (
    <section className="directory-panel">
      <div className="directory-header">
        <div>
          <p className="eyebrow">Patient directory</p>
          <h2>Records and health details</h2>
        </div>
        <button className="button button-primary" onClick={startCreate} type="button">Add patient</button>
      </div>
      <div className="directory-layout">
        <div className="patient-list">
          <label className="search-label">
            Search patients
            <input value={search} onChange={(event) => setSearch(event.target.value)} placeholder="Name, ID, or phone" />
          </label>
          {isLoading && <p className="muted-message">Loading patient records…</p>}
          {!isLoading && !filteredPatients.length && <p className="muted-message">No patients match your search.</p>}
          <div className="patient-list-items">
            {filteredPatients.map((patient) => (
              <button
                className={`patient-list-item ${patient.id === selectedId ? "selected" : ""}`}
                key={patient.id}
                onClick={() => selectPatient(patient)}
                type="button"
              >
                <span className="patient-avatar">{patient.name.slice(0, 1).toUpperCase()}</span>
                <span><strong>{patient.name}</strong><small>{patient.id} · {patient.phone}</small></span>
              </button>
            ))}
          </div>
        </div>
        <div className="patient-detail">
          {isEditing ? (
            <form className="patient-form" onSubmit={savePatient}>
              <div className="detail-heading"><div><p className="eyebrow">Patient record</p><h2>{selectedId ? "Edit patient" : "New patient"}</h2></div></div>
              <label>Patient ID<input value={form.id} disabled={Boolean(selectedId)} onChange={(event) => updateField("id", event.target.value)} required /></label>
              <label>Full name<input value={form.name} onChange={(event) => updateField("name", event.target.value)} required /></label>
              <label>Indian phone number<input value={form.phone} onChange={(event) => updateField("phone", event.target.value)} required /></label>
              <div className="form-row">
                <label>Glucose (mg/dL)<input type="number" min="0" value={form.biomarkers.glucose_mg_dl} onChange={(event) => updateBiomarker("glucose_mg_dl", event.target.value)} required /></label>
                <label>HbA1c (%)<input type="number" min="0" step="0.1" value={form.biomarkers.hba1c_percent} onChange={(event) => updateBiomarker("hba1c_percent", event.target.value)} required /></label>
              </div>
              <div className="form-actions"><button className="button button-primary" disabled={isSaving} type="submit">{isSaving ? "Saving…" : "Save patient"}</button><button className="button button-secondary" onClick={() => selectedId ? setIsEditing(false) : selectPatient(patients[0] ?? EMPTY_PATIENT)} type="button">Cancel</button></div>
            </form>
          ) : (
            <div className="patient-detail-view">
              {selectedId ? (
                <>
                  <div className="detail-heading"><div><p className="eyebrow">Patient details</p><h2>{form.name}</h2><p className="detail-subtitle">{form.id} · {form.phone}</p></div><span className="verified-badge">Active record</span></div>
                  <div className="biomarker-grid"><div><span>Blood glucose</span><strong>{form.biomarkers.glucose_mg_dl} <small>mg/dL</small></strong></div><div><span>HbA1c</span><strong>{form.biomarkers.hba1c_percent}<small>%</small></strong></div></div>
                  <div className="form-actions"><button className="button button-primary" disabled={isCalling} onClick={dispatchCall} type="button">{isCalling ? "Dispatching…" : "Call patient"}</button><button className="button button-secondary" onClick={() => setIsEditing(true)} type="button">Edit details</button><button className="button button-danger" onClick={removePatient} type="button">Delete record</button></div>
                </>
              ) : <p className="muted-message">Select a patient to view details.</p>}
            </div>
          )}
          {error && <p className="form-error" role="alert">{error}</p>}
          {notice && <p className="form-success" role="status">{notice}</p>}
        </div>
      </div>
    </section>
  );
}

const EMPTY_SLOT = { id: "", provider: "", starts_at: "", duration_minutes: 30 };

function SlotManager() {
  const { signOut } = useAuth();
  const [slots, setSlots] = useState<Slot[]>([]);
  const [draft, setDraft] = useState(EMPTY_SLOT);
  const [editingId, setEditingId] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  function loadSlots() {
    setIsLoading(true);
    getSlots()
      .then(setSlots)
      .catch((requestError: unknown) => {
        if (requestError instanceof ApiError && requestError.status === 401) {
          void signOut();
          return;
        }
        setError(requestError instanceof Error ? requestError.message : "Slots could not be loaded.");
      })
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    loadSlots();
  }, []);

  function startCreate() {
    setDraft(EMPTY_SLOT);
    setEditingId("");
    setError("");
    setNotice("");
  }

  function startEdit(slot: Slot) {
    setEditingId(slot.id);
    setDraft({
      id: slot.id,
      provider: slot.provider,
      starts_at: slot.starts_at.slice(0, 16),
      duration_minutes: slot.duration_minutes,
    });
    setError("");
    setNotice("");
  }

  async function saveSlot(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setIsSaving(true);
    setError("");
    setNotice("");
    const payload = {
      ...draft,
      starts_at: `${draft.starts_at}:00+05:30`,
      duration_minutes: Number(draft.duration_minutes),
    };
    try {
      const saved = editingId ? await updateSlot(payload) : await createSlot(payload);
      setSlots((current) => editingId
        ? current.map((slot) => slot.id === saved.id ? saved : slot)
        : [...current, saved]);
      startCreate();
      setNotice("Slot saved.");
    } catch (requestError: unknown) {
      if (requestError instanceof ApiError && requestError.status === 401) {
        void signOut();
        return;
      }
      setError(requestError instanceof Error ? requestError.message : "Slot could not be saved.");
    } finally {
      setIsSaving(false);
    }
  }

  async function removeSlot(slot: Slot) {
    if (!window.confirm(`Delete the ${slot.provider} slot on ${formatSlotTime(slot.starts_at)}?`)) return;
    setError("");
    setNotice("");
    try {
      await deleteSlot(slot.id);
      setSlots((current) => current.filter((item) => item.id !== slot.id));
      setNotice("Slot deleted.");
    } catch (requestError: unknown) {
      setError(requestError instanceof Error ? requestError.message : "Slot could not be deleted.");
    }
  }

  return (
    <section className="directory-panel slots-panel">
      <div className="directory-header">
        <div><p className="eyebrow">Appointment capacity</p><h2>Consultation slots</h2></div>
        <button className="button button-primary" onClick={startCreate} type="button">New slot</button>
      </div>
      <div className="slots-layout">
        <div className="slot-list">
          {isLoading && <p className="muted-message">Loading slots…</p>}
          {!isLoading && !slots.length && <p className="muted-message">No appointment slots configured.</p>}
          {slots.map((slot) => (
            <div className="slot-row" key={slot.id}>
              <div><strong>{formatSlotTime(slot.starts_at)}</strong><small>{slot.provider} · {slot.duration_minutes} minutes</small></div>
              <div className="slot-row-actions"><span className={`slot-status ${slot.status}`}>{slot.status}</span><button className="text-button" disabled={slot.status === "booked"} onClick={() => startEdit(slot)} type="button">Edit</button><button className="text-button danger-text" disabled={slot.status === "booked"} onClick={() => removeSlot(slot)} type="button">Delete</button></div>
            </div>
          ))}
        </div>
        <form className="slot-form" onSubmit={saveSlot}>
          <p className="eyebrow">{editingId ? "Edit slot" : "Add slot"}</p>
          <label>Slot ID<input value={draft.id} disabled={Boolean(editingId)} onChange={(event) => setDraft({ ...draft, id: event.target.value })} required /></label>
          <label>Provider<input value={draft.provider} onChange={(event) => setDraft({ ...draft, provider: event.target.value })} required /></label>
          <label>India date and time<input type="datetime-local" value={draft.starts_at} onChange={(event) => setDraft({ ...draft, starts_at: event.target.value })} required /></label>
          <label>Duration (minutes)<input type="number" min="5" max="240" value={draft.duration_minutes} onChange={(event) => setDraft({ ...draft, duration_minutes: Number(event.target.value) })} required /></label>
          <div className="form-actions"><button className="button button-primary" disabled={isSaving} type="submit">{isSaving ? "Saving…" : "Save slot"}</button>{editingId && <button className="button button-secondary" onClick={startCreate} type="button">Cancel</button>}</div>
        </form>
      </div>
      {error && <p className="form-error directory-message" role="alert">{error}</p>}
      {notice && <p className="form-success directory-message" role="status">{notice}</p>}
    </section>
  );
}

function formatSlotTime(value: string) {
  return new Intl.DateTimeFormat("en-IN", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Kolkata",
  }).format(new Date(value));
}

const CONFIG_GROUPS = [
  { title: "LLM, model and voice", keys: ["LLM_PROVIDER", "LLM_MODEL", "LLM_BASE_URL", "LLM_API_KEY", "ASSEMBLYAI_API_KEY", "CARTESIA_API_KEY", "CARTESIA_VOICE_ID"] },
  { title: "LiveKit and calling", keys: ["LIVEKIT_URL", "LIVEKIT_API_KEY", "LIVEKIT_API_SECRET", "SIP_OUTBOUND_TRUNK_ID"] },
  { title: "Agent and evaluation", keys: ["PATIENT_ID", "AGENT_PROMPT_ID", "OPIK_API_KEY", "OPIK_WORKSPACE", "OPIK_PROJECT_NAME"] },
];

const CONFIG_LABELS: Record<string, string> = {
  LLM_PROVIDER: "LLM provider (ollama, openai, google, anthropic)",
  LLM_MODEL: "LLM model",
  LLM_BASE_URL: "LLM base URL (optional for native providers)",
  LLM_API_KEY: "LLM API key",
  OLLAMA_MODEL: "Local model",
  OLLAMA_BASE_URL: "Local model URL",
  ASSEMBLYAI_API_KEY: "AssemblyAI API key",
  CARTESIA_API_KEY: "Cartesia API key",
  CARTESIA_VOICE_ID: "Cartesia voice ID",
  LIVEKIT_URL: "LiveKit URL",
  LIVEKIT_API_KEY: "LiveKit API key",
  LIVEKIT_API_SECRET: "LiveKit API secret",
  SIP_OUTBOUND_TRUNK_ID: "Outbound SIP trunk ID",
  PATIENT_ID: "Default patient ID",
  AGENT_PROMPT_ID: "Active prompt ID",
  OPIK_API_KEY: "Opik API key",
  OPIK_WORKSPACE: "Opik workspace",
  OPIK_PROJECT_NAME: "Opik project",
};

function DeveloperWorkspace({ onSummaryRefresh }: { onSummaryRefresh: () => void }) {
  const { signOut } = useAuth();
  const [settings, setSettings] = useState<ConfigSetting[]>([]);
  const [values, setValues] = useState<Record<string, string>>({});
  const [prompts, setPrompts] = useState<SystemPrompt[]>([]);
  const [selectedPrompt, setSelectedPrompt] = useState<SystemPrompt | null>(null);
  const [isNewPrompt, setIsNewPrompt] = useState(false);
  const [promptForm, setPromptForm] = useState({ id: "", description: "", template: "" });
  const [preview, setPreview] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [isSavingConfig, setIsSavingConfig] = useState(false);
  const [isSavingPrompt, setIsSavingPrompt] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const [health, setHealth] = useState("");

  function handleUnauthorized(requestError: unknown) {
    if (requestError instanceof ApiError && requestError.status === 401) {
      void signOut();
      return true;
    }
    return false;
  }

  function loadDeveloperData() {
    setIsLoading(true);
    Promise.all([getDeveloperConfig(), getPrompts()])
      .then(([configResponse, promptResponse]) => {
        setSettings(configResponse.settings);
        setValues(Object.fromEntries(configResponse.settings.map((setting) => [setting.key, setting.value])));
        setPrompts(promptResponse.prompts);
        const active = promptResponse.prompts.find((prompt) => prompt.active) ?? promptResponse.prompts[0] ?? null;
        if (active) {
          setSelectedPrompt(active);
          setPromptForm({ id: active.id, description: active.description, template: active.template });
        }
      })
      .catch((requestError: unknown) => {
        if (handleUnauthorized(requestError)) return;
        setError(requestError instanceof Error ? requestError.message : "Developer settings could not be loaded.");
      })
      .finally(() => setIsLoading(false));
  }

  useEffect(() => {
    loadDeveloperData();
  }, []);

  async function saveConfig(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setIsSavingConfig(true);
    try {
      const response = await updateDeveloperConfig(values);
      setSettings(response.settings);
      setValues(Object.fromEntries(response.settings.map((setting) => [setting.key, setting.value])));
      setNotice("Saved to backend/.env. New calls will use these settings; an active call keeps its current configuration.");
      onSummaryRefresh();
    } catch (requestError: unknown) {
      if (handleUnauthorized(requestError)) return;
      setError(requestError instanceof Error ? requestError.message : "Configuration could not be saved.");
    } finally {
      setIsSavingConfig(false);
    }
  }

  async function runHealthCheck() {
    setError("");
    setHealth("");
    try {
      const result = await testDeveloperConfig();
      setHealth(`${result.configured_count} of ${result.total_count} service groups configured.`);
    } catch (requestError: unknown) {
      if (handleUnauthorized(requestError)) return;
      setError(requestError instanceof Error ? requestError.message : "Configuration test failed.");
    }
  }

  function selectPrompt(prompt: SystemPrompt) {
    setSelectedPrompt(prompt);
    setIsNewPrompt(false);
    setPromptForm({ id: prompt.id, description: prompt.description, template: prompt.template });
    setPreview("");
    setError("");
  }

  function startNewPrompt() {
    setSelectedPrompt(null);
    setIsNewPrompt(true);
    setPromptForm({ id: "", description: "", template: "" });
    setPreview("");
    setError("");
  }

  async function selectActivePrompt(prompt: SystemPrompt) {
    setError("");
    try {
      await updateDeveloperConfig({ AGENT_PROMPT_ID: prompt.id });
      setPrompts((current) => current.map((item) => ({ ...item, active: item.id === prompt.id })));
      setNotice(`Active prompt changed to ${prompt.id}.`);
      onSummaryRefresh();
    } catch (requestError: unknown) {
      if (handleUnauthorized(requestError)) return;
      setError(requestError instanceof Error ? requestError.message : "Active prompt could not be changed.");
    }
  }

  async function savePrompt(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setNotice("");
    setIsSavingPrompt(true);
    try {
      const saved = isNewPrompt
        ? await createPrompt(promptForm)
        : await updatePrompt(promptForm);
      setPrompts((current) => isNewPrompt ? [...current, { ...saved, active: false }] : current.map((item) => item.id === saved.id ? { ...saved, active: item.active } : item));
      setSelectedPrompt({ ...saved, active: selectedPrompt?.active ?? false });
      setIsNewPrompt(false);
      setNotice("System prompt saved.");
      onSummaryRefresh();
    } catch (requestError: unknown) {
      if (handleUnauthorized(requestError)) return;
      setError(requestError instanceof Error ? requestError.message : "Prompt could not be saved.");
    } finally {
      setIsSavingPrompt(false);
    }
  }

  async function removePrompt() {
    if (!selectedPrompt || !window.confirm(`Delete the prompt "${selectedPrompt.id}"?`)) return;
    setError("");
    try {
      await deletePrompt(selectedPrompt.id);
      const remaining = prompts.filter((prompt) => prompt.id !== selectedPrompt.id);
      setPrompts(remaining);
      if (remaining[0]) selectPrompt(remaining[0]);
      else startNewPrompt();
      setNotice("System prompt deleted.");
      onSummaryRefresh();
    } catch (requestError: unknown) {
      if (handleUnauthorized(requestError)) return;
      setError(requestError instanceof Error ? requestError.message : "Prompt could not be deleted.");
    }
  }

  async function showPreview() {
    setError("");
    try {
      const response = await previewPrompt(promptForm.template);
      setPreview(response.preview);
    } catch (requestError: unknown) {
      if (handleUnauthorized(requestError)) return;
      setError(requestError instanceof Error ? requestError.message : "Prompt preview failed.");
    }
  }

  return (
    <div className="developer-workspace">
      {isLoading && <p className="muted-message">Loading developer settings…</p>}
      <section className="developer-card">
        <div className="developer-card-header"><div><p className="eyebrow">Runtime configuration</p><h2>Providers and environment</h2><p>Secret values are masked and are never returned to the browser.</p></div><button className="button button-secondary" onClick={runHealthCheck} type="button">Test configuration</button></div>
        <form className="config-form" onSubmit={saveConfig}>
          {CONFIG_GROUPS.map((group) => (
            <fieldset key={group.title}><legend>{group.title}</legend><div className="config-grid">
              {group.keys.map((key) => {
                const setting = settings.find((item) => item.key === key);
                const input = key === "LLM_PROVIDER"
                  ? <select value={values[key] ?? "ollama"} onChange={(event) => setValues({ ...values, [key]: event.target.value })}><option value="ollama">Ollama (local)</option><option value="openai">OpenAI</option><option value="google">Google Gemini</option><option value="anthropic">Anthropic Claude</option></select>
                  : setting?.secret
                    ? <input type="password" value={values[key] ?? ""} placeholder={setting.masked || "Not configured"} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />
                    : <input value={values[key] ?? ""} onChange={(event) => setValues({ ...values, [key]: event.target.value })} />;
                return <label key={key}>{CONFIG_LABELS[key]}{input}<small>{setting?.configured ? setting.secret ? "Configured · leave blank to preserve" : "Configured" : "Not configured"}</small></label>;
              })}
            </div></fieldset>
          ))}
          <div className="form-actions"><button className="button button-primary" disabled={isSavingConfig} type="submit">{isSavingConfig ? "Saving…" : "Save configuration"}</button>{health && <span className="form-success">{health}</span>}</div>
        </form>
      </section>

      <section className="developer-card">
        <div className="developer-card-header"><div><p className="eyebrow">System prompts</p><h2>Prompt versions</h2><p>Use supported variables: {"{patient_name}"}, {"{glucose_mg_dl}"}, {"{hba1c_percent}"}.</p></div><button className="button button-primary" onClick={startNewPrompt} type="button">New prompt</button></div>
        <div className="prompt-layout">
          <div className="prompt-list">{prompts.map((prompt) => <button className={`prompt-list-item ${selectedPrompt?.id === prompt.id ? "selected" : ""}`} key={prompt.id} onClick={() => selectPrompt(prompt)} type="button"><span><strong>{prompt.id}</strong><small>{prompt.description}</small></span>{prompt.active && <em>Active</em>}</button>)}</div>
          <form className="prompt-editor" onSubmit={savePrompt}>
            <label>Prompt ID<input value={promptForm.id} disabled={!isNewPrompt} onChange={(event) => setPromptForm({ ...promptForm, id: event.target.value })} required /></label>
            <label>Description<input value={promptForm.description} onChange={(event) => setPromptForm({ ...promptForm, description: event.target.value })} required /></label>
            <label>Template<textarea value={promptForm.template} onChange={(event) => setPromptForm({ ...promptForm, template: event.target.value })} rows={10} required /></label>
            <div className="form-actions"><button className="button button-primary" disabled={isSavingPrompt} type="submit">{isSavingPrompt ? "Saving…" : "Save prompt"}</button><button className="button button-secondary" onClick={showPreview} type="button">Preview</button>{selectedPrompt && <button className="button button-danger" onClick={removePrompt} type="button">Delete</button>}{selectedPrompt && !selectedPrompt.active && <button className="button button-secondary" onClick={() => void selectActivePrompt(selectedPrompt)} type="button">Set active</button>}</div>
            {preview && <div className="prompt-preview"><strong>Preview with dummy values</strong><pre>{preview}</pre></div>}
          </form>
        </div>
      </section>
      {error && <p className="form-error developer-message" role="alert">{error}</p>}
      {notice && <p className="form-success developer-message" role="status">{notice}</p>}
    </div>
  );
}

export function App() {
  return (
    <AuthProvider>
      <AuthenticatedApp />
    </AuthProvider>
  );
}

function AuthenticatedApp() {
  const { isAuthenticated } = useAuth();
  return isAuthenticated ? <Dashboard /> : <LoginPage />;
}
