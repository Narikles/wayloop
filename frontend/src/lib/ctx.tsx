import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { CircleCheck, CircleAlert } from "lucide-react";
import type { Api } from "../api/client";
import { ApiError } from "../api/client";
import type { Me } from "../api/types";

declare const __DEMO__: boolean;
export const IS_DEMO = typeof __DEMO__ !== "undefined" && __DEMO__;

/** Enregistrement de fichier proposé par la visionneuse claude.ai (démo publiée) ; null ailleurs. */
type ViewerDownloads = { save(req: { filename: string; data: string | Blob }): Promise<{ status: string }> };
export async function viewerDownloads(): Promise<ViewerDownloads | null> {
  const claude = (window as unknown as { claude?: { use?: (name: string) => Promise<unknown> } }).claude;
  if (!IS_DEMO || typeof claude?.use !== "function") return null;
  try {
    return ((await claude.use("downloads")) as ViewerDownloads | null) ?? null;
  } catch {
    return null;
  }
}

export const ApiCtx = createContext<Api>(null as unknown as Api);
export const useApi = () => useContext(ApiCtx);

type Session = { me: Me | null; reload: () => Promise<void>; version: number; touch: () => void };
export const SessionCtx = createContext<Session>({ me: null, reload: async () => {}, version: 0, touch: () => {} });
export const useSession = () => useContext(SessionCtx);
export const useIsPremium = () => useSession().me?.plan.id !== "free";
export const useHas = (feature: string) => !!useSession().me?.plan.features.includes(feature);

/** Thème de l'interface : clair par défaut, sombre au choix (Paramètres > Apparence). */
export type Theme = "light" | "dark";
const THEME_KEY = "wayloop.theme";
export function storedTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}
export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme;
  document.querySelector('meta[name="theme-color"]')?.setAttribute("content", theme === "dark" ? "#111723" : "#ffffff");
  try {
    localStorage.setItem(THEME_KEY, theme);
  } catch {
    /* stockage indisponible : le thème vaut pour la session */
  }
}

type Notify = (msg: string, tone?: "ok" | "bad") => void;
const ToastCtx = createContext<Notify>(() => {});
export const useToast = () => useContext(ToastCtx);

type Upgrade = (reason?: string) => void;
const UpgradeCtx = createContext<Upgrade>(() => {});
export const useUpgrade = () => useContext(UpgradeCtx);

export function Providers({ children, upgradeModal }: { children: ReactNode; upgradeModal: (reason: string | null, close: () => void) => ReactNode }) {
  const [toast, setToast] = useState<{ msg: string; tone: "ok" | "bad" } | null>(null);
  const [upgrade, setUpgrade] = useState<string | null | false>(false);
  const timer = useRef<number | undefined>(undefined);
  const notify = useCallback<Notify>((msg, tone = "ok") => {
    setToast({ msg, tone });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setToast(null), 3600);
  }, []);
  return (
    <ToastCtx.Provider value={notify}>
      <UpgradeCtx.Provider value={(r) => setUpgrade(r ?? null)}>
        {children}
        {upgrade !== false && upgradeModal(upgrade, () => setUpgrade(false))}
        {toast && (
          <div className="toast" role="status">
            {toast.tone === "ok" ? <CircleCheck size={18} /> : <CircleAlert size={18} />} {toast.msg}
          </div>
        )}
      </UpgradeCtx.Provider>
    </ToastCtx.Provider>
  );
}

/** Exécute une action ; une erreur 402 (offre) ouvre la fenêtre des offres, les autres un message. */
export function useAction() {
  const notify = useToast();
  const upgrade = useUpgrade();
  return useCallback(
    async <T,>(fn: () => Promise<T>, ok?: string): Promise<T | undefined> => {
      try {
        const r = await fn();
        if (ok) notify(ok);
        return r;
      } catch (e) {
        if (e instanceof ApiError && (e.status === 402 || e.upgrade)) upgrade(e.message);
        else notify((e as Error).message, "bad");
        return undefined;
      }
    },
    [notify, upgrade],
  );
}

/** Charge une ressource ; renvoie [données, erreur, recharger, setter]. */
export function useLoad<T>(fn: () => Promise<T>, deps: unknown[]): [T | null, string | null, () => Promise<void>, (v: T) => void] {
  const [data, setData] = useState<T | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const reload = useCallback(async () => {
    try {
      setErr(null);
      setData(await fn());
    } catch (e) {
      setErr((e as Error).message);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps);
  useEffect(() => {
    void reload();
  }, [reload]);
  return [data, err, reload, setData];
}

export function useDebounced<T>(value: T, ms = 250): T {
  const [v, setV] = useState(value);
  useEffect(() => {
    const t = window.setTimeout(() => setV(value), ms);
    return () => window.clearTimeout(t);
  }, [value, ms]);
  return v;
}
