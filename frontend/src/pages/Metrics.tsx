import { Link } from "react-router-dom";
import { BarChart3 } from "lucide-react";
import { useApi, useLoad } from "../lib/ctx";
import { SOURCE_LABELS } from "../lib/format";
import { Badge, Card, Empty, ErrorBox, PageHeader, Spinner, Stat } from "../ui/kit";

const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)} %`);
const num = (v: number | null | undefined, unit = "") => (v === null || v === undefined ? "—" : `${v.toLocaleString("fr-FR")}${unit}`);

export default function MetricsPage() {
  const api = useApi();
  const [m, err] = useLoad(() => api.metrics(), []);
  if (err) return <main className="content"><ErrorBox msg={err} /></main>;
  if (!m) return <main className="content"><Spinner /></main>;
  const s = m.summary;
  const sources = Object.entries((s.sources || {}) as Record<string, number>).sort((a, b) => b[1] - a[1]);
  const totalApps = sources.reduce((t, [, v]) => t + v, 0);
  return (
    <main className="content">
      <PageHeader title="Indicateurs" />
      {!m.recruitments.length ? <Card><Empty icon={<BarChart3 size={20} />} title="Pas encore de données">Les indicateurs apparaissent dès votre premier recrutement.</Empty></Card> : (
        <>
          <div className="grid c4">
            <Stat label="Recrutements aboutis" value={num(s.hired)} hint={s.active ? `${s.active} en cours` : undefined} />
            <Stat label="Candidatures par offre" value={num(s.applications_per_offer_median)} hint="Médiane" />
            <Stat label="Délai jusqu'à l'embauche" value={num(s.days_to_close_median, " j")} hint="Médiane, depuis la publication" />
            <Stat label="Présence aux entretiens" value={pct(s.attendance_rate)} />
          </div>
          <div className="split">
            <Card title="Par recrutement" flush>
              <div className="table-wrap">
                <table className="table">
                  <thead><tr><th>Poste</th><th className="num">Candidatures</th><th className="num hide-sm">Présence</th><th>Issue</th></tr></thead>
                  <tbody>
                    {m.recruitments.map((r) => (
                      <tr key={r.id}>
                        <td><Link className="row-link" to={`/recrutements/${r.id}`}>{r.title}</Link></td>
                        <td className="num">{r.applications}</td>
                        <td className="num hide-sm">{pct(r.attendance_rate)}</td>
                        <td>{r.state === "closed" ? (r.hired ? <Badge tone="ok" dot>Embauche</Badge> : <Badge>Sans embauche</Badge>) : r.state === "abandoned" ? <Badge>Abandonné</Badge> : <Badge tone="brand" dot>En cours</Badge>}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </Card>
            <Card title="D'où viennent les candidats">
              {sources.length ? sources.map(([k, v]) => (
                <div key={k} className="stack sm" style={{ gap: 4 }}>
                  <div className="row between small"><span>{SOURCE_LABELS[k] || k}</span><span className="tnum muted">{v}</span></div>
                  <div className="meter"><span style={{ width: `${(v / Math.max(1, totalApps)) * 100}%` }} /></div>
                </div>
              )) : <p className="muted small">Pas encore de candidature.</p>}
            </Card>
          </div>
        </>
      )}
    </main>
  );
}
