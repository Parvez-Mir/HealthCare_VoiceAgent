import {
  createContext,
  type FormEvent,
  type PropsWithChildren,
  useContext,
  useMemo,
  useState,
} from "react";
import { ApiError, login, logout } from "./api";

const SESSION_KEY = "careline-dashboard-token";
const DEVELOPMENT_USER = {
  email: "admin@careline.dev",
  password: "careline-dev",
  name: "Careline operator",
};

type AuthContextValue = {
  isAuthenticated: boolean;
  userName: string;
  signIn: (email: string, password: string) => Promise<boolean>;
  signOut: () => Promise<void>;
};

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: PropsWithChildren) {
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => Boolean(window.sessionStorage.getItem(SESSION_KEY)),
  );

  const value = useMemo<AuthContextValue>(
    () => ({
      isAuthenticated,
      userName: DEVELOPMENT_USER.name,
      signIn: async (email, password) => {
        try {
          await login(email, password);
          setIsAuthenticated(true);
          return true;
        } catch (error) {
          if (!(error instanceof ApiError)) throw error;
          return false;
        }
      },
      signOut: async () => {
        await logout();
        setIsAuthenticated(false);
      },
    }),
    [isAuthenticated],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}

export function LoginPage() {
  const { signIn } = useAuth();
  const [email, setEmail] = useState(DEVELOPMENT_USER.email);
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError("");
    setIsSubmitting(true);
    try {
      const valid = await signIn(email.trim(), password);
      if (!valid) setError("That development account could not be verified.");
    } catch {
      setError("The backend is unavailable. Start FastAPI and try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <main className="auth-page">
      <section className="auth-card" aria-labelledby="login-title">
        <div className="brand-mark brand-mark-large" aria-hidden="true">
          <span>c</span>
        </div>
        <p className="eyebrow">Careline operations</p>
        <h1 id="login-title">Welcome back</h1>
        <p className="auth-intro">Sign in to manage patient care workflows and voice-agent settings.</p>
        <form className="stack-form" onSubmit={handleSubmit}>
          <label>
            Email
            <input
              type="email"
              value={email}
              onChange={(event) => setEmail(event.target.value)}
              autoComplete="username"
              required
            />
          </label>
          <label>
            Password
            <input
              type="password"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              autoComplete="current-password"
              required
            />
          </label>
          {error && <p className="form-error" role="alert">{error}</p>}
          <button className="button button-primary button-full" disabled={isSubmitting} type="submit">
            {isSubmitting ? "Connecting…" : "Sign in"}
          </button>
        </form>
        <p className="auth-note">
          Development access only. Production authentication will be added before deployment.
        </p>
      </section>
    </main>
  );
}
