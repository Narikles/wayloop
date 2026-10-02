import { useState } from "react";
import { Globe, Send } from "lucide-react";
import { ApiError } from "../../api/client";
import type { Issue, RecruitmentDetail } from "../../api/types";
import { useApi, useToast } from "../../lib/ctx";
import { fmtDate } from "../../lib/format";
import { Badge, Button, Card, IssueLine, OfferText, Segmented, removeMention } from "../../ui/kit";
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
        <Card title="Texte de l'offre" actions={editable && !editing && offer ? <button className="btn sm" onClick={() => setEditing(true)}>Modifier</button> : undefined}>
          {!offer ? <p className="muted">Pas encore d'offre.</p> : editing
            ? <OfferEditor rec={rec} onSaved={(r) => { onChange(r); setEditing(false); }} onCancel={() => setEditing(false)} />
            : <OfferText text={offer.long} skipTitle={rec.title} />}
        </Card>
      </div>
      <div className="stack lg">
        {rec.published_at && <DiffusionCard rec={rec} />}
        <Card title="Questions aux candidats" sub="Posées au moment de postuler ; les réponses sont rapprochées du CV.">
          {rec.profile.criteria.length ? (
            <ul className="stack sm" style={{ margin: 0, paddingLeft: 18 }}>
              {rec.profile.criteria.map((c) => <li key={c.id}>{c.label} <span className="xs muted">· {c.required ? "indispensable" : "souhaité"}</span></li>)}
            </ul>
          ) : <p className="muted small">Aucun critère : les candidats envoient seulement leur CV.</p>}
        </Card>
      </div>
    </div>
  );
}

function DiffusionCard({ rec }: { rec: RecruitmentDetail }) {
  const chans = rec.offer?.channels || [];
  const closed = chans.length > 0 && chans.every((c) => c.status === "closed");
  return (
    <Card title="Diffusion" sub={closed ? "Offre retirée." : `En ligne depuis le ${fmtDate(rec.published_at)}.`}>
      <ul className="chan-list">
        {chans.map((c) => (
          <li key={c.id}>
            <Globe size={16} color="var(--muted)" />
            <span className="grow"><span className="strong small">{c.label}</span>{c.detail && <span className="xs muted">{c.detail}</span>}</span>
            <Badge tone={c.status === "closed" ? "" : "ok"} dot>{c.status === "closed" ? "Retirée" : "En ligne"}</Badge>
          </li>
        ))}
      </ul>
      {rec.apply_link && !closed && (
        <div className="stack sm">
          <span className="small muted">Lien à partager (réseaux, e-mail, affichage en magasin)</span>
          <div className="link-box"><code>{rec.apply_link}</code><CopyButton text={rec.apply_link} label="Copier" /></div>
        </div>
      )}
      {!closed && <span className="xs muted">D'autres sites d'emploi s'ajouteront ici automatiquement.</span>}
    </Card>
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
