import { useEffect, useState, type ReactNode } from "react";
import { Link, NavLink, Navigate, useLocation, useNavigate } from "react-router-dom";
import { BarChart3, Briefcase, CalendarDays, Check, Home, LogOut, Menu, Plus, Settings, Sparkles } from "lucide-react";
import { IS_DEMO, useApi, useLoad, useSession } from "../lib/ctx";
import { fmtEuro, initials, isClosed } from "../lib/format";
import { Logo, Modal } from "../ui/kit";

export const PRO_POINTS = [
  "Plusieurs recrutements en même temps",
  "Remerciement automatique des refusés, relance des non-répondants, récapitulatif chaque lundi",
  "Historique complet de chaque candidat",
  "Créneaux d'entretien en ligne et export des candidatures",
];

export function UpgradeModal({ reason, onClose }: { reason: string | null; onClose: () => void }) {
  const nav = useNavigate();
  const api = useApi();
  const [p] = useLoad(() => api.pricing(), []);
  const team = !!reason && /Agence/.test(reason);
  return (
    <Modal title={team ? "WayLoop Agence" : "WayLoop Pro"} sub={reason || undefined} onClose={onClose}
      foot={<><button className="btn" onClick={onClose}>Plus tard</button>
        <button className="btn primary" onClick={() => { onClose(); nav("/parametres/abonnement"); }}><Sparkles size={16} /> Voir les offres</button></>}>
      <div className="stack">
        {(team ? ["Tout ce que comprend Pro", "Plusieurs utilisateurs dans le même espace", "Support prioritaire"] : PRO_POINTS)
          .map((f) => <div className="feat" key={f}><Check size={16} color="var(--ok)" /> {f}</div>)}
        {p && <p className="muted small">{team
          ? `${fmtEuro(p.agency.monthly)} HT par mois sans engagement, ou ${fmtEuro(p.agency.yearly_per_month)} HT par mois en annuel.`
          : `${fmtEuro(p.premium.monthly)} HT par mois sans engagement, ou ${fmtEuro(p.premium.yearly_per_month)} HT par mois en annuel.`}</p>}
      </div>
    </Modal>
  );
}

function PlanCard() {
  const { me, version } = useSession();
  const api = useApi();
  const loc = useLocation();
  const [b] = useLoad(() => api.billing(), [loc.pathname, version]);
  if (!me || !b || b.plan === "premium") return null;
  const used = b.usage.active_recruitments;
  const limit = b.usage.limit || 1;
  return (
    <div className="plan-card">
      <div className="row between"><span className="strong small">Offre Gratuit</span><span className="xs muted tnum">{used}/{limit} en cours</span></div>
      <div className="meter"><span style={{ width: `${Math.min(100, (used / limit) * 100)}%` }} /></div>
      <Link to="/parametres/abonnement" className="btn sm"><Sparkles size={14} /> Passer à Pro</Link>
    </div>
  );
}

export default function AppShell({ children }: { children: ReactNode }) {
  const { me, version } = useSession();
  const api = useApi();
  const loc = useLocation();
  const [open, setOpen] = useState(false);
  const [recs] = useLoad(() => (me ? api.listRecruitments() : Promise.resolve([])), [loc.pathname, me?.id, version]);
  useEffect(() => {
    setOpen(false);
  }, [loc.pathname]);
  if (!me) return <Navigate to="/connexion" replace />;
  const todo = (recs || []).filter((r) => (r.pending || r.new_applications) && !isClosed(r.state)).length;
  const item = (to: string, icon: ReactNode, label: string, count?: number, end?: boolean) => (
    <NavLink to={to} end={end} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`}>
      {icon}<span>{label}</span>{count ? <span className="count tnum" aria-label={`${count} à faire`}>{count}</span> : null}
    </NavLink>
  );
  return (
    <>
      {IS_DEMO && <div className="demo-band">Démo interactive · entreprise et candidats fictifs · aucune donnée n'est envoyée</div>}
      <div className="shell">
        {open && <div className="scrim" onClick={() => setOpen(false)} />}
        <aside className={`sidebar ${open ? "open" : ""}`}>
          <Link to="/" className="logo"><Logo /> WayLoop</Link>
          <Link to="/recrutements/nouveau" className="btn primary" style={{ marginBottom: 10 }}><Plus size={16} /> Nouveau recrutement</Link>
          <nav aria-label="Navigation principale" style={{ display: "contents" }}>
            {item("/", <Home size={18} />, "Accueil", todo, true)}
            {item("/recrutements", <Briefcase size={18} />, "Recrutements")}
            {item("/entretiens", <CalendarDays size={18} />, "Entretiens")}
            {item("/indicateurs", <BarChart3 size={18} />, "Indicateurs")}
            {item("/parametres", <Settings size={18} />, "Paramètres")}
          </nav>
          <div className="sidebar-foot">
            <PlanCard />
            <div className="user-chip">
              <span className="avatar">{initials(me.name || me.email)}</span>
              <div className="stack sm" style={{ gap: 0, minWidth: 0, flex: 1 }}>
                <span className="strong small" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{me.name || me.email}</span>
                <span className="xs muted" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }}>{me.company?.name}</span>
              </div>
              {!IS_DEMO && <LogoutButton />}
            </div>
          </div>
        </aside>
        <div className="main">
          <div className="topbar">
            <button className="btn ghost icon" onClick={() => setOpen(true)} aria-label="Menu"><Menu size={20} /></button>
            <Link to="/" className="logo" style={{ padding: 0 }}><Logo size={26} /> WayLoop</Link>
          </div>
          {children}
        </div>
      </div>
    </>
  );
}

function LogoutButton() {
  const api = useApi();
  const { reload } = useSession();
  return (
    <button className="btn ghost sm icon" title="Se déconnecter" aria-label="Se déconnecter" onClick={async () => { await api.logout(); await reload(); }}>
      <LogOut size={16} />
    </button>
  );
}
