import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { ArrowRight, Check, NotebookPen } from "lucide-react";
import type { ApplicationItem, DebriefNote, RecruitmentDetail } from "../../api/types";
import { useAction, useApi, useLoad, useSession } from "../../lib/ctx";
import { fmtDayShort, fmtTime } from "../../lib/format";
import { Badge, Button, Card, Empty, Field, Spinner } from "../../ui/kit";
import type { PageProps } from "../Recruitment";

const happened = (a: ApplicationItem) => !!a.interview && (a.interview.status === "attended" || (a.interview.status === "booked" && !!a.interview.start && Date.parse(a.interview.start) < Date.now()));
const toNote = (a: ApplicationItem) => happened(a) && a.debrief_status !== "validated";

function statusLine(a: ApplicationItem): [string, string] {
  const when = a.interview?.start ? `Entretien ${fmtDayShort(a.interview.start)} · ${fmtTime(a.interview.start)}` : "Date à fixer";
  if (a.debrief_status === "validated") return [`Noté · ${when.toLowerCase()}`, "ok"];
  if (a.interview?.status === "no_show") return ["Absent(e)", ""];
  if (toNote(a)) return [when, "warn"];
  return [when, ""];
}

export function DebriefPage({ rec, reload }: PageProps) {
  const api = useApi();
  const loc = useLocation();
  const focus = new URLSearchParams(loc.search).get("candidat");
  const [apps, , reloadApps] = useLoad(() => api.listApplications(rec.id), [rec.id, rec.state]);
  const met = useMemo(() => (apps || []).filter((a) => a.interview && (a.status !== "rejected" || a.debrief_status)), [apps]);
  const [cur, setCur] = useState<string | null>(focus);
  useEffect(() => {
    if (!cur && met.length) setCur((met.find(toNote) || met[0]).id);
  }, [met, cur]);
  if (!apps) return <Spinner />;
  if (!met.length) {
    return <Card><Empty icon={<NotebookPen size={20} />} title="Rien à noter pour l'instant">Après chaque entretien, notez ici les réponses aux questions : la comparaison se fait ensuite toute seule.</Empty></Card>;
  }
  const allDone = met.every((a) => a.debrief_status === "validated" || a.interview?.status === "no_show");
  const current = met.find((a) => a.id === cur) || met[0];
  const next = () => {
    const after = met.filter((a) => a.id !== current.id).find(toNote);
    if (after) setCur(after.id);
  };
  return (
    <div className="stack lg">
      {allDone && rec.state !== "closed" && (
        <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Tous les entretiens sont notés</h2></>}
          sub="Le comparatif est prêt : choisissez la personne à recruter."
          foot={<Link className="btn primary" to={`/recrutements/${rec.id}/decision`}>Comparer et décider <ArrowRight size={16} /></Link>} />
      )}
      <div className="split wide-left">
        <Card title="Personnes rencontrées" flush>
          <ul className="note-list">
            {met.map((a) => {
              const [l, t] = statusLine(a);
              return (
                <li key={a.id}>
                  <button className={a.id === current.id ? "on" : ""} aria-current={a.id === current.id} onClick={() => setCur(a.id)}>
                    <span className="grow"><b>{a.name}</b><span className="xs muted">{l}</span></span>
                    {a.debrief_status === "validated" ? <Check size={16} color="var(--ok)" /> : t === "warn" ? <Badge tone="warn" dot>À noter</Badge> : null}
                  </button>
                </li>
              );
            })}
          </ul>
        </Card>
        <NotesEditor key={current.id} rec={rec} appId={current.id} onSaved={async () => { await reloadApps(); await reload(); next(); }} />
      </div>
    </div>
  );
}

function NotesEditor({ rec, appId, onSaved }: { rec: RecruitmentDetail; appId: string; onSaved: () => void }) {
  const api = useApi();
  const run = useAction();
  const { touch } = useSession();
  const [a] = useLoad(() => api.getApplication(appId), [appId]);
  const qs = rec.grid?.questions || [];
  const [notes, setNotes] = useState<Record<string, DebriefNote> | null>(null);
  const [overall, setOverall] = useState("");
  useEffect(() => {
    if (!a) return;
    setNotes(a.debrief?.notes || Object.fromEntries(qs.map((q) => [q.id, { score: null, notes: "" }])));
    setOverall(a.debrief?.overall || "");
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [a]);
  if (!a || !notes) return <Card><Spinner /></Card>;
  const setN = (qid: string, patch: Partial<DebriefNote>) => setNotes({ ...notes, [qid]: { ...notes[qid], ...patch } });
  const scored = Object.values(notes).filter((n) => n?.score).length;
  return (
    <Card title={`Notes — ${a.name}`} sub="1 insuffisant · 2 correct · 3 solide. Notez ce qui a été dit, pas une impression."
      actions={a.debrief?.status === "validated" ? <Badge tone="ok" dot>Enregistré</Badge> : undefined}
      foot={<>
        <span className="small muted tnum" style={{ marginRight: "auto" }}>{scored}/{qs.length} questions notées</span>
        <Button variant="primary" icon={<Check size={16} />} onClick={async () => {
          const r = await run(() => api.saveNotes(a.id, notes, overall), "Notes enregistrées");
          if (r) { touch(); onSaved(); }
        }}>Enregistrer les notes</Button>
      </>}>
      {qs.map((q, i) => (
        <div className="stack sm" key={q.id} style={{ paddingBottom: 14, borderBottom: "1px solid var(--line)" }}>
          <b className="strong"><span className="muted">{i + 1}.</span> {q.text}</b>
          <div className="row">
            <div className="score" role="radiogroup" aria-label={`Note de la question ${i + 1}`}>
              {[1, 2, 3].map((s) => <button key={s} role="radio" aria-checked={notes[q.id]?.score === s} className={notes[q.id]?.score === s ? "on" : ""} title={q.anchors[String(s) as "1"]}
                onClick={() => setN(q.id, { score: notes[q.id]?.score === s ? null : s })}>{s}</button>)}
            </div>
            <span className="small muted" style={{ flex: "1 1 220px" }}>{notes[q.id]?.score ? q.anchors[String(notes[q.id].score) as "1"] : ""}</span>
          </div>
          <textarea className="textarea" rows={2} style={{ minHeight: 52 }} aria-label={`Notes de la question ${i + 1}`} placeholder="Ce qu'a répondu la personne"
            value={notes[q.id]?.notes || ""} onChange={(e) => setN(q.id, { notes: e.target.value })} />
        </div>
      ))}
      <Field label="Impression générale (facultatif)"><textarea className="textarea" rows={2} value={overall} onChange={(e) => setOverall(e.target.value)} /></Field>
    </Card>
  );
}
