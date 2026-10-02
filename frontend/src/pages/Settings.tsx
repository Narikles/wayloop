import { useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router-dom";
import { Check, CreditCard, ExternalLink, Minus } from "lucide-react";
import type { CompanyRef } from "../api/types";
import { applyTheme, IS_DEMO, useAction, useApi, useLoad, useSession, type Theme } from "../lib/ctx";
import { fmtDate, fmtEuro } from "../lib/format";
import { Combobox } from "../ui/Combobox";
import { Badge, Button, Card, ErrorBox, Field, Notice, PageHeader, Segmented, Spinner, Tabs } from "../ui/kit";

type Section = "entreprise" | "apparence" | "abonnement";

export default function SettingsPage() {
  const { section = "entreprise" } = useParams();
  const nav = useNavigate();
  const s = (["entreprise", "apparence", "abonnement"].includes(section) ? section : "entreprise") as Section;
  return (
    <main className="content narrow">
      <PageHeader title="Paramètres" />
      <Tabs<Section> value={s} onChange={(v) => nav(v === "entreprise" ? "/parametres" : `/parametres/${v}`)}
        items={[{ id: "entreprise", label: "Entreprise" }, { id: "apparence", label: "Apparence" }, { id: "abonnement", label: "Abonnement" }]} />
      {s === "entreprise" && <CompanySection />}
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

const ROWS: [string, boolean | string, boolean | string][] = [
  ["Recrutements en même temps", "1", "Illimités"],
  ["Offre rédigée et publiée sur Google pour l'emploi, lien à partager", true, true],
  ["Questions aux candidats et synthèse critère par critère", true, true],
  ["Sélection, e-mails groupés, réponse à chaque candidat", true, true],
  ["Questions d'entretien, notes et comparatif", true, true],
  ["Dates d'entretien confirmées, rappel la veille", true, true],
  ["Les candidats choisissent leur créneau en ligne", false, true],
  ["Export des candidatures", false, true],
];

function Cell({ v }: { v: boolean | string }) {
  if (typeof v === "string") return <span className="strong">{v}</span>;
  return v ? <Check size={18} color="var(--ok)" aria-label="Inclus" /> : <Minus size={18} color="var(--subtle)" aria-label="Non inclus" />;
}

function BillingSection() {
  const api = useApi();
  const run = useAction();
  const loc = useLocation();
  const { reload: reloadMe } = useSession();
  const [b, err, reload] = useLoad(() => api.billing(), []);
  const [interval, setInterval] = useState<"month" | "year">("year");
  const status = new URLSearchParams(loc.search).get("statut");
  if (err) return <ErrorBox msg={err} />;
  if (!b) return <Spinner />;
  const premium = b.plan === "premium";
  const price = interval === "year" ? b.prices.yearly_per_month : b.prices.monthly;
  const checkout = async () => {
    const r = await run(() => api.checkout(interval));
    if (!r) return;
    if (r.url.startsWith("http") && !r.url.includes("/abonnement")) window.location.href = r.url;
    else { await reload(); await reloadMe(); }
  };
  return (
    <div className="stack lg">
      {status === "ok" && <Notice tone="ok" title="Votre abonnement Premium est actif." />}
      {status === "annule" && <Notice title="Paiement annulé">Vous êtes toujours sur l'offre Gratuit.</Notice>}
      <Card title={premium ? "Premium" : "Offre Gratuit"} sub={premium
        ? `${b.interval === "year" ? "Annuel" : "Mensuel"}${b.period_end ? ` · prochaine échéance le ${fmtDate(b.period_end)}` : ""}`
        : `${b.usage.active_recruitments}/${b.usage.limit} recrutement en cours`}
        actions={premium ? <Badge tone="ok" dot>Actif</Badge> : undefined}>
        {premium ? (
          <div className="row">
            {b.billing_mode === "stripe" && b.has_customer && <Button icon={<ExternalLink size={14} />} onClick={async () => { const r = await run(() => api.portal()); if (r) window.location.href = r.url; }}>Factures et moyen de paiement</Button>}
            {b.billing_mode === "demo" && <Button variant="ghost" onClick={async () => { await run(() => api.cancelDemo(), "Retour à l'offre Gratuit"); await reload(); await reloadMe(); }}>Revenir à l'offre Gratuit</Button>}
          </div>
        ) : (
          <div className="stack">
            <div className="row between">
              <div className="row" style={{ alignItems: "baseline", gap: 6 }}>
                <span className="price">{fmtEuro(price)}</span>
                <span className="muted">HT / mois{interval === "year" ? `, soit ${fmtEuro(b.prices.yearly)} HT par an` : ", sans engagement"}</span>
              </div>
              <Segmented label="Facturation" value={interval} onChange={setInterval} items={[{ id: "month", label: "Mensuel" }, { id: "year", label: "Annuel · −20 %" }]} />
            </div>
            {b.billing_mode === "disabled" ? <Notice>Le paiement en ligne n'est pas encore ouvert. Contactez-nous.</Notice> : (
              <div className="row">
                <Button variant="primary" size="lg" icon={<CreditCard size={16} />} onClick={checkout}>
                  {b.billing_mode === "stripe" && b.trial_days ? `Essayer Premium ${b.trial_days} jours` : "Passer à Premium"}
                </Button>
                <span className="xs muted">{IS_DEMO || b.billing_mode === "demo" ? "Démo : activation immédiate, sans paiement." : "Paiement sécurisé par Stripe · résiliable à tout moment."}</span>
              </div>
            )}
          </div>
        )}
      </Card>
      <Card title="Ce que comprend chaque offre" flush>
        <div className="table-wrap">
          <table className="table">
            <thead><tr><th /><th className="center">Gratuit</th><th className="center">Premium</th></tr></thead>
            <tbody>{ROWS.map(([l, f, p]) => <tr key={l}><td>{l}</td><td className="center"><Cell v={f} /></td><td className="center"><Cell v={p} /></td></tr>)}</tbody>
          </table>
        </div>
      </Card>
    </div>
  );
}
