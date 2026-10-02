import { useState } from "react";
import { useParams } from "react-router-dom";
import { useAction, useApi, useLoad } from "../../lib/ctx";
import { fmtDate } from "../../lib/format";
import { Badge, Button, Card, ErrorBox, Notice, Spinner } from "../../ui/kit";
import PublicLayout from "./PublicLayout";

const STATUS: Record<string, string> = {
  received: "Reçue", screened: "En cours d'examen", shortlisted: "Retenue pour un entretien", not_shortlisted: "En cours d'examen",
  invited: "Invitation à un entretien", booked: "Entretien prévu", interviewed: "Entretien passé", hired: "Retenue", rejected: "Non retenue", withdrawn: "Retirée",
};
const EVAL: Record<string, string> = { met: "remplit", partial: "en partie", not_met: "ne remplit pas", unknown: "non établi" };

export default function CandidatePage() {
  const { token = "" } = useParams();
  const api = useApi();
  const run = useAction();
  const [d, err] = useLoad(() => api.candidate(token), [token]);
  const [ask, setAsk] = useState(false);
  const [gone, setGone] = useState(false);
  return (
    <PublicLayout company={d?.company} slug={d?.company_slug}>
      {gone ? <Notice tone="ok" title="Vos données ont été supprimées">Votre candidature est retirée et vos informations effacées.</Notice> : <>
        <ErrorBox msg={err} />
        {!d && !err && <Spinner />}
        {d && <div className="stack lg" style={{ maxWidth: 720 }}>
          <div className="stack sm"><h1>Vos données</h1><p className="muted">Ce que {d.company} conserve à votre sujet, et la synthèse établie pour votre candidature.</p></div>
          <Card title="Coordonnées">
            <dl className="dl"><dt>Nom</dt><dd>{d.first_name} {d.last_name}</dd><dt>E-mail</dt><dd>{d.email}</dd>{d.phone && <><dt>Téléphone</dt><dd>{d.phone}</dd></>}
              <dt>Suppression automatique</dt><dd>{fmtDate(d.deletion_due)}</dd><dt>Autres postes</dt><dd>{d.pool_consent ? "Vous acceptez d'être recontacté(e)" : "Non"}</dd></dl>
          </Card>
          {d.applications.map((a, i) => (
            <Card key={i} title={a.title} sub={`Envoyée le ${fmtDate(a.sent_at)}${a.cv_filename ? ` · ${a.cv_filename}` : ""}`} actions={<Badge>{STATUS[a.status] || a.status}</Badge>}>
              {a.evaluations.length > 0 && <div className="stack sm small">{a.evaluations.map((e, j) => <span key={j}><b className="strong">{e.label}</b> : {EVAL[e.status] || e.status} <span className="muted">— {e.justification}</span></span>)}
                <span className="xs muted">Cette synthèse aide l'entreprise à lire les candidatures ; elle ne décide de rien.</span></div>}
            </Card>
          ))}
          <Card title="Retirer ma candidature" sub="Toutes vos données sont supprimées immédiatement, CV compris. Action définitive.">
            {!ask ? <div className="row"><button className="btn danger" onClick={() => setAsk(true)}>Retirer et supprimer mes données</button></div> : (
              <div className="row"><Button variant="danger solid" onClick={async () => { const ok = await run(() => api.withdraw(token).then(() => true)); if (ok) setGone(true); }}>Confirmer la suppression</Button>
                <button className="btn" onClick={() => setAsk(false)}>Annuler</button></div>
            )}
          </Card>
        </div>}
      </>}
    </PublicLayout>
  );
}
