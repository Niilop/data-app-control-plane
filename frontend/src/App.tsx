import { useState } from "react";
import {
  Link,
  NavLink,
  Navigate,
  Outlet,
  Route,
  Routes,
  useLocation,
} from "react-router";
import {
  Activity,
  Boxes,
  ChevronRight,
  Layers3,
  LogOut,
  Menu,
  Network,
  Users,
} from "lucide-react";
import { api } from "./api";
import {
  ActionForm,
  Badge,
  ErrorNotice,
  Field,
  Loading,
  text,
} from "./components";
import { DataProvider, useSession } from "./state";
import type { User } from "./types";
import { Applications, ApplicationDetail } from "./pages/applications";
import {
  Teams,
  Environments,
  ActivityPage,
  Account,
} from "./pages/administration";

export function Brand() {
  return (
    <div className="brand">
      <span className="brand-mark">
        <Layers3 size={22} />
      </span>
      <span>
        Control plane<small>Data applications</small>
      </span>
    </div>
  );
}
function Login() {
  const { setUser, message } = useSession();
  const [register, setRegister] = useState(false);
  const [notice, setNotice] = useState("");
  return (
    <main className="login-page">
      <div className="login-brand">
        <Brand />
        <Badge tone="blue">Local workspace</Badge>
      </div>
      <div className="login-card">
        <span className="eyebrow">YOUR WORKSPACE</span>
        <h1>{register ? "Create your account" : "Welcome back"}</h1>
        <p>
          {register
            ? "Join your team’s application workspace."
            : "Sign in to manage your data applications."}
        </p>
        {(notice || message) && (
          <div className="alert" role="status">
            {notice || message}
          </div>
        )}
        <ActionForm
          key={String(register)}
          submitLabel={register ? "Create account" : "Sign in"}
          submit={async (data) => {
            if (register) {
              await api("/auth/register", {
                method: "POST",
                body: {
                  email: text(data, "email"),
                  username: text(data, "username"),
                  password: String(data.get("password")),
                },
              });
              setRegister(false);
              setNotice("Account created. Sign in to continue.");
            } else {
              const user = await api<User>("/auth/session", {
                method: "POST",
                body: new URLSearchParams({
                  username: text(data, "username"),
                  password: String(data.get("password")),
                }),
              });
              setUser(user);
            }
          }}
        >
          {register && (
            <Field label="Email">
              <input
                name="email"
                type="email"
                autoComplete="email"
                required
                maxLength={255}
              />
            </Field>
          )}
          <Field label={register ? "Username" : "Email or username"}>
            <input
              name="username"
              autoComplete="username"
              required
              maxLength={255}
            />
          </Field>
          <Field label="Password">
            <input
              name="password"
              type="password"
              autoComplete={register ? "new-password" : "current-password"}
              required
            />
          </Field>
        </ActionForm>
        <p className="login-switch">
          {register ? "Already have an account?" : "New to the workspace?"}{" "}
          <button
            className="text-button"
            onClick={() => {
              setRegister(!register);
              setNotice("");
            }}
          >
            {register ? "Sign in" : "Create account"}
          </button>
        </p>
      </div>
      <p className="login-foot">
        Your applications. Clear ownership. A complete history.
      </p>
    </main>
  );
}
function Shell() {
  const { user, setUser } = useSession();
  const [menu, setMenu] = useState(false);
  const [error, setError] = useState<Error | null>(null);
  const location = useLocation();
  if (!user) return null;
  const section = location.pathname.split("/")[1] || "applications";
  return (
    <DataProvider>
      <a className="skip-link" href="#main-content">
        Skip to content
      </a>
      <div className={`app-shell ${menu ? "menu-open" : ""}`}>
        <aside className="sidebar">
          <Link
            className="brand-link"
            to="/applications"
            onClick={() => setMenu(false)}
          >
            <Brand />
          </Link>
          <p className="nav-label">WORKSPACE</p>
          <nav aria-label="Main navigation">
            {[
              ["/applications", "Applications", Boxes],
              ["/teams", "Teams", Users],
              ["/environments", "Environments", Network],
              ...(user.is_platform_admin
                ? [["/activity", "Activity", Activity] as const]
                : []),
            ].map(([to, name, Icon]) => (
              <NavLink
                key={String(to)}
                to={String(to)}
                onClick={() => setMenu(false)}
              >
                <Icon size={18} />
                <span>{String(name)}</span>
              </NavLink>
            ))}
          </nav>
          <div className="sidebar-bottom">
            <div className="workspace-note">
              <span className="live-dot" />
              Local development<small>Simulated execution</small>
            </div>
            <NavLink
              className="profile-link"
              to="/account"
              onClick={() => setMenu(false)}
            >
              <span className="avatar">
                {user.username.slice(0, 2).toUpperCase()}
              </span>
              <span>
                {user.username}
                <small>
                  {user.is_platform_admin
                    ? "Platform administrator"
                    : "Workspace member"}
                </small>
              </span>
              <ChevronRight size={16} />
            </NavLink>
          </div>
        </aside>
        <div className="main-column">
          <header className="topbar">
            <div className="breadcrumbs">
              <button
                className="icon-button mobile-menu"
                aria-label="Toggle navigation"
                aria-expanded={menu}
                onClick={() => setMenu(!menu)}
              >
                <Menu size={20} />
              </button>
              <span>Workspace</span>
              <ChevronRight size={14} />
              <strong>
                {section.charAt(0).toUpperCase() + section.slice(1)}
              </strong>
            </div>
            <div className="actions">
              <Badge tone="blue">
                <span className="live-dot" />
                Simulated
              </Badge>
              <button
                className="icon-button"
                aria-label="Sign out"
                title="Sign out"
                onClick={async () => {
                  try {
                    await api("/auth/session", { method: "DELETE" });
                    setUser(null);
                  } catch (e) {
                    setError(e as Error);
                  }
                }}
              >
                <LogOut size={18} />
              </button>
            </div>
          </header>
          <main id="main-content" tabIndex={-1}>
            <ErrorNotice error={error} />
            <Outlet />
          </main>
          <footer>
            Data Application Control Plane
            <span>Local workspace · Simulation only</span>
          </footer>
        </div>
      </div>
    </DataProvider>
  );
}
export default function App() {
  const { user, loading } = useSession();
  if (loading) return <Loading />;
  if (!user) return <Login />;
  return (
    <Routes>
      <Route element={<Shell key={user.id} />}>
        <Route path="/applications" element={<Applications />} />
        <Route path="/applications/:id" element={<ApplicationDetail />} />
        <Route path="/teams" element={<Teams />} />
        <Route path="/environments" element={<Environments />} />
        <Route
          path="/activity"
          element={
            user.is_platform_admin ? (
              <ActivityPage />
            ) : (
              <Navigate to="/applications" replace />
            )
          }
        />
        <Route path="/account" element={<Account />} />
        <Route path="*" element={<Navigate to="/applications" replace />} />
      </Route>
    </Routes>
  );
}
