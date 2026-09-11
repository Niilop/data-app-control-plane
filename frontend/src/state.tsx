import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { api } from "./api";
import type { Page, User } from "./types";

const Session = createContext<{
  user: User | null;
  loading: boolean;
  message: string;
  setUser: (user: User | null) => void;
}>({ user: null, loading: true, message: "", setUser: () => {} });
export function SessionProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  useEffect(() => {
    const controller = new AbortController();
    api<User>("/auth/me", { signal: controller.signal })
      .then((next) => {
        if (!controller.signal.aborted) setUser(next);
      })
      .catch((error) => {
        if (error.status !== 401 && error.name !== "AbortError")
          setMessage(error.message);
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    const expired = () => {
      setUser(null);
      setMessage("Your session has ended. Sign in to continue.");
    };
    window.addEventListener("session-expired", expired);
    return () => {
      controller.abort();
      window.removeEventListener("session-expired", expired);
    };
  }, []);
  return (
    <Session.Provider
      value={{
        user,
        loading,
        message,
        setUser: (next) => {
          setUser(next);
          setMessage("");
        },
      }}
    >
      {children}
    </Session.Provider>
  );
}
export const useSession = () => useContext(Session);

const Refresh = createContext<{
  version: number;
  refresh: () => void;
  notify: (message: string) => void;
  commandKey: (scope: string) => string;
}>({
  version: 0,
  refresh: () => {},
  notify: () => {},
  commandKey: () => {
    throw new Error("Missing workspace context");
  },
});
export function DataProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const [notice, setNotice] = useState("");
  const commandKeys = useRef(new Map<string, string>());
  const commandKey = (scope: string) => {
    if (!commandKeys.current.has(scope))
      commandKeys.current.set(scope, crypto.randomUUID());
    return commandKeys.current.get(scope)!;
  };
  const refresh = useCallback(() => setVersion((value) => value + 1), []);
  return (
    <Refresh.Provider
      value={{ version, refresh, notify: setNotice, commandKey }}
    >
      {notice && (
        <div className="toast" role="status">
          {notice}
          <button
            aria-label="Dismiss notification"
            onClick={() => setNotice("")}
          >
            ×
          </button>
        </div>
      )}
      {children}
    </Refresh.Provider>
  );
}
export const useData = () => useContext(Refresh);

export function useResource<T>(path: string | null) {
  const { version } = useData();
  const [state, setState] = useState<{
    path: string | null;
    version: number;
    data: T | null;
    loading: boolean;
    error: Error | null;
  }>({ path, version, data: null, loading: true, error: null });
  useEffect(() => {
    if (!path) return;
    const controller = new AbortController();
    setState((previous) => ({
      path,
      version,
      data: previous.path === path ? previous.data : null,
      loading: true,
      error: null,
    }));
    api<T>(path, { signal: controller.signal })
      .then((data) => {
        if (!controller.signal.aborted)
          setState({ path, version, data, loading: false, error: null });
      })
      .catch((error) => {
        if (!controller.signal.aborted)
          setState({ path, version, data: null, loading: false, error });
      });
    return () => controller.abort();
  }, [path, version]);
  return state.path === path
    ? {
        ...state,
        loading: state.loading || state.version !== version,
        error: state.version === version ? state.error : null,
      }
    : { ...state, data: null, loading: true, error: null };
}

export function usePage<T>(path: string) {
  const [cursors, setCursors] = useState<(string | null)[]>([null]);
  const cursor = cursors[cursors.length - 1];
  const resource = useResource<Page<T>>(
    `${path}${path.includes("?") ? "&" : "?"}limit=20${cursor ? `&cursor=${encodeURIComponent(cursor)}` : ""}`,
  );
  return {
    ...resource,
    page: cursors.length,
    next: () => {
      if (resource.data?.next_cursor)
        setCursors([...cursors, resource.data.next_cursor]);
    },
    previous: () => setCursors(cursors.slice(0, -1)),
    first: () => setCursors([null]),
  };
}
