import { useState } from "react";
import { Link } from "react-router-dom";
import { CalendarDays, MapPin } from "lucide-react";
import type { InterviewItem } from "../api/types";
import { useApi, useLoad, useSession } from "../lib/ctx";
import { fmtDayShort, fmtTime } from "../lib/format";
import { Card, Empty, ErrorBox, PageHeader, Spinner } from "../ui/kit";
import { ScheduleModal } from "./recruitment/shared";

/** Une ligne d'agenda : quand, qui, pour quel poste, et le geste utile. */
export function AgendaRow({ iv, action }: { iv: InterviewItem; action?: React.ReactNode }) {
  return (
    <div className="agenda-item">
      <div className="when">
        {iv.start ? <><span className="small muted cap">{fmtDayShort(iv.start)}</span><b>{fmtTime(iv.start)}</b></>
          : <span className="small muted">{iv.self_booking ? "Lien envoyé" : "Date à fixer"}</span>}
      </div>
      <div className="who">
        <b>{iv.name}</b>
        <span className="small muted"><Link to={`/recrutements/${iv.recruitment_id}/entretiens`}>{iv.recruitment_title}</Link>
          {iv.start && iv.location ? <> · <MapPin size={12} style={{ verticalAlign: "-1px" }} /> {iv.location}</> : null}</span>
      </div>
      <div className="row" style={{ justifyContent: "flex-end" }}>{action}</div>
    </div>
  );
}

export default function Agenda() {
  const api = useApi();
  const { touch } = useSession();
  const [a, err, reload] = useLoad(() => api.agenda(), []);
  const [sched, setSched] = useState<InterviewItem | null>(null);
  if (err) return <main className="content"><ErrorBox msg={err} /></main>;
  if (!a) return <main className="content"><Spinner /></main>;
  const nothing = !a.upcoming.length && !a.to_schedule.length && !a.to_note.length;
  const manual = a.to_schedule.filter((iv) => !iv.self_booking);
  const online = a.to_schedule.filter((iv) => iv.self_booking);
  return (
    <main className="content narrow">
      <PageHeader title="Entretiens" sub="Tous vos recrutements en cours, au même endroit." />
      {nothing && <Card><Empty icon={<CalendarDays size={20} />} title="Aucun entretien pour l'instant">Les entretiens apparaissent ici dès que vous invitez des candidats.</Empty></Card>}
      {manual.length > 0 && (
        <Card title="Dates à fixer" sub="Convenez de la date avec la personne, puis indiquez-la : elle reçoit la confirmation." flush>
          {manual.map((iv) => <AgendaRow key={iv.id} iv={iv} action={<button className="btn sm primary" onClick={() => setSched(iv)}>Fixer la date</button>} />)}
        </Card>
      )}
      {online.length > 0 && (
        <Card title="Créneau en cours de choix" sub="Ces personnes ont reçu un lien pour choisir leur créneau en ligne." flush>
          {online.map((iv) => <AgendaRow key={iv.id} iv={iv} action={<button className="btn sm ghost" onClick={() => setSched(iv)}>Fixer la date</button>} />)}
        </Card>
      )}
      {a.upcoming.length > 0 && (
        <Card title="À venir" flush>
          {a.upcoming.map((iv) => <AgendaRow key={iv.id} iv={iv} action={<button className="btn sm ghost" onClick={() => setSched(iv)}>Modifier</button>} />)}
        </Card>
      )}
      {a.to_note.length > 0 && (
        <Card title="À noter" sub="Notez chaque entretien pendant qu'il est frais." flush>
          {a.to_note.map((iv) => (
            <AgendaRow key={iv.id} iv={iv} action={<Link className="btn sm primary" to={`/recrutements/${iv.recruitment_id}/debrief?candidat=${iv.application_id}`}>Noter</Link>} />
          ))}
        </Card>
      )}
      {sched && <ScheduleModal iv={sched} onClose={() => setSched(null)} onDone={async () => { setSched(null); await reload(); touch(); }} />}
    </main>
  );
}
