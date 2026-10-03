import { useMemo, useState } from "react";
import { MessageSquare, MoveRight, UserPlus } from "lucide-react";
import type { ApplicationItem, PipelineStage, RecruitmentDetail } from "../../api/types";
import { useAction, useApi, useToast } from "../../lib/ctx";
import { fmtShort, fmtTime, MANUAL_SOURCES, PIPELINE, relDays, SOURCE_LABELS } from "../../lib/format";
import { Badge, Button, Field, Modal } from "../../ui/kit";
import { GroupBadge } from "./candidates";

/** Colonne d'une candidature (le serveur l'indique ; repli pour les anciennes données). */
export function stageOf(a: ApplicationItem): PipelineStage {
  if (a.stage) return a.stage;
  if (a.status === "hired") return "embauche";
  if (a.status === "rejected" || a.status === "not_shortlisted") return "refuse";
  if (a.status === "booked" || a.status === "interviewed") return "entretien";
  if (a.status === "shortlisted" || a.status === "invited") return "preselectionne";
  return a.seen ? "a_evaluer" : "recu";
}

export type MoveHandler = (a: ApplicationItem, to: PipelineStage) => void;

/** Où peut aller une carte depuis sa colonne (mêmes règles que le serveur). */
export function targetsFor(a: ApplicationItem, rec: RecruitmentDetail): PipelineStage[] {
  const from = stageOf(a);
  const final = a.status === "hired" || (a.status === "rejected" && !a.rejection_due_at) || a.status === "withdrawn";
  if (final || ["closed", "abandoned"].includes(rec.state)) return [];
  const out: PipelineStage[] = [];
  if (from === "recu") out.push("a_evaluer");
  if (["recu", "a_evaluer"].includes(from) || a.status === "not_shortlisted") out.push("preselectionne");
  if (from === "preselectionne" && ["received", "screened"].includes(a.status)) out.push("a_evaluer");
  if (from === "refuse" && a.rejection_due_at) out.push("a_evaluer");
  if (a.interview?.status === "invited") out.push("entretien");
  if (["interviewing", "decision"].includes(rec.state) && ["booked", "interviewed", "invited"].includes(a.status)) out.push("embauche");
  if (from !== "refuse") out.push("refuse");
  return out;
}

export function PipelineBoard({ rec, apps, suggested, onOpen, onMove, onUndo, onAnswerWaiting }: {
  rec: RecruitmentDetail; apps: ApplicationItem[]; suggested: string[];
  onOpen: (id: string) => void; onMove: MoveHandler; onUndo: (a: ApplicationItem) => void; onAnswerWaiting: (ids: string[]) => void;
}) {
  const [over, setOver] = useState<PipelineStage | null>(null);
  const cols = useMemo(() => {
    const m: Record<PipelineStage, ApplicationItem[]> = { recu: [], a_evaluer: [], preselectionne: [], entretien: [], refuse: [], embauche: [] };
    apps.forEach((a) => m[stageOf(a)].push(a));
    return m;
  }, [apps]);
  const byId = useMemo(() => Object.fromEntries(apps.map((a) => [a.id, a])), [apps]);
  const waiting = cols.refuse.filter((a) => a.status === "not_shortlisted").map((a) => a.id);
  return (
    <div className="kanban" role="list" aria-label="Pipeline des candidatures">
      {PIPELINE.map((col) => (
        <section key={col.id} className={`kcol ${over === col.id ? "over" : ""}`} role="listitem" aria-label={col.label}
          onDragOver={(e) => { e.preventDefault(); setOver(col.id); }} onDragLeave={() => setOver(null)}
          onDrop={(e) => {
            e.preventDefault();
            setOver(null);
            const a = byId[e.dataTransfer.getData("text/plain")];
            if (a && stageOf(a) !== col.id) onMove(a, col.id);
          }}>
          <header className="kcol-head" title={col.hint}>
            <span className="strong small">{col.label}</span>
            <span className="count tnum">{cols[col.id].length}</span>
          </header>
          {col.id === "refuse" && waiting.length > 0 && (
            <button className="btn sm kcol-action" onClick={() => onAnswerWaiting(waiting)}>Répondre aux {waiting.length} en attente</button>
          )}
          <div className="kcol-body">
            {cols[col.id].map((a) => (
              <KCard key={a.id} a={a} rec={rec} suggested={suggested.includes(a.id)} onOpen={onOpen} onMove={onMove} onUndo={onUndo} />
            ))}
            {!cols[col.id].length && <span className="kempty">{col.hint}</span>}
          </div>
        </section>
      ))}
    </div>
  );
}

function KCard({ a, rec, suggested, onOpen, onMove, onUndo }: {
  a: ApplicationItem; rec: RecruitmentDetail; suggested: boolean; onOpen: (id: string) => void; onMove: MoveHandler; onUndo: (a: ApplicationItem) => void;
}) {
  const [menu, setMenu] = useState(false);
  const targets = targetsFor(a, rec);
  const st = stageOf(a);
  const pendingShortlist = st === "preselectionne" && ["received", "screened"].includes(a.status);
  return (
    <article className={`kcard ${st === "recu" ? "new" : ""}`} draggable={targets.length > 0} tabIndex={0}
      onDragStart={(e) => { e.dataTransfer.setData("text/plain", a.id); e.dataTransfer.effectAllowed = "move"; }}
      onClick={() => onOpen(a.id)} onKeyDown={(e) => { if (e.key === "Enter") onOpen(a.id); }} aria-label={a.name}>
      <div className="row between" style={{ gap: 6, flexWrap: "nowrap" }}>
        <b className="kname">{a.name}</b>
        {targets.length > 0 && (
          <div className="menu" onClick={(e) => e.stopPropagation()}>
            <button className="btn ghost sm icon" aria-label={`Déplacer ${a.name}`} aria-expanded={menu} onClick={() => setMenu(!menu)}><MoveRight size={15} /></button>
            {menu && (
              <div className="menu-list" role="menu">
                {targets.map((t) => (
                  <button key={t} role="menuitem" className={`menu-item ${t === "refuse" ? "danger" : ""}`} onClick={() => { setMenu(false); onMove(a, t); }}>
                    {PIPELINE.find((p) => p.id === t)!.label}
                  </button>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
      <span className="xs muted">{SOURCE_LABELS[a.source] || a.source} · {relDays(a.created_at)}</span>
      <div className="row kbadges">
        {st === "recu" && <Badge tone="brand">Nouveau</Badge>}
        {a.group && <GroupBadge g={a.group} />}
        {pendingShortlist && <Badge tone="brand" title="Dans la sélection à valider">{suggested ? "Suggéré · à valider" : "À valider"}</Badge>}
        {a.awaiting_answers && !a.no_email && st !== "refuse" && <Badge title="Le candidat n'a pas encore répondu aux questions du poste">Questions à remplir</Badge>}
        {a.no_email && <Badge tone="warn" title="Pas d'adresse e-mail : informez la personne vous-même (RGPD)">Sans e-mail</Badge>}
        {a.status === "not_shortlisted" && <Badge tone="warn">Réponse à envoyer</Badge>}
        {a.interview?.status === "invited" && <Badge>Date à fixer</Badge>}
        {a.status === "booked" && a.interview?.start && <Badge tone="brand">{fmtShort(a.interview.start)}</Badge>}
        {a.status === "interviewed" && <Badge tone="violet">Entretien fait</Badge>}
        {!!a.notes_count && <span className="xs muted row" style={{ gap: 3 }}><MessageSquare size={12} />{a.notes_count}</span>}
      </div>
      {a.rejection_due_at && !a.rejection_sent_at && (
        <div className="kdue" onClick={(e) => e.stopPropagation()}>
          <span className="xs" title="Message de remerciement programmé : rien n'est parti tant que l'heure n'est pas passée">Remerciement prévu à {fmtTime(a.rejection_due_at)}</span>
          <button className="btn link sm" onClick={() => onUndo(a)}>Annuler</button>
        </div>
      )}
    </article>
  );
}

/** Candidature reçue hors formulaire : message LinkedIn, appel, CV remis en main propre… */
export function AddCandidateModal({ rec, onClose, onDone }: { rec: RecruitmentDetail; onClose: () => void; onDone: () => void }) {
  const api = useApi();
  const run = useAction();
  const notify = useToast();
  const [f, setF] = useState({ first_name: "", last_name: "", email: "", phone: "", source: "linkedin", message: "", note: "" });
  const [cv, setCv] = useState<File | null>(null);
  const [ack, setAck] = useState(true);
  const set = (k: keyof typeof f, v: string) => setF({ ...f, [k]: v });
  const hasQuestions = rec.profile.criteria.length > 0 || (rec.profile.questions || []).length > 0;
  return (
    <Modal size="lg" title="Ajouter un candidat" onClose={onClose}
      sub="Pour une candidature reçue ailleurs : message LinkedIn, e-mail, appel, CV déposé. Elle rejoint le pipeline, provenance indiquée."
      foot={<><button className="btn" onClick={onClose}>Annuler</button>
        <Button variant="primary" icon={<UserPlus size={16} />} disabled={!f.first_name.trim() || !f.last_name.trim()} onClick={async () => {
          const fd = new FormData();
          Object.entries(f).forEach(([k, v]) => v.trim() && fd.append(k, v.trim()));
          fd.append("send_ack", String(ack && !!f.email.trim()));
          if (cv) fd.append("cv", cv);
          const r = await run(() => api.addCandidate(rec.id, fd));
          if (r) { notify(f.email.trim() && ack ? "Candidat ajouté : accusé de réception envoyé" : "Candidat ajouté"); onDone(); }
        }}>Ajouter</Button></>}>
      <div className="grid c2">
        <Field label="Prénom" htmlFor="ac-first"><input id="ac-first" className="input" value={f.first_name} onChange={(e) => set("first_name", e.target.value)} /></Field>
        <Field label="Nom" htmlFor="ac-last"><input id="ac-last" className="input" value={f.last_name} onChange={(e) => set("last_name", e.target.value)} /></Field>
      </div>
      <div className="grid c2">
        <Field label="E-mail" htmlFor="ac-email" hint="Recommandé : la personne reçoit l'information sur ses données.">
          <input id="ac-email" className="input" type="email" value={f.email} onChange={(e) => set("email", e.target.value)} />
        </Field>
        <Field label="Téléphone" htmlFor="ac-phone"><input id="ac-phone" className="input" type="tel" value={f.phone} onChange={(e) => set("phone", e.target.value)} /></Field>
      </div>
      <Field label="Provenance" htmlFor="ac-src">
        <select id="ac-src" className="select" value={f.source} onChange={(e) => set("source", e.target.value)}>
          {MANUAL_SOURCES.map((s) => <option key={s.id} value={s.id}>{s.label}</option>)}
        </select>
      </Field>
      <Field label="Message du candidat" htmlFor="ac-msg" hint="Collez son message LinkedIn ou résumez l'appel.">
        <textarea id="ac-msg" className="textarea" rows={3} value={f.message} onChange={(e) => set("message", e.target.value)} />
      </Field>
      <Field label="CV" htmlFor="ac-cv" hint="PDF, DOCX ou TXT. Facultatif.">
        <input id="ac-cv" type="file" accept=".pdf,.docx,.txt" onChange={(e) => setCv(e.target.files?.[0] || null)} />
      </Field>
      <Field label="Votre note" htmlFor="ac-note" hint="Visible seulement par vous et votre équipe.">
        <textarea id="ac-note" className="textarea" rows={2} value={f.note} onChange={(e) => set("note", e.target.value)} />
      </Field>
      <label className="check">
        <input type="checkbox" checked={ack && !!f.email.trim()} disabled={!f.email.trim()} onChange={(e) => setAck(e.target.checked)} />
        <span>Envoyer l'accusé de réception (information sur ses données){hasQuestions ? " avec le lien pour répondre aux questions du poste" : ""}</span>
      </label>
    </Modal>
  );
}
