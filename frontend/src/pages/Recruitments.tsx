import { useState } from "react";
import { Link } from "react-router-dom";
import { Briefcase, Plus, Search } from "lucide-react";
import { useApi, useLoad } from "../lib/ctx";
import { fmtDate, isClosed } from "../lib/format";
import { Badge, Card, Empty, ErrorBox, MiniSteps, PageHeader, Segmented, Skeleton } from "../ui/kit";

export default function Recruitments() {
  const api = useApi();
  const [recs, err] = useLoad(() => api.listRecruitments(), []);
  const [filter, setFilter] = useState<"active" | "closed">("active");
  const [q, setQ] = useState("");
  const list = (recs || []).filter((r) => (filter === "closed") === isClosed(r.state) && r.title.toLowerCase().includes(q.toLowerCase()));
  const closedCount = (recs || []).filter((r) => isClosed(r.state)).length;
  return (
    <main className="content">
      <PageHeader title="Recrutements" actions={<Link to="/recrutements/nouveau" className="btn primary"><Plus size={16} /> Nouveau recrutement</Link>} />
      <ErrorBox msg={err} />
      <Card flush title={closedCount ? <Segmented label="Afficher" value={filter} onChange={setFilter}
        items={[{ id: "active", label: "En cours" }, { id: "closed", label: `Terminés · ${closedCount}` }]} /> : undefined}
        actions={(recs?.length || 0) > 8 ? <div className="input-group" style={{ width: 240 }}><Search size={16} /><input className="input" placeholder="Rechercher un poste" value={q} onChange={(e) => setQ(e.target.value)} /></div> : undefined}>
        {!recs ? <div style={{ padding: 20 }}><Skeleton h={120} /></div> : list.length === 0 ? (
          <Empty icon={<Briefcase size={20} />} title={filter === "active" ? "Aucun recrutement en cours" : "Aucun recrutement terminé"}
            action={filter === "active" ? <Link to="/recrutements/nouveau" className="btn primary"><Plus size={16} /> Nouveau recrutement</Link> : undefined} />
        ) : (
          <div className="table-wrap">
            <table className="table">
              <thead><tr><th>Poste</th><th>Où en est-on</th><th className="num">Candidatures</th><th className="hide-sm">Prochaine action</th></tr></thead>
              <tbody>
                {list.map((r) => (
                  <tr key={r.id}>
                    <td><div className="cell-title"><Link className="row-link" to={`/recrutements/${r.id}`}>{r.title}</Link><span className="xs muted">Créé le {fmtDate(r.created_at)}</span></div></td>
                    <td><div className="stack sm" style={{ gap: 4 }}><MiniSteps step={r.step} closed={isClosed(r.state)} /><span className="xs muted">{r.state_label}</span></div></td>
                    <td className="num">{r.applications}</td>
                    <td className="hide-sm">{r.pending ? <Link to={`/recrutements/${r.id}/${r.pending.page || r.page}`}><Badge tone="brand">{r.pending.title}</Badge></Link> : <span className="subtle">—</span>}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </main>
  );
}
