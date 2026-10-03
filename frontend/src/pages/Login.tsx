import { useState } from "react";
import { Navigate } from "react-router-dom";
import { BellRing, Columns3, Inbox, MailCheck, Send, Sparkles } from "lucide-react";
import type { CompanyRef } from "../api/types";
import { useApi, useLoad, useSession } from "../lib/ctx";
import { fmtEuro } from "../lib/format";
import { Combobox } from "../ui/Combobox";
import { Button, Field, Logo, Notice, Tabs } from "../ui/kit";

export default function Login() {
  const api = useApi();
  const { me } = useSession();
  const [mode, setMode] = useState<"login" | "signup">("login");
  const [email, setEmail] = useState("");
  const [company, setCompany] = useState("");
  const [co, setCo] = useState<CompanyRef | null>(null);
  const [name, setName] = useState("");
  const [sent, setSent] = useState<{ demo_link?: string | null } | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [prices] = useLoad(() => api.pricing(), []);
  if (me) return <Navigate to="/" replace />;

  const submit = async () => {
    setErr(null);
    try {
      if (mode === "login") setSent(await api.requestLink(email));
      else setSent(await api.signup({ company_name: co?.name || company, name, email,
        siren: co?.siren, address: co?.address, naf_code: co?.naf_code, headcount_range: co?.headcount_range }));
    } catch (e) {
      setErr((e as Error).message);
    }
  };

  return (
    <div className="auth">
      <div className="auth-form">
        <div>
          <div className="logo" style={{ padding: 0 }}><Logo size={34} /> WayLoop</div>
          {sent ? (
            <div className="stack lg">
              <div className="stack sm">
                <MailCheck size={28} color="var(--brand)" />
                <h1>Vérifiez votre boîte mail</h1>
                <p className="muted">Nous avons envoyé un lien de connexion à <b>{email}</b>. Il est valable 30 minutes. Aucun mot de passe à retenir.</p>
              </div>
              {sent.demo_link && <a className="btn primary lg" href={sent.demo_link.replace(/^https?:\/\/[^/]+/, "")}>Mode démo : ouvrir le lien</a>}
              <button className="btn link" onClick={() => setSent(null)}>Utiliser une autre adresse</button>
            </div>
          ) : (
            <form className="stack lg" onSubmit={(e) => { e.preventDefault(); void submit(); }}>
              <div className="stack sm">
                <h1>{mode === "login" ? "Connexion" : "Créer votre espace"}</h1>
                <p className="muted">{mode === "login" ? "Recevez un lien de connexion par e-mail." : "Gratuit, sans carte bancaire."}</p>
              </div>
              <Tabs value={mode} onChange={setMode} items={[{ id: "login", label: "J'ai un compte" }, { id: "signup", label: "Créer un compte" }]} />
              {mode === "signup" && (
                <>
                  <Field label="Entreprise" htmlFor="company" hint={co ? `SIREN ${co.siren}${co.headcount_range ? ` · ${co.headcount_range}` : ""}` : "Nom ou numéro SIREN — annuaire officiel des entreprises"}>
                    <Combobox<CompanyRef> id="company" value={company} placeholder="Ex. Négoce Durand" minChars={3}
                      onChange={(v) => { setCompany(v); setCo(null); }}
                      onPick={(c) => { setCo(c); setCompany(c.display_name); }}
                      search={async (q) => (await api.companySearch(q)).results}
                      render={(c) => <><b>{c.display_name}</b><span className="xs muted">{c.address} · SIREN {c.siren}</span></>}
                      footer="Source : annuaire-entreprises.data.gouv.fr" />
                  </Field>
                  <Field label="Votre nom" htmlFor="name"><input id="name" className="input" required value={name} onChange={(e) => setName(e.target.value)} /></Field>
                </>
              )}
              <Field label="E-mail professionnel" htmlFor="email">
                <input id="email" className="input" type="email" required autoComplete="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="vous@entreprise.fr" />
              </Field>
              {err && <Notice tone="bad">{err}</Notice>}
              <Button type="submit" variant="primary" size="lg">{mode === "login" ? "Recevoir mon lien" : "Créer mon espace gratuit"}</Button>
              <p className="xs muted">En continuant, vous acceptez les conditions d'utilisation.</p>
            </form>
          )}
        </div>
      </div>
      <div className="auth-side">
        <div className="row" style={{ color: "#fff", gap: 10, fontWeight: 600 }}><Logo size={28} /> WayLoop</div>
        <div className="stack lg">
          <h2>Recruter sans le chaos{"\u00a0"}: un processus clair, de l'offre au dernier candidat.</h2>
          {[
            [<Sparkles size={18} key="a" />, "Décrivez le poste en une phrase : l'offre, les critères et trois questions de présélection sont rédigés en cinq minutes."],
            [<Send size={18} key="b" />, "Publiez partout, honnêtement : Google pour l'emploi automatiquement, LinkedIn, Indeed et France Travail en un copier-coller."],
            [<Inbox size={18} key="c" />, "Toutes les candidatures au même endroit, provenance indiquée : formulaire, e-mail, message LinkedIn, appel."],
            [<Columns3 size={18} key="d" />, "Un pipeline simple : reçu, à évaluer, présélectionné, entretien, refusé ou embauché. Plus aucun candidat oublié."],
            [<BellRing size={18} key="e" />, "Remerciements et relances automatiques, récapitulatif chaque lundi."],
          ].map(([ic, t], i) => <div className="pt" key={i}>{ic}<span>{t}</span></div>)}
        </div>
        <span className="small" style={{ color: "rgb(255 255 255 / 70%)" }}>
          Gratuit pour un recrutement à la fois{prices ? ` · Pro ${fmtEuro(prices.premium.monthly)} HT/mois · Agence ${fmtEuro(prices.agency.monthly)} HT/mois` : ""}
        </span>
      </div>
    </div>
  );
}
