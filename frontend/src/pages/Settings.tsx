import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Check, CreditCard, ExternalLink, Lock, Trash2, UserPlus } from "lucide-react";
import type { Automations, Billing, CompanyRef, PlanOffer } from "../api/types";
import { applyTheme, IS_DEMO, useAction, useApi, useHas, useLoad, useSession, useToast, useUpgrade, type Theme } from "../lib/ctx";
import { fmtDate, fmtEuro } from "../lib/format";
import { Combobox } from "../ui/Combobox";
import { Badge, Button, Card, ErrorBox, Field, Notice, PageHeader, Segmented, Spinner, Tabs } from "../ui/kit";

type Section = "entreprise" | "automatisations" | "equipe" | "apparence" | "abonnement";
const SECTIONS: { id: Section; label: string }[] = [
  { id: "entreprise", label: "Entreprise" }, { id: "automatisations", label: "Automatisations" }, { id: "equipe", label: "Équipe" },
  { id: "apparence", label: "Apparence" }, { id: "abonnement", label: "Abonnement" },
];

export default function SettingsPage() {
  const { section = "entreprise" } = useParams();
  const nav = useNavigate();
  const s = (SECTIONS.some((x) => x.id === section) ? section : "entreprise") as Section;
  return (
    <main className="content narrow">
      <PageHeader title="Paramètres" />
      <Tabs<Section> value={s} onChange={(v) => nav(v === "entreprise" ? "/parametres" : `/parametres/${v}`)} items={SECTIONS} />
      {s === "entreprise" && <CompanySection />}
      {s === "automatisations" && <AutomationsSection />}
      {s === "equipe" && <TeamSection />}
      {s === "apparence" && <AppearanceSection />}
      {s === "abonnement" && <BillingSection />}
    </main>
  );
}

function CompanySection() {
  const api = useApi();
  const { me, reload } = useSession();
  const c = me!.company!;
  const [f, setF] = useState({
    company_name: c.name, siren: c.siren || "", naf_code: c.naf_code || "", headcount_range: c.headcount_range || "",
    address: c.address || "", name: me!.name || "", phone: me!.phone || "",
  });
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  return (
    <Card foot={<Button variant="primary" done="Enregistré" onClick={async () => { await api.saveSettings(f); await reload(); }}>Enregistrer</Button>}>
      <Field label="Entreprise" hint={f.siren ? `SIREN ${f.siren}${f.headcount_range ? ` · ${f.headcount_range}` : ""}` : "Recherchez-la dans l'annuaire officiel des entreprises."}>
        <Combobox<CompanyRef> value={f.company_name} minChars={3} onChange={(v) => set("company_name", v)}
          onPick={(x) => setF({ ...f, company_name: x.name || x.display_name, siren: x.siren, naf_code: x.naf_code || "", headcount_range: x.headcount_range || "", address: f.address || x.address || "" })}
          search={async (q) => (await api.companySearch(q)).results}
          render={(x) => <><b>{x.display_name}</b><span className="xs muted">{x.address} · SIREN {x.siren}</span></>} footer="annuaire-entreprises.data.gouv.fr" />
      </Field>
      <Field label="Adresse" hint="Proposée par défaut comme lieu des entretiens."><input className="input" value={f.address} onChange={(e) => set("address", e.target.value)} /></Field>
      <div className="grid c2">
        <Field label="Votre nom"><input className="input" value={f.name} onChange={(e) => set("name", e.target.value)} /></Field>
        <Field label="Téléphone"><input className="input" type="tel" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
      </div>
      <span className="xs muted">Les notifications arrivent par e-mail à {me!.email}, avec un lien qui ouvre directement la bonne page.</span>
    </Card>
  );
}

function AutomationsSection() {
  const api = useApi();
  const run = useAction();
  const upgrade = useUpgrade();
  const [a, err, , setA] = useLoad(() => api.automations(), []);
  if (err) return <ErrorBox msg={err} />;
  if (!a) return <Spinner />;
  const save = async (patch: Partial<Automations>) => {
    const r = await run(() => api.saveAutomations(patch), "Enregistré");
    if (r) setA(r);
  };
  const Toggle = ({ k, paid }: { k: "auto_reject" | "relance" | "weekly_recap" | "notify_new"; paid?: boolean }) => {
    const locked = paid && !a.available;
    return locked
      ? <button className="btn sm" onClick={() => upgrade("Les automatisations sont incluses dans l'offre Pro.")}><Lock size={14} /> Pro</button>
      : <label className="switch"><input type="checkbox" checked={!!a[k]} onChange={(e) => save({ [k]: e.target.checked })} aria-label="Activer" /></label>;
  };
  return (
    <div className="stack lg">
      {!a.available && (
        <Notice tone="brand" title="Automatisations incluses dans l'offre Pro"
          actions={<button className="btn sm primary" onClick={() => upgrade("Les automatisations sont incluses dans l'offre Pro.")}>Voir l'offre Pro</button>}>
          Avec l'offre Gratuit, vous envoyez vous-même les réponses (le message est prêt) et vous suivez les relances dans le pipeline.
        </Notice>
      )}
      <Card title="Ce que WayLoop fait pour vous" sub="Rien n'est décidé à votre place : ces envois suivent vos choix, ou rappellent ce qui attend.">
        <div className="settings-row">
          <span className="grow"><span className="strong">Remerciement automatique des refusés</span>
            <span className="small muted">Quand vous classez une candidature « Refusé », un message courtois part tout seul {a.delay_minutes >= 60 ? `${Math.round(a.delay_minutes / 60)} h` : `${a.delay_minutes} min`} plus tard. D'ici là, vous pouvez annuler.</span></span>
          <Toggle k="auto_reject" paid />
        </div>
        <div className="settings-row">
          <span className="grow"><span className="strong">Relance des non-répondants</span>
            <span className="small muted">Une seule relance : candidats reçus par e-mail ou ajoutés à la main qui n'ont pas répondu aux questions du poste, invitations en entretien restées sans date.</span>
            {a.available && a.relance && (
              <span className="row small" style={{ gap: 6, marginTop: 6 }}>Après
                <select className="select" style={{ width: 80, height: 32 }} value={a.relance_days} aria-label="Délai de relance" onChange={(e) => save({ relance_days: Number(e.target.value) })}>
                  {[2, 3, 4, 5, 7, 10, 14].map((d) => <option key={d} value={d}>{d}</option>)}
                </select> jours</span>
            )}</span>
          <Toggle k="relance" paid />
        </div>
        <div className="settings-row">
          <span className="grow"><span className="strong">Récapitulatif chaque lundi</span>
            <span className="small muted">Par e-mail, pour vous et votre équipe : candidatures reçues dans la semaine (par provenance), présélectionnées, entretiens prévus, ce qui attend une réponse.</span></span>
          <Toggle k="weekly_recap" paid />
        </div>
        <div className="settings-row">
          <span className="grow"><span className="strong">Alerte à chaque nouvelle candidature</span>
            <span className="small muted">Un e-mail avec le lien direct vers le pipeline. Incluse dans toutes les offres.</span></span>
          <Toggle k="notify_new" />
        </div>
      </Card>
    </div>
  );
}

function TeamSection() {
  const api = useApi();
  const run = useAction();
  const upgrade = useUpgrade();
  const { me } = useSession();
  const hasTeam = useHas("team");
  const [team, err, , setTeam] = useLoad(() => api.team(), []);
  const [f, setF] = useState({ name: "", email: "" });
  if (err) return <ErrorBox msg={err} />;
  if (!team) return <Spinner />;
  return (
    <div className="stack lg">
      {!hasTeam && (
        <Notice tone="brand" title="Plusieurs utilisateurs : offre Agence"
          actions={<button className="btn sm primary" onClick={() => upgrade("Plusieurs utilisateurs : inclus dans l'offre Agence.")}>Voir l'offre Agence</button>}>
          Invitez un associé, un manager ou votre cabinet : chacun se connecte avec son adresse et suit les mêmes recrutements.
        </Notice>
      )}
      <Card title="Membres" flush>
        <ul className="todo-list">
          {team.map((m) => (
            <li key={m.id}>
              <span className="avatar">{(m.name || m.email).slice(0, 1).toUpperCase()}</span>
              <div className="grow"><b>{m.name || m.email}{m.me ? " (vous)" : ""}</b><span className="xs muted">{m.email} · {m.role === "owner" ? "titulaire du compte" : "membre"}</span></div>
              {me?.role === "owner" && m.role !== "owner" && (
                <Button size="sm" variant="ghost" icon={<Trash2 size={14} />} onClick={async () => {
                  const r = await run(() => api.removeMember(m.id), "Membre retiré");
                  if (r) setTeam(r);
                }}>Retirer</Button>
              )}
            </li>
          ))}
        </ul>
      </Card>
      {hasTeam && (
        <Card title="Inviter un membre" sub="Il reçoit un lien de connexion par e-mail, sans mot de passe."
          foot={<Button variant="primary" icon={<UserPlus size={16} />} disabled={f.name.trim().length < 2 || !f.email.includes("@")} onClick={async () => {
            const r = await run(() => api.inviteMember(f.name.trim(), f.email.trim()), "Invitation envoyée");
            if (r) { setTeam(r); setF({ name: "", email: "" }); }
          }}>Inviter</Button>}>
          <div className="grid c2">
            <Field label="Nom" htmlFor="tm-name"><input id="tm-name" className="input" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} /></Field>
            <Field label="E-mail" htmlFor="tm-email"><input id="tm-email" className="input" type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
          </div>
        </Card>
      )}
    </div>
  );
}

function AppearanceSection() {
  const api = useApi();
  const run = useAction();
  const { me, reload } = useSession();
  const [theme, setTheme] = useState<Theme>(me?.theme === "dark" ? "dark" : "light");
  const choose = async (t: Theme) => {
    setTheme(t);
    applyTheme(t);
    await run(() => api.saveSettings({ theme: t }));
    await reload();
  };
  return (
    <Card title="Thème">
      <div className="theme-choice" role="radiogroup" aria-label="Thème">
        {(["light", "dark"] as const).map((t) => (
          <button key={t} type="button" role="radio" aria-checked={theme === t} className={theme === t ? "on" : ""} onClick={() => choose(t)}>
            <span className={`sw ${t}`} aria-hidden><span /><span /></span>
            <span className="row between">{t === "light" ? "Clair" : "Sombre"}{theme === t && <Check size={16} color="var(--brand)" />}</span>
          </button>
        ))}
      </div>
    </Card>
  );
}

const PLAN_POINTS: Record<string, string[]> = {
  free: ["Un recrutement à la fois", "Offre rédigée avec l'assistant, conforme d'office", "Diffusion : Google pour l'emploi + textes prêts pour LinkedIn, Indeed, France Travail",
    "Toutes les candidatures au même endroit, pipeline, notes", "Entretiens, notes, décision, réponse à chaque candidat", "Historique des 30 derniers jours"],
  premium: ["Recrutements illimités", "Remerciement automatique des refusés", "Relance des non-répondants", "Récapitulatif chaque lundi",
    "Historique complet", "Créneaux d'entretien en ligne, export Excel / Google Sheets"],
  agency: ["Tout ce que comprend Pro", "Plusieurs utilisateurs", "Support prioritaire"],
};

function BillingSection() {
  const api = useApi();
  const run = useAction();
  const loc = useLocation();
  const notify = useToast();
  const { reload: reloadMe } = useSession();
  const [b, err, reload] = useLoad(() => api.billing(), []);
  const [interval, setInterval] = useState<"month" | "year">("year");
  const status = new URLSearchParams(loc.search).get("statut");
  if (err) return <ErrorBox msg={err} />;
  if (!b) return <Spinner />;
  const paid = b.plan !== "free";
  const checkout = async (plan: "premium" | "agency") => {
    const r = await run(() => api.checkout(interval, plan));
    if (!r) return;
    if (r.url.startsWith("http") && !r.url.includes("/abonnement")) window.location.href = r.url;
    else {
      await reload();
      await reloadMe();
      notify(`Offre ${b.plans.find((p) => p.id === plan)?.name || ""} activée`);
    }
  };
  return (
    <div className="stack lg">
      {status === "ok" && <Notice tone="ok" title={`Votre offre ${b.plan_name} est active.`} />}
      {status === "annule" && <Notice title="Paiement annulé">Votre offre n'a pas changé.</Notice>}
      {paid && (
        <Card title={`Offre ${b.plan_name}`} sub={`${b.interval === "year" ? "Annuel" : "Mensuel"}${b.period_end ? ` · prochaine échéance le ${fmtDate(b.period_end)}` : ""}`}
          actions={<Badge tone="ok" dot>Active</Badge>}>
          <div className="row">
            {b.billing_mode === "stripe" && b.has_customer && <Button icon={<ExternalLink size={14} />} onClick={async () => { const r = await run(() => api.portal()); if (r) window.location.href = r.url; }}>Factures, moyen de paiement, changement d'offre</Button>}
            {b.billing_mode === "demo" && <Button variant="ghost" onClick={async () => { await run(() => api.cancelDemo(), "Retour à l'offre Gratuit"); await reload(); await reloadMe(); }}>Revenir à l'offre Gratuit</Button>}
          </div>
        </Card>
      )}
      <div className="row between">
        <span className="small muted">Prix hors taxes, sans engagement en mensuel.</span>
        <Segmented label="Facturation" value={interval} onChange={setInterval} items={[{ id: "month", label: "Mensuel" }, { id: "year", label: "Annuel · −20 %" }]} />
      </div>
      {b.billing_mode === "disabled" && <Notice>Le paiement en ligne n'est pas encore ouvert. Contactez-nous.</Notice>}
      <div className="pricing three">
        {b.plans.map((p) => <PlanCard key={p.id} p={p} b={b} interval={interval} onChoose={checkout} />)}
      </div>
      <span className="xs muted">{IS_DEMO || b.billing_mode === "demo" ? "Démo : changement d'offre immédiat, sans paiement." : `Paiement sécurisé par Stripe${b.trial_days ? `, ${b.trial_days} jours d'essai` : ""} · résiliable à tout moment.`}</span>
    </div>
  );
}

function PlanCard({ p, b, interval, onChoose }: { p: PlanOffer; b: Billing; interval: "month" | "year"; onChoose: (plan: "premium" | "agency") => Promise<void> }) {
  const current = b.plan === p.id;
  const price = p.id === "free" ? 0 : interval === "year" ? p.yearly_per_month : p.monthly;
  return (
    <Card className={`plan ${current ? "current" : ""}`} title={<span className="row between" style={{ width: "100%" }}><h3>{p.name}</h3>{current && <Badge tone="brand">Votre offre</Badge>}</span>}>
      <div className="row" style={{ alignItems: "baseline", gap: 6 }}>
        <span className="price">{fmtEuro(price)}</span>
        <span className="muted small">{p.id === "free" ? "pour toujours" : interval === "year" ? `HT / mois, soit ${fmtEuro(p.yearly)} HT par an` : "HT / mois"}</span>
      </div>
      <div className="stack sm">{(PLAN_POINTS[p.id] || []).map((x) => <div className="feat small" key={x}><Check size={15} color="var(--ok)" /> {x}</div>)}</div>
      {p.id !== "free" && !current && b.billing_mode !== "disabled" && !(b.plan !== "free" && b.billing_mode === "stripe") && (
        <Button variant={p.id === "premium" ? "primary" : ""} icon={<CreditCard size={16} />} onClick={() => onChoose(p.id as "premium" | "agency")}>
          {b.billing_mode === "stripe" && b.trial_days && b.plan === "free" ? `Essayer ${p.name} ${b.trial_days} jours` : `Choisir ${p.name}`}
        </Button>
      )}
    </Card>
  );
}
