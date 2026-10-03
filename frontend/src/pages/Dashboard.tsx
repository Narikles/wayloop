import { Link } from "react-router-dom";
import { ArrowRight, Briefcase, CalendarDays, Plus } from "lucide-react";
import { useApi, useLoad, useSession } from "../lib/ctx";
import { isClosed, plural } from "../lib/format";
import { Card, Empty, ErrorBox, MiniSteps, PageHeader, Skeleton } from "../ui/kit";
import { AgendaRow } from "./Agenda";

export default function Dashboard() {
  const api = useApi();
  const { me } = useSession();
  const [recs, err] = useLoad(() => api.listRecruitments(), []);
  const [agenda] = useLoad(() => api.agenda(), []);
  const active = (recs || []).filter((r) => !isClosed(r.state));
  const todo = active.filter((r) => r.pending || r.new_applications);
  const first = me?.name?.split(" ")[0];
  const upcoming = agenda?.upcoming.slice(0, 5) || [];

  return (
    <main className="content">
      <PageHeader title={`Bonjour${first ? ` ${first}` : ""}`}
        sub={!recs ? "" : todo.length ? `${plural(todo.length, "recrutement")} ${todo.length > 1 ? "attendent" : "attend"} un geste de votre part.` : "Rien ne vous attend pour l'instant."}
        actions={<Link to="/recrutements/nouveau" className="btn primary"><Plus size={16} /> Nouveau recrutement</Link>} />
      <ErrorBox msg={err} />
      {!recs ? <Skeleton h={160} /> : active.length === 0 ? (
        <Card>
          <Empty icon={<Briefcase size={20} />} title="Aucun recrutement en cours"
            action={<Link to="/recrutements/nouveau" className="btn primary"><Plus size={16} /> Décrire un poste</Link>}>
            Décrivez le poste en une phrase : l'offre, les critères et les questions de présélection sont rédigés pour vous. Toutes les candidatures arrivent ici, au même endroit.
          </Empty>
        </Card>
      ) : (
        <div className="split">
          <div className="stack lg">
            <Card title="À faire" flush>
              {todo.length === 0 ? <p className="muted" style={{ padding: 20 }}>Tout est à jour. Les prochaines étapes apparaîtront ici dès qu'elles seront prêtes.</p> : (
                <ul className="todo-list">
                  {todo.flatMap((r) => [
                    ...(r.pending ? [
                      <li key={`${r.id}-p`}>
                        <span className="dot" aria-hidden />
                        <div className="grow"><b>{r.pending.title}</b><span className="xs muted">{r.title}</span></div>
                        <Link className="btn sm" to={`/recrutements/${r.id}/${r.pending.page || r.page}`}>Ouvrir <ArrowRight size={14} /></Link>
                      </li>] : []),
                    ...(r.new_applications ? [
                      <li key={`${r.id}-n`}>
                        <span className="dot" aria-hidden />
                        <div className="grow"><b>{plural(r.new_applications, "nouvelle candidature", "nouvelles candidatures")} à ouvrir</b><span className="xs muted">{r.title}</span></div>
                        <Link className="btn sm" to={`/recrutements/${r.id}/candidatures`}>Ouvrir <ArrowRight size={14} /></Link>
                      </li>] : []),
                  ])}
                </ul>
              )}
            </Card>
            <Card title="Recrutements en cours" flush actions={<Link to="/recrutements" className="btn sm ghost">Tout voir <ArrowRight size={14} /></Link>}>
              <div className="table-wrap">
                <table className="table">
                  <tbody>
                    {active.map((r) => (
                      <tr key={r.id}>
                        <td><div className="cell-title"><Link className="row-link" to={`/recrutements/${r.id}`}>{r.title}</Link><span className="xs muted">{r.state_label}</span></div></td>
                        <td className="hide-sm"><MiniSteps step={r.step} /></td>
                        <td className="num nowrap">{plural(r.applications, "candidature")}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
          </div>
          <Card title="Prochains entretiens" flush actions={<Link to="/entretiens" className="btn sm ghost">Agenda <ArrowRight size={14} /></Link>}>
            {upcoming.length ? upcoming.map((iv) => <AgendaRow key={iv.id} iv={iv} />)
              : <Empty icon={<CalendarDays size={20} />} title="Aucun entretien prévu" />}
          </Card>
        </div>
      )}
    </main>
  );
}
