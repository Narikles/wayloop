import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Scale, Send } from "lucide-react";
import type { Comparison, Proposal, RecruitmentDetail } from "../../api/types";
import { useApi, useLoad } from "../../lib/ctx";
import { fmtDate, plural } from "../../lib/format";
import { Button, Card, Empty, Field, Spinner, Tabs } from "../../ui/kit";
import type { PageProps } from "../Recruitment";

export function DecisionPage({ rec, onChange }: PageProps) {
  const pending = (k: string) => rec.pending.find((p) => p.kind === k);
  const closing = pending("closing_messages");
  const followups = rec.pending.filter((p) => p.kind === "followup");
  const deciding = !!pending("decision") || rec.state === "decision";

  if (["closed", "abandoned"].includes(rec.state)) {
    return <div className="stack lg">
      {followups.map((p) => <FollowupCard key={p.id} rec={rec} prop={p} onChange={onChange} />)}
      <ClosedSummary rec={rec} />
    </div>;
  }
  if (closing) return <ClosingCard rec={rec} prop={closing} onChange={onChange} />;
  if (deciding) return <DecisionCard rec={rec} onChange={onChange} />;
  return <NotYet rec={rec} onChange={onChange} />;
}

function NotYet({ rec, onChange }: Omit<PageProps, "reload">) {
  const api = useApi();
  const interviewing = rec.state === "interviewing";
  return (
    <Card>
      <Empty icon={<Scale size={20} />} title="La décision vient après les entretiens"
        action={interviewing && rec.counts.noted > 0 ? <Button variant="ghost" onClick={async () => onChange(await api.openDecision(rec.id))}>Comparer sans attendre les autres entretiens</Button> : undefined}>
        Une fois les entretiens notés, le comparatif s'affiche ici et chaque candidat reçoit une réponse.
      </Empty>
    </Card>
  );
}

export function ComparisonTable({ c, chosen, onChoose }: { c: Comparison; chosen?: string | null; onChoose?: (id: string) => void }) {
  if (!c.candidates.length) return <p className="muted">Aucun entretien noté pour l'instant.</p>;
  return (
    <div className="table-wrap">
      <table className="table">
        <thead><tr><th style={{ minWidth: 220 }}>Question</th>{c.candidates.map((x) => <th key={x.application_id} className="center">{x.name}</th>)}</tr></thead>
        <tbody>
          {c.questions.map((q, i) => (
            <tr key={q.id}><td className="small"><span className="muted">{i + 1}.</span> {q.text}</td>
              {c.candidates.map((x) => <td key={x.application_id} className="center tnum" title={x.notes[q.id] || ""}>{x.scores[q.id] ? <b className="strong">{x.scores[q.id]}</b> : <span className="subtle">–</span>}</td>)}</tr>
          ))}
          <tr><td><b className="strong">Total</b> <span className="xs muted">sur {c.max_total}</span></td>
            {c.candidates.map((x) => <td key={x.application_id} className="center tnum"><b className="strong">{x.total ?? "–"}</b>{x.answered < c.questions.length && <div className="xs muted">{x.answered}/{c.questions.length} notées</div>}</td>)}</tr>
          {onChoose && <tr><td className="small muted">Votre choix</td>{c.candidates.map((x) => (
            <td key={x.application_id} className="center"><input type="radio" name="hire" style={{ accentColor: "var(--brand)", width: 18, height: 18 }} checked={chosen === x.application_id} onChange={() => onChoose(x.application_id)} aria-label={`Choisir ${x.name}`} /></td>
          ))}</tr>}
        </tbody>
      </table>
    </div>
  );
}

/** Sur mobile : une carte par personne (total, notes question par question), au lieu du tableau. */
function ComparisonCards({ c, chosen, onChoose }: { c: Comparison; chosen: string | null; onChoose: (id: string) => void }) {
  return (
    <div className="only-sm stack sm" role="radiogroup" aria-label="Personne à recruter">
      {c.candidates.map((x) => (
        <label key={x.application_id} className={`pick-card ${chosen === x.application_id ? "on" : ""}`}>
          <input type="radio" name="hire-m" checked={chosen === x.application_id} onChange={() => onChoose(x.application_id)} />
          <span className="grow">
            <b className="strong">{x.name}</b>
            <span className="xs muted tnum">{c.questions.map((q, i) => `Q${i + 1} ${x.scores[q.id] ?? "–"}`).join(" · ")}</span>
          </span>
          <span className="tnum strong">{x.total ?? "–"}<span className="xs muted">/{c.max_total}</span></span>
        </label>
      ))}
    </div>
  );
}

function DecisionCard({ rec, onChange }: Omit<PageProps, "reload">) {
  const api = useApi();
  const [c] = useLoad(() => api.comparison(rec.id), [rec.id, rec.counts.noted]);
  const [chosen, setChosen] = useState<string | null>(null);
  const name = useMemo(() => c?.candidates.find((x) => x.application_id === chosen)?.name, [c, chosen]);
  if (!c) return <Spinner />;
  return (
    <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Comparez et choisissez</h2></>}
      sub="Vos notes, question par question. Le total aide à comparer ; c'est vous qui décidez."
      foot={<>
        <Button variant="ghost" onClick={async () => onChange(await api.decide(rec.id, null))}>Ne recruter personne</Button>
        <Button variant="primary" disabled={!chosen} onClick={async () => onChange(await api.decide(rec.id, chosen))}>{name ? `Recruter ${name}` : "Choisissez une personne"}</Button>
      </>}>
      <div className="hide-sm" style={{ margin: "0 -20px" }}><ComparisonTable c={c} chosen={chosen} onChoose={setChosen} /></div>
      <ComparisonCards c={c} chosen={chosen} onChoose={setChosen} />
      {c.candidates.some((x) => x.overall) && (
        <div className="stack sm small">{c.candidates.filter((x) => x.overall).map((x) => <span key={x.application_id}><b className="strong">{x.name} :</b> <span className="muted">{x.overall}</span></span>)}</div>
      )}
    </Card>
  );
}

const TPL_LABEL: Record<string, string> = { hired: "Personne recrutée", rejected_interviewed: "Personnes rencontrées", rejected: "Autres candidats" };

function ClosingCard({ rec, prop, onChange }: { rec: RecruitmentDetail; prop: Proposal; onChange: (r: RecruitmentDetail) => void }) {
  const api = useApi();
  const tpl: Record<string, { subject: string; body: string; count: number }> = prop.payload.templates;
  const [edit, setEdit] = useState(tpl);
  const [tab, setTab] = useState(Object.keys(tpl)[0]);
  const total = Object.values(tpl).reduce((s, t) => s + t.count, 0);
  const t = edit[tab];
  return (
    <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Répondre à chaque candidat</h2></>}
      sub={`${plural(total, "réponse prête", "réponses prêtes")}. Relisez si vous le souhaitez, puis envoyez : le recrutement est alors clos.`}
      foot={<Button variant="primary" icon={<Send size={16} />} done="Réponses envoyées" onClick={async () => onChange(await api.accept(rec.id, prop.id, { templates: edit }))}>Envoyer les {total} réponses</Button>}>
      {Object.keys(edit).length > 1 && <Tabs value={tab} onChange={setTab} items={Object.entries(edit).map(([k, v]) => ({ id: k, label: TPL_LABEL[k] || k, count: v.count }))} />}
      {t && <>
        <Field label="Objet"><input className="input" value={t.subject} onChange={(e) => setEdit({ ...edit, [tab]: { ...t, subject: e.target.value } })} /></Field>
        <Field label="Message" hint={<><span className="kbd">{"{prénom}"}</span> est remplacé pour chacun.</>}>
          <textarea className="textarea" rows={9} value={t.body} onChange={(e) => setEdit({ ...edit, [tab]: { ...t, body: e.target.value } })} />
        </Field>
      </>}
    </Card>
  );
}

function FollowupCard({ rec, prop, onChange }: { rec: RecruitmentDetail; prop: Proposal; onChange: (r: RecruitmentDetail) => void }) {
  const api = useApi();
  return (
    <Card className="highlight" title={<><span className="eyebrow">{prop.title}</span><h2>La personne recrutée est-elle toujours en poste ?</h2></>}
      foot={<>
        <Button onClick={async () => onChange(await api.accept(rec.id, prop.id, { still_there: false }))}>Non, elle est partie</Button>
        <Button variant="primary" onClick={async () => onChange(await api.accept(rec.id, prop.id, { still_there: true }))}>Oui</Button>
      </>} />
  );
}

function ClosedSummary({ rec }: { rec: RecruitmentDetail }) {
  const api = useApi();
  const [apps] = useLoad(() => api.listApplications(rec.id), [rec.id]);
  const hired = apps?.find((a) => a.status === "hired");
  const from = rec.published_at || rec.created_at;
  const days = rec.closed_at ? Math.max(1, Math.round((Date.parse(rec.closed_at) - Date.parse(from)) / 86_400_000)) : null;
  return (
    <Card title={<h2>{rec.outcome === "hired" ? "Recrutement abouti" : "Recrutement clos"}</h2>}
      sub={`Clos le ${fmtDate(rec.closed_at)}. Chaque candidat a reçu une réponse.`}
      foot={<Link className="btn" to="/recrutements/nouveau">Nouveau recrutement</Link>}>
      <div className="grid c3">
        <div className="stack sm"><span className="small muted">Personne recrutée</span><span className="strong">{hired ? hired.name : "—"}</span></div>
        <div className="stack sm"><span className="small muted">Candidatures</span><span className="strong tnum">{rec.applications}</span></div>
        <div className="stack sm"><span className="small muted">Durée</span><span className="strong tnum">{days ? `${days} jour${days > 1 ? "s" : ""}` : "—"}</span></div>
      </div>
    </Card>
  );
}
