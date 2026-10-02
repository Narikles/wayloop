import { Link } from "react-router-dom";
import type { AuditItem } from "../../api/types";
import { useApi, useLoad } from "../../lib/ctx";
import { fmtShort, SOURCE_LABELS } from "../../lib/format";
import { Card, ErrorBox, Spinner } from "../../ui/kit";
import type { PageProps } from "../Recruitment";

const ACTOR: Record<string, string> = { system: "WayLoop", user: "Vous", candidate: "Candidat" };
const GROUP_FR: Record<string, string> = { meets: "remplit les critères", partial: "en partie", does_not: "ne les remplit pas", unreadable: "CV à lire" };
// Événements techniques regroupés : l'historique reste lisible.
const HIDDEN = new Set(["screening.masked", "screening.criterion_evaluated", "proposal.created", "message.sent", "recruitment.transition"]);

const KIND_FR: Record<string, string> = {
  offer: "publication de l'offre", start_screening: "préparation de la sélection", shortlist: "sélection", invite_manual: "invitations",
  availability: "créneaux d'entretien", decision: "décision", closing_messages: "réponses aux candidats", followup: "suivi",
};

function describe(e: AuditItem): string {
  const d = e.details || {};
  switch (e.action) {
    case "proposal.accepted": case "proposal.modified": case "proposal.refused": return KIND_FR[d.kind] || "";
    case "screening.grouped": return GROUP_FR[d.group] || "";
    case "offer.proposed": return d.by === "user" ? `Version ${d.version}, modifiée par vous` : `Version ${d.version}`;
    case "message.bulk_sent": return `${d.count} message(s)`;
    case "decision.made": return d.outcome === "hired" ? "Embauche" : "Sans embauche";
    case "grid.generated": return `${d.questions} questions`;
    case "shortlist.validated": return `${d.selected} personne(s)`;
    case "application.received": return SOURCE_LABELS[d.source] || d.source || "";
    case "interview.attendance": return d.attended ? "Présent(e)" : "Absent(e)";
    case "followup.answered": return d.still_there ? `Toujours en poste à ${d.months} mois` : `Partie avant ${d.months} mois`;
    default: return "";
  }
}

export function HistoryPage({ rec }: PageProps) {
  const api = useApi();
  const [items, err] = useLoad<AuditItem[]>(() => api.audit(rec.id), [rec.id]);
  if (err) return <ErrorBox msg={err} />;
  if (!items) return <Spinner />;
  const shown = items.filter((e) => !HIDDEN.has(e.action)).reverse();
  return (
    <Card title="Historique" sub="Ce qui a été fait, par qui et quand." flush actions={<Link className="btn sm ghost" to={`/recrutements/${rec.id}`}>Retour</Link>}>
      <div className="table-wrap">
        <table className="table">
          <thead><tr><th>Date</th><th>Par</th><th>Événement</th></tr></thead>
          <tbody>
            {shown.map((e) => (
              <tr key={e.id}>
                <td className="tnum muted nowrap">{fmtShort(e.at)}</td>
                <td>{ACTOR[e.actor_type] || e.actor_type}</td>
                <td>{e.label}{e.subject && <span className="muted"> · {e.subject}</span>}{describe(e) && <span className="muted"> · {describe(e)}</span>}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
