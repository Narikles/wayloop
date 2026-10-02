import { useCallback, useEffect, useState, type ReactNode } from "react";
import { BrowserRouter, MemoryRouter, Navigate, Route, Routes, useLocation, useNavigate, useParams } from "react-router-dom";
import type { Api } from "./api/client";
import type { Me } from "./api/types";
import AppShell, { UpgradeModal } from "./layout/AppShell";
import { ApiCtx, applyTheme, IS_DEMO, Providers, SessionCtx, useApi, useSession } from "./lib/ctx";
import Agenda from "./pages/Agenda";
import Dashboard from "./pages/Dashboard";
import Login from "./pages/Login";
import MetricsPage from "./pages/Metrics";
import NewRecruitment from "./pages/NewRecruitment";
import Recruitment from "./pages/Recruitment";
import Recruitments from "./pages/Recruitments";
import SettingsPage from "./pages/Settings";
import Booking from "./pages/public/Booking";
import CandidatePage from "./pages/public/CandidatePage";
import OfferPage from "./pages/public/OfferPage";
import Privacy from "./pages/public/Privacy";
import { Notice, Spinner } from "./ui/kit";

function TokenExchange() {
  const { token } = useParams();
  const api = useApi();
  const { reload } = useSession();
  const nav = useNavigate();
  const loc = useLocation();
  const [err, setErr] = useState<string | null>(null);
  useEffect(() => {
    (async () => {
      try {
        const r = await api.exchange(token || "", new URLSearchParams(loc.search).get("next"));
        await reload();
        nav(r.redirect, { replace: true });
      } catch (e) {
        setErr((e as Error).message);
      }
    })();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [token]);
  return (
    <main className="content narrow" style={{ paddingTop: 80 }}>
      {err ? <Notice tone="bad" title="Lien expiré">{err} <a href="/connexion">Recevoir un nouveau lien</a></Notice> : <Spinner label="Connexion…" />}
    </main>
  );
}

/** Chaque nouvelle page s'ouvre en haut. */
function ScrollToTop() {
  const { pathname } = useLocation();
  useEffect(() => window.scrollTo(0, 0), [pathname]);
  return null;
}

function ToBilling() {
  const loc = useLocation();
  return <Navigate to={`/parametres/abonnement${loc.search}`} replace />;
}

function Routed() {
  const priv = (el: ReactNode) => <AppShell>{el}</AppShell>;
  return (
    <Routes>
      <Route path="/connexion" element={<Login />} />
      <Route path="/connexion/:token" element={<TokenExchange />} />
      <Route path="/p/:token" element={<TokenExchange />} />
      <Route path="/offres/:token" element={<OfferPage />} />
      <Route path="/rdv/:token" element={<Booking />} />
      <Route path="/candidat/:token" element={<CandidatePage />} />
      <Route path="/confidentialite/:slug" element={<Privacy />} />
      <Route path="/" element={priv(<Dashboard />)} />
      <Route path="/recrutements" element={priv(<Recruitments />)} />
      <Route path="/recrutements/nouveau" element={priv(<NewRecruitment />)} />
      <Route path="/recrutements/:id" element={priv(<Recruitment />)} />
      <Route path="/recrutements/:id/:page" element={priv(<Recruitment />)} />
      <Route path="/entretiens" element={priv(<Agenda />)} />
      <Route path="/indicateurs" element={priv(<MetricsPage />)} />
      <Route path="/parametres" element={priv(<SettingsPage />)} />
      <Route path="/parametres/:section" element={priv(<SettingsPage />)} />
      <Route path="/abonnement" element={<ToBilling />} />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export default function App({ api }: { api: Api }) {
  const [me, setMe] = useState<Me | null>(null);
  const [ready, setReady] = useState(false);
  const reload = useCallback(async (force = true) => {
    const publicPage = /^\/(offres|rdv|candidat|confidentialite)\//.test(window.location.pathname);
    if (!force && publicPage && !api.demo) {
      setReady(true);
      return;
    }
    try {
      const m = await api.me();
      setMe(m);
      applyTheme(m.theme === "dark" ? "dark" : "light");
    } catch {
      setMe(null);
    } finally {
      setReady(true);
    }
  }, [api]);
  useEffect(() => {
    void reload(false);
  }, [reload]);
  const [version, setVersion] = useState(0);
  const touch = useCallback(() => setVersion((v) => v + 1), []);
  if (!ready) return <main className="content"><Spinner /></main>;
  const Router = IS_DEMO ? MemoryRouter : BrowserRouter;
  return (
    <ApiCtx.Provider value={api}>
      <SessionCtx.Provider value={{ me, reload: async () => { await reload(true); touch(); }, version, touch }}>
        <Router>
          <Providers upgradeModal={(reason, close) => <UpgradeModal reason={reason} onClose={close} />}>
            <ScrollToTop />
            <Routed />
          </Providers>
        </Router>
      </SessionCtx.Provider>
    </ApiCtx.Provider>
  );
}
