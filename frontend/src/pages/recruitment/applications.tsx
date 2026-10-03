import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Columns3, List, Mail, UserPlus, Users, UserX } from "lucide-react";
import type { ApplicationItem, PipelineStage, Proposal } from "../../api/types";
import { useAction, useApi, useHas, useLoad, useToast } from "../../lib/ctx";
import { fmtTime, isClosed, plural } from "../../lib/format";
import { Button, Card, Empty, ErrorBox, Modal, Segmented, Spinner } from "../../ui/kit";
import type { PageProps } from "../Recruitment";
import { BulkModal, CandidateDrawer, CandidatesTable, SelectionBar, useFilteredApps, useInvite } from "./candidates";
import { AddCandidateModal, PipelineBoard, stageOf } from "./pipeline";
import { ScheduleModal } from "./shared";

type View = "pipeline" | "liste";
const VIEW_KEY = "wayloop.candidatures.vue";
function storedView(): View {
  try {
    return localStorage.getItem(VIEW_KEY) === "liste" ? "liste" : "pipeline";
  } catch {
    return "pipeline";
  }
}

export function ApplicationsPage({ rec, onChange, reload }: PageProps) {
  const api = useApi();
  const nav = useNavigate();
  const run = useAction();
  const notify = useToast();
  const hasAutomations = useHas("automations");
  const [apps, err, reloadApps] = useLoad(() => api.listApplications(rec.id), [rec.id, rec.state, rec.applications, rec.busy.length]);
  const [auto] = useLoad(() => api.automations(), [rec.id]);
  const [view, setView] = useState<View>(storedView);
  const [sel, setSel] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [modal, setModal] = useState<{ mode: "email" | "reject"; ids: string[] } | null>(null);
  const [adding, setAdding] = useState(false);
  const [schedule, setSchedule] = useState<ApplicationItem | null>(null);
  const [hire, setHire] = useState<ApplicationItem | null>(null);
  const { list, toolbar } = useFilteredApps(apps);
  const refresh = async () => { setSel([]); await reloadApps(); await reload(); };
  const { canInvite, invite, node } = useInvite(rec, refresh);
  const startProp = rec.pending.find((p) => p.kind === "start_screening");
  const closed = isClosed(rec.state);
  const shortlistProp = rec.pending.find((p) => p.kind === "shortlist");
  const autoReject = hasAutomations && !!auto?.auto_reject;
  const chooseView = (v: View) => {
    setView(v);
    try { localStorage.setItem(VIEW_KEY, v); } catch { /* préférence non conservée */ }
  };

  /** « Refusé » : remerciement automatique (annulable) avec l'offre Pro, sinon message relu puis envoyé. */
  const reject = async (ids: string[]) => {
    if (!autoReject) return setModal({ mode: "reject", ids });
    const r = await run(() => api.bulk(rec.id, { application_ids: ids, action: "reject" }));
    if (r) {
      notify(r.due_at ? `Remerciement programmé à ${fmtTime(r.due_at)} : vous pouvez annuler d'ici là` : "Réponse envoyée");
      await refresh();
    }
  };
  const move = async (a: ApplicationItem, to: PipelineStage) => {
    if (to === "refuse") return reject([a.id]);
    if (to === "entretien") {
      if (a.interview?.status === "invited") return setSchedule(a);
      return notify(rec.state === "scheduling" ? "Envoyez d'abord les invitations, page Entretiens." : "Présélectionnez puis invitez la personne d'abord.", "bad");
    }
    if (to === "embauche") {
      if (["interviewing", "decision"].includes(rec.state)) return setHire(a);
      return notify("La décision se prend après les entretiens.", "bad");
    }
    const r = await run(() => api.pipelineMove(rec.id, a.id, to));
    if (r) { notify(r.message); await refresh(); }
  };
  const undo = async (a: ApplicationItem) => {
    const r = await run(() => api.undoRejection(a.id), "Refus annulé : aucun message n'est parti");
    if (r) await refresh();
  };

  if (rec.state === "offer_review") {
    return <Card><Empty icon={<Users size={20} />} title="L'offre n'est pas encore publiée" action={<Link className="btn primary" to={`/recrutements/${rec.id}/offre`}>Voir l'offre</Link>}>Les candidatures arrivent ici dès sa publication.</Empty></Card>;
  }
  if (err) return <ErrorBox msg={err} />;
  if (!apps) return <Spinner />;
  if (rec.busy.length) return <Card className="highlight"><Spinner label="Préparation de la synthèse des candidatures…" /></Card>;
  if (shortlistProp && view === "liste") return <ShortlistReview {...{ rec, onChange, prop: shortlistProp, onView: () => chooseView("pipeline") }} />;

  const proposed: string[] = shortlistProp?.payload.application_ids || [];
  const suggested: string[] = shortlistProp?.payload.suggested || [];
  return (
    <div className="stack lg">
      {shortlistProp ? (
        <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Validez la sélection</h2></>}
          sub={`${shortlistProp.summary || ""} Glissez des cartes vers « Présélectionné » ou « À évaluer » pour ajuster.`}
          foot={<>
            <span className="small muted" style={{ marginRight: "auto" }}>{plural(proposed.length, "personne")} à rencontrer</span>
            <Button variant="primary" disabled={!proposed.length} onClick={async () => {
              onChange(await api.accept(rec.id, shortlistProp.id, { application_ids: proposed }));
              nav(`/recrutements/${rec.id}/entretiens`);
            }}>Valider la sélection</Button>
          </>} />
      ) : startProp ? (
        <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>{startProp.title}</h2></>} sub={startProp.summary || undefined}
          foot={<><Button variant="ghost" onClick={async () => onChange(await api.refuse(rec.id, startProp.id))}>Attendre d'autres candidatures</Button>
            <Button variant="primary" onClick={async () => onChange(await api.accept(rec.id, startProp.id))}>Préparer la sélection</Button></>} />
      ) : rec.state === "collecting" && apps.length > 0 && (
        <div className="row between">
          <span className="small muted">La sélection vous est proposée dès 5 candidatures, ou au bout d'une semaine. Vous pouvez aussi glisser vos favoris vers « Présélectionné ».</span>
          <Button size="sm" onClick={async () => onChange(await api.startScreening(rec.id))}>Préparer la sélection maintenant</Button>
        </div>
      )}
      <div className="row between">
        <Segmented<View> label="Affichage" value={view} onChange={chooseView}
          items={[{ id: "pipeline", label: <span className="row" style={{ gap: 6 }}><Columns3 size={14} /> Pipeline</span> },
            { id: "liste", label: <span className="row" style={{ gap: 6 }}><List size={14} /> Liste</span> }]} />
        {!closed && <button className="btn sm" onClick={() => setAdding(true)}><UserPlus size={14} /> Ajouter un candidat</button>}
      </div>
      {apps.length === 0 ? (
        <Card><Empty icon={<Users size={20} />} title="Aucune candidature pour l'instant">
          L'offre est en ligne. Publiez-la aussi sur LinkedIn, Indeed et France Travail (textes prêts dans la page Offre) ; une candidature reçue ailleurs s'ajoute ici avec « Ajouter un candidat ».
        </Empty></Card>
      ) : view === "pipeline" ? (
        <PipelineBoard rec={rec} apps={apps} suggested={suggested} onOpen={setOpen} onMove={move} onUndo={undo}
          onAnswerWaiting={(ids) => setModal({ mode: "reject", ids })} />
      ) : (
        <Card title={toolbar} flush>
          <CandidatesTable apps={list} criteria={rec.profile.criteria} selected={sel} onSelect={closed ? undefined : setSel} onOpen={setOpen} />
        </Card>
      )}
      {sel.length > 0 && view === "liste" && (
        <SelectionBar count={sel.length} onClear={() => setSel([])}>
          {canInvite && <button className="btn sm" onClick={() => invite(sel)}><UserPlus size={14} /> Inviter en entretien</button>}
          <button className="btn sm" onClick={() => setModal({ mode: "email", ids: sel })}><Mail size={14} /> Écrire</button>
          <button className="btn sm" onClick={() => reject(sel)}><UserX size={14} /> Ne pas retenir</button>
        </SelectionBar>
      )}
      {modal && <BulkModal rec={rec} ids={modal.ids} mode={modal.mode} autoReject={autoReject} onClose={() => setModal(null)} onDone={async () => { setModal(null); await refresh(); }} />}
      {adding && <AddCandidateModal rec={rec} onClose={() => setAdding(false)} onDone={async () => { setAdding(false); await refresh(); }} />}
      {schedule?.interview && (
        <ScheduleModal iv={{ id: schedule.interview.id, name: schedule.name, start: schedule.interview.start, location: schedule.interview.location }}
          defaultLocation={rec.interview_location} onClose={() => setSchedule(null)} onDone={async () => { setSchedule(null); await refresh(); }} />
      )}
      {hire && (
        <Modal title={`Recruter ${hire.name} ?`} onClose={() => setHire(null)}
          sub="Les réponses aux autres candidats sont préparées : vous les relisez avant l'envoi, page Décision."
          foot={<><button className="btn" onClick={() => setHire(null)}>Annuler</button>
            <Button variant="primary" onClick={async () => {
              const r = await run(() => api.decide(rec.id, hire.id));
              if (r) { setHire(null); onChange(r); nav(`/recrutements/${rec.id}/decision`); }
            }}>Recruter cette personne</Button></>}>
          <p className="muted">Si des entretiens restent à noter, vous pourrez encore les compléter ; la décision est enregistrée dans l'historique.</p>
        </Modal>
      )}
      {node}
      {open && <CandidateDrawer id={open} rec={rec} onClose={() => { setOpen(null); void reloadApps(); }} onChanged={refresh} onReject={(id) => reject([id])} />}
    </div>
  );
}

function ShortlistReview({ rec, onChange, prop, onView }: Omit<PageProps, "reload"> & { prop: Proposal; onView: () => void }) {
  const api = useApi();
  const nav = useNavigate();
  const [apps] = useLoad(() => api.listApplications(rec.id), [rec.id, prop.id]);
  const proposed: string[] = prop.payload.application_ids || [];
  const [sel, setSel] = useState<string[]>(proposed);
  const [open, setOpen] = useState<string | null>(null);
  const { list, toolbar } = useFilteredApps(apps);
  if (!apps) return <Spinner />;
  const added = sel.filter((id) => !proposed.includes(id)).length;
  return (
    <div className="stack lg">
      <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>Choisissez qui rencontrer</h2></>} sub={prop.summary || undefined}
        foot={<>
          <span className="small muted" style={{ marginRight: "auto" }}>{plural(sel.length, "personne")} à rencontrer{added ? ` · dont ${added} ajoutée${added > 1 ? "s" : ""} par vous` : ""}</span>
          <button className="btn ghost" onClick={onView}><Columns3 size={16} /> Voir le pipeline</button>
          <Button variant="primary" disabled={!sel.length} onClick={async () => {
            onChange(await api.accept(rec.id, prop.id, { application_ids: sel }));
            nav(`/recrutements/${rec.id}/entretiens`);
          }}>Valider la sélection</Button>
        </>} />
      <Card title={toolbar} flush>
        <CandidatesTable apps={list} criteria={rec.profile.criteria} selected={sel} onSelect={setSel} onOpen={setOpen} showStage={false} />
      </Card>
      {open && <CandidateDrawer id={open} rec={rec} onClose={() => setOpen(null)} />}
    </div>
  );
}

export { stageOf };
