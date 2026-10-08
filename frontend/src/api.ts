const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";
const TOKEN_KEY = "careline-dashboard-token";

export type DashboardSummary = {
  patient_count: number;
  open_slot_count: number;
  prompt_count: number;
  active_prompt_id: string;
};

export type Patient = {
  id: string;
  name: string;
  phone: string;
  biomarkers: {
    glucose_mg_dl: number;
    hba1c_percent: number;
  };
};

export type Slot = {
  id: string;
  provider: string;
  starts_at: string;
  duration_minutes: number;
  status: "available" | "booked";
};

export type ConfigSetting = {
  key: string;
  value: string;
  configured: boolean;
  secret: boolean;
  masked: string;
};

export type SystemPrompt = {
  id: string;
  description: string;
  template: string;
  active: boolean;
};

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

async function request<T>(path: string, options: RequestInit = {}): Promise<T> {
  const token = window.sessionStorage.getItem(TOKEN_KEY);
  const headers = new Headers(options.headers);
  headers.set("Content-Type", "application/json");
  if (token) {
    headers.set("Authorization", `Bearer ${token}`);
  }

  const response = await fetch(`${API_BASE_URL}${path}`, { ...options, headers });
  if (!response.ok) {
    let message = `Request failed with status ${response.status}`;
    try {
      const body = (await response.json()) as { detail?: string };
      if (body.detail) message = body.detail;
    } catch {
      // Keep the status-based error when the server did not return JSON.
    }
    throw new ApiError(message, response.status);
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export async function login(email: string, password: string) {
  const response = await request<{
    access_token: string;
    user: { email: string; name: string };
  }>("/auth/login", {
    method: "POST",
    body: JSON.stringify({ email, password }),
  });
  window.sessionStorage.setItem(TOKEN_KEY, response.access_token);
  return response.user;
}

export async function logout() {
  try {
    await request<void>("/auth/logout", { method: "POST" });
  } finally {
    window.sessionStorage.removeItem(TOKEN_KEY);
  }
}

export function getDashboardSummary() {
  return request<DashboardSummary>("/dashboard/summary");
}

export function getPatients() {
  return request<Patient[]>("/patients");
}

export function createPatient(patient: Patient) {
  return request<Patient>("/patients", {
    method: "POST",
    body: JSON.stringify(patient),
  });
}

export function updatePatient(patient: Patient) {
  return request<Patient>(`/patients/${encodeURIComponent(patient.id)}`, {
    method: "PUT",
    body: JSON.stringify(patient),
  });
}

export function deletePatient(patientId: string) {
  return request<void>(`/patients/${encodeURIComponent(patientId)}`, { method: "DELETE" });
}

export function getSlots() {
  return request<Slot[]>("/dashboard/slots");
}

export function createSlot(slot: Omit<Slot, "status">) {
  return request<Slot>("/dashboard/slots", {
    method: "POST",
    body: JSON.stringify(slot),
  });
}

export function updateSlot(slot: Omit<Slot, "status">) {
  return request<Slot>(`/dashboard/slots/${encodeURIComponent(slot.id)}`, {
    method: "PUT",
    body: JSON.stringify(slot),
  });
}

export function deleteSlot(slotId: string) {
  return request<void>(`/dashboard/slots/${encodeURIComponent(slotId)}`, { method: "DELETE" });
}

export function dispatchPatientCall(patientId: string) {
  return request<{ patient_id: string; phone_number: string; room: string; status: string }>("/calls", {
    method: "POST",
    body: JSON.stringify({ patient_id: patientId }),
  });
}

export function getDeveloperConfig() {
  return request<{ settings: ConfigSetting[] }>("/developer/config");
}

export function updateDeveloperConfig(values: Record<string, string>) {
  return request<{ settings: ConfigSetting[] }>("/developer/config", {
    method: "PUT",
    body: JSON.stringify({ values }),
  });
}

export function testDeveloperConfig() {
  return request<{ checks: Record<string, boolean>; configured_count: number; total_count: number }>("/developer/config/test", {
    method: "POST",
  });
}

export function getPrompts() {
  return request<{ prompts: SystemPrompt[] }>("/developer/prompts");
}

export function createPrompt(prompt: Omit<SystemPrompt, "active">) {
  return request<SystemPrompt>("/developer/prompts", {
    method: "POST",
    body: JSON.stringify(prompt),
  });
}

export function updatePrompt(prompt: Omit<SystemPrompt, "active">) {
  return request<SystemPrompt>(`/developer/prompts/${encodeURIComponent(prompt.id)}`, {
    method: "PUT",
    body: JSON.stringify(prompt),
  });
}

export function deletePrompt(promptId: string) {
  return request<void>(`/developer/prompts/${encodeURIComponent(promptId)}`, { method: "DELETE" });
}

export function previewPrompt(template: string) {
  return request<{ preview: string }>("/developer/prompts/preview", {
    method: "POST",
    body: JSON.stringify({ template }),
  });
}
