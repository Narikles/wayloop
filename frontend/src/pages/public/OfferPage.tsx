import { useRef, useState } from "react";
import { Link, useLocation, useParams } from "react-router-dom";
import { Briefcase, CheckCircle2, Clock, Euro, FileUp, Home, MapPin } from "lucide-react";
import type { ScreeningQuestion } from "../../api/types";
import { useApi, useLoad } from "../../lib/ctx";
import { Badge, Button, Card, ErrorBox, Field, Notice, Spinner, OfferText } from "../../ui/kit";
import PublicLayout from "./PublicLayout";

function QuestionInput({ q, value, onChange }: { q: ScreeningQuestion; value: unknown; onChange: (v: unknown) => void }) {
  const id = `q-${q.id}`;
  if (q.input === "yesno") {
    return (
      <div className="seg" role="radiogroup" aria-labelledby={`ql-${q.id}`}>
        <button type="button" role="radio" aria-checked={value === true} className={value === true ? "on" : ""} onClick={() => onChange(true)}>Oui</button>
        <button type="button" role="radio" aria-checked={value === false} className={value === false ? "on" : ""} onClick={() => onChange(false)}>Non</button>
      </div>
    );
  }
  if (q.input === "select") {
    return (
      <select id={id} className="select" value={value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value)}>
        <option value="" disabled>Choisir…</option>
        {q.options!.map((o) => <option key={String(o.value)} value={String(o.value)}>{o.label}</option>)}
      </select>
    );
  }
  if (q.input === "number") {
    return (
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input id={id} className="input tnum" type="number" min={q.min} max={q.max} step="0.5" style={{ maxWidth: 120 }} value={value === undefined ? "" : String(value)} onChange={(e) => onChange(e.target.value)} />
        <span className="muted">{q.unit}</span>
      </div>
    );
  }
  return <textarea id={id} className="textarea" rows={2} value={(value as string) || ""} onChange={(e) => onChange(e.target.value)} />;
}

export default function OfferPage() {
  const { token = "" } = useParams();
  const loc = useLocation();
  const api = useApi();
  const [o, err] = useLoad(() => api.publicOffer(token), [token]);
  const [done, setDone] = useState(false);
  const [f, setF] = useState({ first_name: "", last_name: "", email: "", phone: "", message: "", pool_consent: false });
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [cv, setCv] = useState<File | null>(null);
  const [drag, setDrag] = useState(false);
  const [formErr, setFormErr] = useState<string | null>(null);
  const file = useRef<HTMLInputElement>(null);
  // Provenance : lien de la plateforme (?src=…), sinon Google si l'on vient d'une recherche Google, sinon lien direct.
  const src = new URLSearchParams(loc.search).get("src") || (/(^|\.)google\./.test(document.referrer ? new URL(document.referrer).hostname : "") ? "google" : "lien");
  const missing = (o?.questions || []).filter((q) => q.required && (answers[q.id] === undefined || answers[q.id] === ""));

  return (
    <PublicLayout company={o?.company} slug={o?.company_slug}>
      <ErrorBox msg={err} />
      {!o && !err && <Spinner />}
      {o && (
        <div className="split">
          <div className="stack lg">
            <div className="stack sm">
              <h1 style={{ fontSize: 28 }}>{o.title}</h1>
              <div className="row" style={{ gap: 14 }}>
                {o.profile.contract && <span className="row small muted" style={{ gap: 6 }}><Briefcase size={15} /> {o.profile.contract}</span>}
                {o.profile.location && <span className="row small muted" style={{ gap: 6 }}><MapPin size={15} /> {o.profile.location}</span>}
                {o.profile.salary?.text && <span className="row small muted" style={{ gap: 6 }}><Euro size={15} /> {o.profile.salary.text}</span>}
                {o.profile.hours && <span className="row small muted" style={{ gap: 6 }}><Clock size={15} /> {o.profile.hours}</span>}
                {o.profile.remote && <span className="row small muted" style={{ gap: 6 }}><Home size={15} /> {o.profile.remote}</span>}
              </div>
            </div>
            {o.open && !done && <button type="button" className="btn primary show-sm" style={{ alignSelf: "flex-start" }} onClick={() => document.getElementById("postuler")?.scrollIntoView({ behavior: "smooth" })}>Postuler</button>}
            <Card><OfferText text={o.long} skipTitle={o.title} /></Card>
          </div>

          <div className="stack lg" style={{ position: "sticky", top: 20 }}>
            {!o.open ? <Notice title="Poste pourvu">Merci de votre intérêt.</Notice> : done ? (
              <Card className="highlight">
                <CheckCircle2 size={28} color="var(--ok)" />
                <h2>Candidature envoyée</h2>
                <p className="muted">Un accusé de réception part à votre adresse, avec la suite du processus et un lien pour consulter ou supprimer vos données. Vous aurez une réponse dans tous les cas.</p>
              </Card>
            ) : (
              <form id="postuler" onSubmit={async (e) => {
                e.preventDefault();
                setFormErr(null);
                if (missing.length) return setFormErr(`Merci de répondre à : ${missing[0].label}`);
                const fd = new FormData();
                Object.entries(f).forEach(([k, v]) => fd.append(k, String(v)));
                fd.append("src", src);
                fd.append("answers", JSON.stringify(answers));
                if (cv) fd.append("cv", cv);
                try { await api.apply(token, fd); setDone(true); } catch (x) { setFormErr((x as Error).message); }
              }}>
                <Card title="Postuler" sub="Environ 3 minutes"
                  foot={<Button type="submit" variant="primary" size="lg">Envoyer ma candidature</Button>}>
                  <div className="grid c2">
                    <Field label="Prénom" htmlFor="first_name"><input id="first_name" className="input" required value={f.first_name} onChange={(e) => setF({ ...f, first_name: e.target.value })} /></Field>
                    <Field label="Nom" htmlFor="last_name"><input id="last_name" className="input" required value={f.last_name} onChange={(e) => setF({ ...f, last_name: e.target.value })} /></Field>
                  </div>
                  <Field label="E-mail" htmlFor="email"><input id="email" className="input" type="email" required value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} /></Field>
                  <Field label="Téléphone (facultatif)" htmlFor="phone"><input id="phone" className="input" type="tel" value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} /></Field>
                  {o.questions.length > 0 && (
                    <div className="stack">
                      <hr className="sep" />
                      <div className="stack sm"><h4>Quelques questions sur le poste</h4><span className="xs muted">Elles portent uniquement sur les critères du poste. Vos réponses seront rapprochées de votre CV.</span></div>
                      {o.questions.map((q) => (
                        <Field key={q.id} htmlFor={q.input === "yesno" ? undefined : `q-${q.id}`} label={<span id={`ql-${q.id}`}>{q.label}{!q.required && <span className="muted"> (facultatif)</span>}</span>} hint={q.help}>
                          <QuestionInput q={q} value={answers[q.id]} onChange={(v) => setAnswers({ ...answers, [q.id]: v })} />
                        </Field>
                      ))}
                      <hr className="sep" />
                    </div>
                  )}
                  <Field label="CV">
                    <div className={`dropzone ${drag ? "drag" : ""}`} onClick={() => file.current?.click()}
                      onDragOver={(e) => { e.preventDefault(); setDrag(true); }} onDragLeave={() => setDrag(false)}
                      onDrop={(e) => { e.preventDefault(); setDrag(false); setCv(e.dataTransfer.files?.[0] || null); }}>
                      <FileUp size={20} />
                      {cv ? <span className="strong">{cv.name}</span> : <span>Glissez votre CV ici ou <span style={{ color: "var(--brand)" }}>parcourez</span></span>}
                      <span className="xs">PDF, Word ou texte · 10 Mo max. · photo inutile</span>
                      <input ref={file} id="cv" type="file" hidden accept=".pdf,.docx,.txt,application/pdf" onChange={(e) => setCv(e.target.files?.[0] || null)} />
                    </div>
                  </Field>
                  <Field label="Message (facultatif)" hint="Sans CV, présentez ici votre parcours."><textarea className="textarea" rows={3} value={f.message} onChange={(e) => setF({ ...f, message: e.target.value })} /></Field>
                  <input type="text" name="website" tabIndex={-1} autoComplete="off" style={{ position: "absolute", left: -9999 }} aria-hidden />
                  <label className="check small"><input type="checkbox" checked={f.pool_consent} onChange={(e) => setF({ ...f, pool_consent: e.target.checked })} />
                    <span>J'accepte que {o.company} garde ma candidature pour d'autres postes (facultatif)</span></label>
                  <span className="xs muted">Vos réponses et votre CV sont comparés aux critères du poste selon des règles fixes, après masquage des informations sans rapport (âge, adresse, situation de famille…). Rien n'est décidé automatiquement : une personne de l'entreprise décide. <Link to={`/confidentialite/${o.company_slug}`}>Vos données</Link>.</span>
                  {formErr && <Notice tone="bad">{formErr}</Notice>}
                </Card>
              </form>
            )}
            {o.open && !done && <div className="row" style={{ gap: 8 }}><Badge tone="ok" dot>Réponse garantie</Badge><Badge>Entretien structuré</Badge></div>}
          </div>
        </div>
      )}
    </PublicLayout>
  );
}
