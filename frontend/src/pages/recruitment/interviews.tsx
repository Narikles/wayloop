import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarClock, Pencil, Plus, Printer, Trash2 } from "lucide-react";
import type { GridQuestion, InterviewItem, Proposal, RecruitmentDetail } from "../../api/types";
import { IS_DEMO, useAction, useApi, useLoad, useSession } from "../../lib/ctx";
import { fmtDay, fmtDayShort, fmtTime, plural } from "../../lib/format";
import { Badge, Button, Card, Empty, ErrorBox, Field, Modal, Notice, Spinner } from "../../ui/kit";
import type { PageProps } from "../Recruitment";
import { CandidateDrawer } from "./candidates";
import { ScheduleModal } from "./shared";

const IV: Record<string, [string, string]> = {
  invited: ["Date à fixer", "warn"], booked: ["Prévu", "brand"], attended: ["Fait", "ok"], no_show: ["Absent(e)", "bad"], cancelled: ["Annulé", ""],
};

export function InterviewsPage({ rec, onChange, reload }: PageProps) {
  const api = useApi();
  const run = useAction();
  const { touch } = useSession();
  const [data, err, reloadIvs] = useLoad(() => api.listInterviews(rec.id), [rec.id, rec.state, rec.counts.interviews]);
  const [sched, setSched] = useState<InterviewItem | null>(null);
  const [open, setOpen] = useState<string | null>(null);
  const [slotsModal, setSlotsModal] = useState(false);
  const invite = rec.pending.find((p) => p.kind === "invite_manual");
  const availability = rec.pending.find((p) => p.kind === "availability");
  const refresh = async () => { await reloadIvs(); await reload(); touch(); };
  const before = ["offer_review", "collecting", "shortlist_review"].includes(rec.state);

  return (
    <div className="stack lg">
      {invite && <InviteCard rec={rec} prop={invite} onChange={onChange} />}
      {availability && <AvailabilityCard rec={rec} prop={availability} onChange={onChange} />}
      {before && (
        <Card><Empty icon={<CalendarClock size={20} />} title="Pas encore d'entretien"
          action={<Link className="btn" to={`/recrutements/${rec.id}/candidatures`}>Voir les candidatures</Link>}>
          Les entretiens s'organisent une fois la sélection validée.
        </Empty></Card>
      )}
      {err && <ErrorBox msg={err} />}
      {!before && !data && !err && <Spinner />}
      {IS_DEMO && api.demoFastForward && data?.interviews.some((i) => i.status === "booked" && i.start && Date.parse(i.start) > Date.now()) && (
        <Notice tone="brand" title="Démo : les entretiens sont prévus dans les prochains jours"
          actions={<Button size="sm" onClick={async () => { onChange(await api.demoFastForward!(rec.id)); await reloadIvs(); }}>Passer après les entretiens</Button>}>
          Avancez le temps pour noter les entretiens et voir la suite.
        </Notice>
      )}
      {data && data.interviews.length > 0 && (
        <Card title="Entretiens" flush
          sub={data.online ? (data.free_slots.length ? `Les candidats choisissent leur créneau en ligne · ${plural(data.free_slots.length, "créneau libre", "créneaux libres")}` : "Plus de créneau libre en ligne.") : "Convenez de la date avec chaque personne, puis indiquez-la ici."}
          actions={data.online ? <button className="btn sm" onClick={() => setSlotsModal(true)}><Plus size={14} /> Ajouter des créneaux</button> : undefined}>
          {data.interviews.map((iv) => {
            const [l, t] = IV[iv.status] || [iv.status, ""];
            const past = iv.start ? Date.parse(iv.start) < Date.now() : false;
            return (
              <div className="agenda-item" key={iv.id}>
                <div className="when">
                  {iv.start ? <><span className="small muted cap">{fmtDayShort(iv.start)}</span><b>{fmtTime(iv.start)}</b></>
                    : <span className="small muted">{data.online ? "Choix en cours" : "À convenir"}</span>}
                </div>
                <div className="who">
                  <button className="btn link" style={{ justifyContent: "flex-start" }} onClick={() => setOpen(iv.application_id)}>{iv.name}</button>
                  <span>{iv.status === "invited" && data.online ? <Badge dot>Lien envoyé</Badge>
                    : <Badge tone={iv.status === "booked" && past ? "warn" : t} dot>{iv.status === "booked" && past ? "À noter" : l}</Badge>}</span>
                </div>
                <div className="row" style={{ justifyContent: "flex-end" }}>
                  {iv.status === "invited" && <button className={`btn sm ${data.online ? "ghost" : "primary"}`} onClick={() => setSched(iv)}>Fixer la date</button>}
                  {iv.status === "booked" && !past && <button className="btn sm ghost" onClick={() => setSched(iv)}>Modifier</button>}
                  {iv.status === "booked" && past && <>
                    <Link className="btn sm primary" to={`/recrutements/${rec.id}/debrief?candidat=${iv.application_id}`}>Noter</Link>
                    <Button size="sm" variant="ghost" onClick={async () => { const r = await run(() => api.attendance(iv.id, false)); if (r) await refresh(); }}>Absent(e)</Button>
                  </>}
                  {iv.status === "attended" && <Link className="btn sm ghost" to={`/recrutements/${rec.id}/debrief?candidat=${iv.application_id}`}>{iv.debrief_status === "validated" ? "Voir les notes" : "Noter"}</Link>}
                </div>
              </div>
            );
          })}
        </Card>
      )}
      <GridCard rec={rec} onChange={onChange} />
      {sched && <ScheduleModal iv={sched} defaultLocation={rec.interview_location} onClose={() => setSched(null)} onDone={async () => { setSched(null); await refresh(); }} />}
      {slotsModal && <SlotsModal rec={rec} onClose={() => setSlotsModal(false)} onDone={async () => { setSlotsModal(false); await refresh(); }} />}
      {open && <CandidateDrawer id={open} rec={rec} onClose={() => setOpen(null)} onChanged={refresh} />}
    </div>
  );
}

function InviteCard({ rec, prop, onChange }: { rec: RecruitmentDetail; prop: Proposal; onChange: (r: RecruitmentDetail) => void }) {
  const api = useApi();
  const [edit, setEdit] = useState(false);
  const [subject, setSubject] = useState<string>(prop.payload.subject);
  const [body, setBody] = useState<string>(prop.payload.body);
  const n = rec.counts.shortlisted || prop.payload.application_ids.length;
  return (
    <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>{n > 1 ? `Invitez les ${n} personnes retenues` : "Invitez la personne retenue"}</h2></>}
      sub="Un e-mail leur demande leurs disponibilités ; les réponses arrivent dans votre boîte mail. Vous fixerez ensuite la date ici."
      foot={<>
        {!edit && <button className="btn ghost" onClick={() => setEdit(true)}>Modifier le message</button>}
        <Button variant="primary" done="Invitations envoyées" onClick={async () => onChange(await api.accept(rec.id, prop.id, { subject, body }))}>Envoyer les invitations</Button>
      </>}>
      {edit ? (
        <>
          <Field label="Objet"><input className="input" value={subject} onChange={(e) => setSubject(e.target.value)} /></Field>
          <Field label="Message" hint={<><span className="kbd">{"{prénom}"}</span> <span className="kbd">{"{poste}"}</span> <span className="kbd">{"{entreprise}"}</span> sont remplacés pour chacun.</>}>
            <textarea className="textarea" rows={9} value={body} onChange={(e) => setBody(e.target.value)} />
          </Field>
        </>
      ) : (
        <div className="stack sm" style={{ padding: 14, borderRadius: 8, background: "var(--surface-2)", border: "1px solid var(--line)" }}>
          <b className="small strong">{subject}</b>
          <div className="pre small muted" style={{ maxHeight: 120, overflow: "hidden" }}>{body}</div>
        </div>
      )}
    </Card>
  );
}

type Range = { start: string; end: string };

function RangesEditor({ ranges, onChange }: { ranges: Range[]; onChange: (r: Range[]) => void }) {
  const [day, setDay] = useState("");
  const [from, setFrom] = useState("09:00");
  const [to, setTo] = useState("12:00");
  const add = () => {
    if (!day) return;
    const mk = (t: string) => new Date(`${day}T${t}:00`).toISOString();
    onChange([...ranges, { start: mk(from), end: mk(to) }].sort((a, b) => a.start.localeCompare(b.start)));
  };
  return (
    <div className="stack">
      <ul className="chan-list">
        {ranges.map((r, i) => (
          <li key={i}>
            <CalendarClock size={16} color="var(--muted)" />
            <span className="grow"><span className="small strong cap">{fmtDay(r.start)}</span><span className="xs muted tnum">{fmtTime(r.start)} – {fmtTime(r.end)}</span></span>
            <button className="btn ghost sm icon" aria-label="Retirer la plage" onClick={() => onChange(ranges.filter((_, j) => j !== i))}><Trash2 size={15} /></button>
          </li>
        ))}
      </ul>
      <div className="row">
        <input type="date" className="input" style={{ width: "auto" }} aria-label="Jour" value={day} onChange={(e) => setDay(e.target.value)} />
        <input type="time" className="input" style={{ width: "auto" }} aria-label="De" value={from} onChange={(e) => setFrom(e.target.value)} />
        <input type="time" className="input" style={{ width: "auto" }} aria-label="À" value={to} onChange={(e) => setTo(e.target.value)} />
        <button className="btn sm" onClick={add} disabled={!day}><Plus size={14} /> Ajouter</button>
      </div>
    </div>
  );
}

function AvailabilityCard({ rec, prop, onChange }: { rec: RecruitmentDetail; prop: Proposal; onChange: (r: RecruitmentDetail) => void }) {
  const api = useApi();
  const [ranges, setRanges] = useState<Range[]>(prop.payload.suggested || []);
  const [location, setLocation] = useState<string>(prop.payload.location || "");
  const [minutes, setMinutes] = useState<number>(prop.payload.minutes || 45);
  return (
    <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Vos disponibilités pour les entretiens</h2></>}
      sub="Chaque personne retenue reçoit un lien pour choisir son créneau, puis une confirmation et un rappel la veille."
      foot={<Button variant="primary" disabled={!ranges.length} done="Invitations envoyées" onClick={async () => onChange(await api.accept(rec.id, prop.id, { ranges, location, minutes }))}>Envoyer les invitations</Button>}>
      <RangesEditor ranges={ranges} onChange={setRanges} />
      <div className="grid c2">
        <Field label="Lieu ou lien visio"><input className="input" value={location} onChange={(e) => setLocation(e.target.value)} /></Field>
        <Field label="Durée d'un entretien">
          <select className="select" value={minutes} onChange={(e) => setMinutes(Number(e.target.value))}>{[30, 45, 60, 90].map((m) => <option key={m} value={m}>{m} minutes</option>)}</select>
        </Field>
      </div>
    </Card>
  );
}

function SlotsModal({ rec, onClose, onDone }: { rec: RecruitmentDetail; onClose: () => void; onDone: () => void }) {
  const api = useApi();
  const run = useAction();
  const [ranges, setRanges] = useState<Range[]>([]);
  return (
    <Modal title="Ajouter des créneaux" sub="Ils s'ajoutent aux créneaux proposés en ligne aux candidats." onClose={onClose}
      foot={<><button className="btn" onClick={onClose}>Annuler</button>
        <Button variant="primary" disabled={!ranges.length} onClick={async () => { const r = await run(() => api.addSlots(rec.id, ranges), "Créneaux ajoutés"); if (r) onDone(); }}>Ajouter</Button></>}>
      <RangesEditor ranges={ranges} onChange={setRanges} />
    </Modal>
  );
}

const ANCHOR_LABEL = { "1": "1 · Insuffisant", "2": "2 · Correct", "3": "3 · Solide" } as const;

/** Questions d'entretien : prêtes d'office, mêmes questions pour tous. */
function GridCard({ rec, onChange }: { rec: RecruitmentDetail; onChange: (r: RecruitmentDetail) => void }) {
  const api = useApi();
  const [show, setShow] = useState(false);
  const [edit, setEdit] = useState<GridQuestion[] | null>(null);
  const grid = rec.grid;
  if (!grid) return null;
  const locked = rec.counts.noted > 0;
  const qs = edit || grid.questions;
  const setQ = (i: number, patch: Partial<GridQuestion>) => setEdit(qs.map((q, j) => (j === i ? { ...q, ...patch } : q)));
  const print = api.gridPrintUrl(rec.id);
  return (
    <Card title="Questions d'entretien" sub={`${plural(grid.questions.length, "question")} liées au poste, les mêmes pour chaque personne, avec repères de notation.`}
      actions={<>
        {print && !IS_DEMO && <a className="btn sm ghost" href={print} target="_blank" rel="noreferrer"><Printer size={14} /> Imprimer</a>}
        <button className="btn sm" aria-expanded={show} onClick={() => { setShow(!show); setEdit(null); }}>{show ? "Masquer" : "Voir les questions"}</button>
      </>}>
      {show && (
        <>
          <ol className="gridq">
            {qs.map((q, i) => (
              <li key={q.id || i}>
                <div className="gq-text">
                  <span className="gq-num tnum">{i + 1}</span>
                  {edit ? <textarea className="textarea" rows={2} aria-label={`Question ${i + 1}`} value={q.text} onChange={(e) => setQ(i, { text: e.target.value })} />
                    : <b className="strong">{q.text}</b>}
                </div>
                <div className="gq-anchors">
                  {(["1", "2", "3"] as const).map((k) => (
                    <div key={k} className={`gq-a s${k}`}>
                      <span className="xs strong">{ANCHOR_LABEL[k]}</span>
                      {edit ? <textarea className="textarea" rows={2} aria-label={`Repère ${k} de la question ${i + 1}`} value={q.anchors[k]} onChange={(e) => setQ(i, { anchors: { ...q.anchors, [k]: e.target.value } })} />
                        : <span className="small">{q.anchors[k]}</span>}
                    </div>
                  ))}
                </div>
              </li>
            ))}
          </ol>
          {!locked && (edit ? (
            <div className="row">
              <Button variant="primary" done="Questions enregistrées" onClick={async () => { onChange(await api.saveGrid(rec.id, edit)); setEdit(null); }}>Enregistrer</Button>
              <button className="btn ghost" onClick={() => setEdit(null)}>Annuler</button>
            </div>
          ) : <div className="row"><button className="btn sm" onClick={() => setEdit(grid.questions)}><Pencil size={14} /> Modifier les questions</button></div>)}
        </>
      )}
    </Card>
  );
}
