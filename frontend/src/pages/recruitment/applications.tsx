import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Mail, UserPlus, Users, UserX } from "lucide-react";
import type { Proposal } from "../../api/types";
import { useApi, useLoad } from "../../lib/ctx";
import { isClosed, plural } from "../../lib/format";
import { Button, Card, Empty, ErrorBox, Spinner } from "../../ui/kit";
import type { PageProps } from "../Recruitment";
import { BulkModal, CandidateDrawer, CandidatesTable, SelectionBar, useFilteredApps, useInvite } from "./candidates";

export function ApplicationsPage({ rec, onChange, reload }: PageProps) {
  const api = useApi();
  const [apps, err, reloadApps] = useLoad(() => api.listApplications(rec.id), [rec.id, rec.state, rec.applications, rec.busy.length]);
  const [sel, setSel] = useState<string[]>([]);
  const [open, setOpen] = useState<string | null>(null);
  const [modal, setModal] = useState<"email" | "reject" | null>(null);
  const { list, toolbar } = useFilteredApps(apps);
  const refresh = async () => { setSel([]); await reloadApps(); await reload(); };
  const { canInvite, invite, node } = useInvite(rec, refresh);
  const startProp = rec.pending.find((p) => p.kind === "start_screening");
  const closed = isClosed(rec.state);
  const shortlistProp = rec.pending.find((p) => p.kind === "shortlist");

  if (rec.state === "offer_review") {
    return <Card><Empty icon={<Users size={20} />} title="L'offre n'est pas encore publiée" action={<Link className="btn primary" to={`/recrutements/${rec.id}/offre`}>Voir l'offre</Link>}>Les candidatures arrivent ici dès sa publication.</Empty></Card>;
  }
  if (err) return <ErrorBox msg={err} />;
  if (!apps) return <Spinner />;
  if (rec.busy.length) return <Card className="highlight"><Spinner label="Préparation de la synthèse des candidatures…" /></Card>;
  if (shortlistProp) return <ShortlistReview {...{ rec, onChange, prop: shortlistProp }} />;

  return (
    <div className="stack lg">
      {startProp ? (
        <Card className="highlight" title={<><span className="eyebrow">À faire</span><h2>{startProp.title}</h2></>} sub={startProp.summary || undefined}
          foot={<><Button variant="ghost" onClick={async () => onChange(await api.refuse(rec.id, startProp.id))}>Attendre d'autres candidatures</Button>
            <Button variant="primary" onClick={async () => onChange(await api.accept(rec.id, startProp.id))}>Préparer la sélection</Button></>} />
      ) : rec.state === "collecting" && apps.length > 0 && (
        <div className="row between">
          <span className="small muted">La sélection vous est proposée dès 5 candidatures, ou au bout d'une semaine.</span>
          <Button size="sm" onClick={async () => onChange(await api.startScreening(rec.id))}>Préparer la sélection maintenant</Button>
        </div>
      )}
      {apps.length === 0 ? (
        <Card><Empty icon={<Users size={20} />} title="Aucune candidature pour l'instant">L'offre est en ligne ; partagez aussi son lien pour aller plus vite.</Empty></Card>
      ) : (
        <Card title={toolbar} flush>
          <CandidatesTable apps={list} criteria={rec.profile.criteria} selected={sel} onSelect={closed ? undefined : setSel} onOpen={setOpen} />
        </Card>
      )}
      {sel.length > 0 && (
        <SelectionBar count={sel.length} onClear={() => setSel([])}>
          {canInvite && <button className="btn sm" onClick={() => invite(sel)}><UserPlus size={14} /> Inviter en entretien</button>}
          <button className="btn sm" onClick={() => setModal("email")}><Mail size={14} /> Écrire</button>
          <button className="btn sm" onClick={() => setModal("reject")}><UserX size={14} /> Ne pas retenir</button>
        </SelectionBar>
      )}
      {modal && <BulkModal rec={rec} ids={sel} mode={modal} onClose={() => setModal(null)} onDone={async () => { setModal(null); await refresh(); }} />}
      {node}
      {open && <CandidateDrawer id={open} rec={rec} onClose={() => setOpen(null)} onChanged={refresh} />}
    </div>
  );
}

function ShortlistReview({ rec, onChange, prop }: Omit<PageProps, "reload"> & { prop: Proposal }) {
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
