import { useState } from "react";
import { Check, ChevronDown, ChevronUp, Copy, ExternalLink, Globe, Mail, Send, Sparkles } from "lucide-react";
import { ApiError } from "../../api/client";
import type { DiffusionChannel, Issue, RecruitmentDetail } from "../../api/types";
import { useAction, useApi, useLoad, useToast } from "../../lib/ctx";
import { fmtDate, fmtShort } from "../../lib/format";
import { Badge, Button, Card, IssueLine, OfferText, Segmented, Spinner, removeMention } from "../../ui/kit";
import type { PageProps } from "../Recruitment";
import { CopyButton } from "./shared";

export function OfferPage({ rec, onChange }: PageProps) {
  const api = useApi();
  const [editing, setEditing] = useState(false);
  const offer = rec.offer;
  const draft = rec.state === "offer_review";
  const editable = draft || rec.state === "collecting";
  return (
    <div className="split">
      <div className="stack lg">
        {draft && (
          <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Publier l'offre</h2></>}
            sub="Elle est mise en ligne avec son lien de candidature et diffusée automatiquement."
            foot={<Button variant="primary" icon={<Send size={16} />} done="Offre publiée" onClick={async () => onChange(await api.publish(rec.id))}>Publier l'offre</Button>} />
        )}
        <Card title="Texte de l'offre" sub={rec.assisted?.engine === "ia" ? <span className="row" style={{ gap: 6 }}><Sparkles size={13} /> Brouillon rédigé avec l'assistant IA, relu par vous</span> : undefined}
          actions={editable && !editing && offer ? <button className="btn sm" onClick={() => setEditing(true)}>Modifier</button> : undefined}>
          {!offer ? <p className="muted">Pas encore d'offre.</p> : editing
            ? <OfferEditor rec={rec} onSaved={(r) => { onChange(r); setEditing(false); }} onCancel={() => setEditing(false)} />
            : <OfferText text={offer.long} skipTitle={rec.title} />}
        </Card>
      </div>
      <div className="stack lg">
        {rec.published_at && <DiffusionCard rec={rec} />}
        <Card title="Questions aux candidats" sub="Posées au moment de postuler.">
          {rec.profile.criteria.length ? (
            <div className="stack sm">
              <span className="xs muted strong">Critères (réponses rapprochées du CV)</span>
              <ul className="stack sm" style={{ margin: 0, paddingLeft: 18 }}>
                {rec.profile.criteria.map((c) => <li key={c.id}>{c.label} <span className="xs muted">· {c.required ? "indispensable" : "souhaité"}</span></li>)}
              </ul>
            </div>
          ) : null}
          {(rec.profile.questions || []).length > 0 && (
            <div className="stack sm">
              <span className="xs muted strong">Présélection (réponse libre, jamais notée)</span>
              <ol className="stack sm" style={{ margin: 0, paddingLeft: 18 }}>
                {rec.profile.questions!.map((q) => <li key={q.id}>{q.text}</li>)}
              </ol>
            </div>
          )}
          {!rec.profile.criteria.length && !(rec.profile.questions || []).length && <p className="muted small">Aucune question : les candidats envoient seulement leur CV.</p>}
        </Card>
      </div>
    </div>
  );
}

const STATUS: Record<string, [string, string]> = {
  todo: ["À publier", "warn"], posted: ["Publiée", "ok"], closed: ["À retirer", "bad"], removed: ["Retirée", ""], draft: ["Après publication", ""],
};

/** Diffusion : automatique là où c'est possible, en un copier-coller ailleurs (« poster partout, honnêtement »). */
function DiffusionCard({ rec }: { rec: RecruitmentDetail }) {
  const api = useApi();
  const [chans, err, , setChans] = useLoad(() => api.diffusion(rec.id), [rec.id, rec.offer?.version, rec.state]);
  if (err) return <Card title="Diffusion"><p className="muted small">{err}</p></Card>;
  if (!chans) return <Card title="Diffusion"><Spinner /></Card>;
  const auto = chans.filter((c) => c.mode === "auto");
  const manual = chans.filter((c) => c.mode === "manual");
  const closed = auto.length > 0 && auto.every((c) => c.status === "closed");
  const done = manual.filter((c) => c.status === "posted").length;
  return (
    <Card title="Diffusion" sub={closed ? "Recrutement clos : l'offre est retirée de Google et de sa page." : `En ligne depuis le ${fmtDate(rec.published_at)}.`}>
      <ul className="chan-list">
        {auto.map((c) => (
          <li key={c.id}>
            <Globe size={16} color="var(--muted)" />
            <span className="grow"><span className="strong small">{c.label}</span><span className="xs muted">{c.detail || "Automatique, sans rien faire"}</span></span>
            <Badge tone={c.status === "closed" ? "" : "ok"} dot>{c.status === "closed" ? "Retirée" : "En ligne"}</Badge>
          </li>
        ))}
      </ul>
      <div className="stack sm">
        <div className="row between">
          <span className="strong small">À publier vous-même, en un copier-coller</span>
          {!closed && <span className="xs muted tnum">{done}/{manual.length} faits</span>}
        </div>
        <span className="xs muted">Ces sites n'acceptent pas de publication automatique sans accord. Le texte est prêt, adapté à chacun, avec un lien de candidature suivi : la provenance de chaque candidat s'affiche dans le pipeline.</span>
        <div className="stack sm">{manual.map((c) => <ManualChannel key={c.id} rec={rec} c={c} onChange={setChans} />)}</div>
      </div>
      {rec.apply_link && !closed && (
        <div className="stack sm">
          <span className="small muted">Lien direct (affichage en magasin, réseaux, e-mail)</span>
          <div className="link-box"><code>{rec.apply_link}</code><CopyButton text={rec.apply_link} label="Copier" /></div>
        </div>
      )}
      {rec.inbound_address && !closed && (
        <div className="stack sm">
          <span className="small muted row" style={{ gap: 6 }}><Mail size={14} /> Adresse de réception des CV : les e-mails reçus deviennent des candidatures</span>
          <div className="link-box"><code>{rec.inbound_address}</code><CopyButton text={rec.inbound_address} label="Copier" /></div>
          <span className="xs muted">Vous pouvez aussi y transférer une candidature reçue dans votre propre boîte.</span>
        </div>
      )}
    </Card>
  );
}

function ManualChannel({ rec, c, onChange }: { rec: RecruitmentDetail; c: DiffusionChannel; onChange: (x: DiffusionChannel[]) => void }) {
  const api = useApi();
  const run = useAction();
  const notify = useToast();
  const [open, setOpen] = useState(false);
  const [optimistic, setOptimistic] = useState<boolean | null>(null);
  const [st, tone] = c.outdated ? ["À mettre à jour", "warn"] : STATUS[c.status] || [c.status, ""];
  const isClosed = c.status === "closed" || c.status === "removed";
  const checkable = !c.outdated && (c.status === "todo" || c.status === "posted");
  const toggle = async (posted: boolean) => {
    setOptimistic(posted);
    const r = await run(() => api.markPosted(rec.id, c.id, posted));
    if (r) onChange(r);
    setOptimistic(null);
  };
  const copy = async () => {
    try {
      await navigator.clipboard.writeText(c.text || "");
      notify(`Texte pour ${c.label} copié`);
    } catch {
      setOpen(true);
      notify("Copie impossible : sélectionnez le texte.", "bad");
    }
  };
  const sub = c.outdated ? "L'offre a changé depuis : recopiez le texte." : c.status === "posted" && c.at ? `Publiée le ${fmtShort(c.at)}` : c.hint;
  return (
    <div className={`chan-manual ${c.status === "posted" && !c.outdated ? "done" : ""}`}>
      <div className="chan-manual-head">
        <span className="grow stack" style={{ gap: 0 }}>
          <span className="strong small">{c.label}</span>
          <span className="xs muted">{sub}</span>
        </span>
        {checkable ? (
          <label className="check chan-check">
            <input type="checkbox" checked={optimistic ?? c.status === "posted"} disabled={optimistic !== null} onChange={(e) => toggle(e.target.checked)} />
            <span className="small">Publiée</span>
          </label>
        ) : <Badge tone={tone}>{st}</Badge>}
      </div>
      {c.status !== "removed" && (
        <div className="row" style={{ gap: 6 }}>
          {!isClosed && c.text && <button className="btn sm" onClick={copy} title={`Copier le texte pour ${c.label}`}><Copy size={14} /> Copier</button>}
          {c.url && <a className="btn sm" href={c.url} target="_blank" rel="noreferrer" aria-label={`Ouvrir ${c.label} (nouvel onglet)`}><ExternalLink size={14} /> Ouvrir</a>}
          {!isClosed && c.text && (
            <button className="btn sm ghost" aria-expanded={open} onClick={() => setOpen(!open)}>
              {open ? <ChevronUp size={14} /> : <ChevronDown size={14} />} {open ? "Masquer" : "Voir le texte"}
            </button>
          )}
          {c.outdated && <button className="btn sm ghost" onClick={() => toggle(true)}><Check size={14} /> C'est mis à jour</button>}
          {c.status === "closed" && <button className="btn sm" onClick={() => toggle(false)}><Check size={14} /> C'est retiré</button>}
        </div>
      )}
      {open && c.text && <textarea className="textarea chan-text" readOnly rows={8} value={c.text} onFocus={(e) => e.currentTarget.select()} aria-label={`Texte pour ${c.label}`} />}
    </div>
  );
}

function OfferEditor({ rec, onSaved, onCancel }: { rec: RecruitmentDetail; onSaved: (r: RecruitmentDetail) => void; onCancel: () => void }) {
  const api = useApi();
  const notify = useToast();
  const offer = rec.offer!;
  const [long, setLong] = useState(offer.long);
  const [short, setShort] = useState(offer.short);
  const [which, setWhich] = useState<"long" | "short">("long");
  const [issues, setIssues] = useState<Issue[]>([]);
  const [busy, setBusy] = useState(false);
  const save = async (s: string, l: string) => {
    setBusy(true);
    try {
      onSaved(await api.editOffer(rec.id, s, l));
      notify(rec.published_at ? "Offre mise à jour partout" : "Offre enregistrée");
    } catch (e) {
      if (e instanceof ApiError && e.issues.length) setIssues(e.issues);
      else notify((e as Error).message, "bad");
    } finally {
      setBusy(false);
    }
  };
  const remove = (i: Issue) => {
    const s = i.field === "short" ? removeMention(short, i.match!) : short;
    const l = i.field === "short" ? long : removeMention(long, i.match!);
    setShort(s);
    setLong(l);
    setIssues([]);
    void save(s, l);
  };
  return (
    <div className="stack">
      <Segmented label="Version" value={which} onChange={setWhich} items={[{ id: "long", label: "Offre complète" }, { id: "short", label: "Résumé (moteurs de recherche)" }]} />
      {which === "long"
        ? <textarea aria-label="Offre complète" className={`textarea ${issues.some((i) => i.field !== "short") ? "has-issue" : ""}`} rows={18} value={long} onChange={(e) => { setLong(e.target.value); setIssues([]); }} />
        : <textarea aria-label="Résumé" className={`textarea ${issues.some((i) => i.field === "short") ? "has-issue" : ""}`} rows={5} value={short} onChange={(e) => { setShort(e.target.value); setIssues([]); }} />}
      {issues.map((i, k) => <IssueLine key={k} issue={i} onRemove={() => remove(i)} />)}
      <div className="row">
        <button className="btn primary" disabled={busy || (long === offer.long && short === offer.short)} onClick={() => save(short, long)}>{busy && <span className="spinner" />} Enregistrer</button>
        <button className="btn ghost" onClick={onCancel}>Annuler</button>
      </div>
    </div>
  );
}
