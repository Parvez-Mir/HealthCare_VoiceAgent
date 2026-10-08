import { type FormEvent, useEffect, useMemo, useState } from "react";
import { AuthProvider, LoginPage, useAuth } from "./auth";
import {
  ApiError,
  createPatient,
  createSlot,
  deletePatient,
  deleteSlot,
  dispatchPatientCall,
  getDashboardSummary,
  getPatients,
  getSlots,
  type Patient,
  type Slot,
  updatePatient,
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
            <section className="empty-panel">
            <div className="empty-illustration" aria-hidden="true">
              <span />
              <span />
              <span />
            </div>
            <p className="eyebrow">Phase 4 foundation</p>
            <h2>Your {content.label.toLowerCase()} workspace is ready</h2>
            <p>The shared dashboard is connected. The {content.label.toLowerCase()} tools will be added in the next implementation slice.</p>
            </section>
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
