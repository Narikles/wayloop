import { useEffect, useRef, useState } from "react";
import { Link, Navigate, useNavigate, useParams } from "react-router-dom";
import { ExternalLink } from "lucide-react";
import type { PageId, RecruitmentDetail } from "../api/types";
import { IS_DEMO, useAction, useApi, useHas, useLoad, useSession, useToast, useUpgrade, viewerDownloads } from "../lib/ctx";
import { fmtDate, isClosed, PAGES, STATE_TONE } from "../lib/format";
import { Badge, Button, ErrorBox, Modal, MoreMenu, PageHeader, Spinner } from "../ui/kit";
import { ApplicationsPage } from "./recruitment/applications";
import { DebriefPage } from "./recruitment/debrief";
import { DecisionPage } from "./recruitment/decision";
import { HistoryPage } from "./recruitment/history";
import { InterviewsPage } from "./recruitment/interviews";
import { OfferPage } from "./recruitment/offer";

export type PageProps = { rec: RecruitmentDetail; onChange: (r: RecruitmentDetail) => void; reload: () => Promise<void> };

export default function Recruitment() {
  const { id = "", page } = useParams();
  const api = useApi();
  const [rec, err, reload, setRec] = useLoad(() => api.getRecruitment(id), [id]);
  const { touch } = useSession();
  const pendingKey = rec ? `${rec.state}:${rec.pending.map((p) => p.id).join(",")}` : "";
  useEffect(() => { if (pendingKey) touch(); }, [pendingKey, touch]);
  const last = useRef(Date.now());
  useEffect(() => {
    const mark = () => (last.current = Date.now());
    window.addEventListener("pointerdown", mark);
    window.addEventListener("keydown", mark);
    const t = window.setInterval(() => {
      if (document.visibilityState === "visible" && Date.now() - last.current < 60_000) void api.active(id, 15).catch(() => {});
    }, 15_000);
    return () => { window.removeEventListener("pointerdown", mark); window.removeEventListener("keydown", mark); window.clearInterval(t); };
  }, [api, id]);
  useEffect(() => {
    if (!rec?.busy?.length) return;
    const t = window.setTimeout(() => void reload(), 2500);
    return () => window.clearTimeout(t);
  }, [rec, reload]);

  if (err) return <main className="content"><ErrorBox msg={err} /></main>;
  if (!rec) return <main className="content"><Spinner /></main>;
  if (!page) return <Navigate to={`/recrutements/${id}/${rec.page}`} replace />;
  const props: PageProps = { rec, onChange: setRec, reload };

  return (
    <main className="content">
      <PageHeader crumbs={<><Link to="/recrutements">Recrutements</Link> / {rec.title}</>} title={rec.title}
        sub={<div className="row" style={{ gap: 8 }}>
          <Badge tone={STATE_TONE[rec.state] ?? ""} dot>{rec.state_label}</Badge>
          <span className="small muted">{rec.published_at ? `En ligne depuis le ${fmtDate(rec.published_at)}` : `Créé le ${fmtDate(rec.created_at)}`}</span>
        </div>}
        actions={<HeaderActions rec={rec} onChange={setRec} />} />
      <StepNav rec={rec} current={page} />
      {page === "offre" && <OfferPage {...props} />}
      {page === "candidatures" && <ApplicationsPage {...props} />}
      {page === "entretiens" && <InterviewsPage {...props} />}
      {page === "debrief" && <DebriefPage {...props} />}
      {page === "decision" && <DecisionPage {...props} />}
      {page === "historique" && <HistoryPage {...props} />}
    </main>
  );
}

function StepNav({ rec, current }: { rec: RecruitmentDetail; current: string }) {
  const nav = useRef<HTMLElement>(null);
  useEffect(() => { // sur mobile, l'onglet ouvert reste visible
    nav.current?.querySelector<HTMLElement>("a.on")?.scrollIntoView({ block: "nearest", inline: "center" });
  }, [current]);
  const closed = isClosed(rec.state);
  const c = rec.counts;
  const pendingOn = (p: PageId) => rec.pending.some((x) => x.page === p);
  const badge: Record<PageId, { n?: number; hot?: boolean }> = {
    offre: { hot: pendingOn("offre") },
    candidatures: { n: c.applications, hot: pendingOn("candidatures") },
    entretiens: { n: c.interviews || undefined, hot: pendingOn("entretiens") || c.to_schedule > 0 },
    debrief: { n: c.to_note || undefined, hot: c.to_note > 0 },
    decision: { hot: pendingOn("decision") },
  };
  return (
    <nav className="stepnav" aria-label="Étapes du recrutement" ref={nav}>
      {PAGES.map((p, i) => {
        const n = i + 1;
        const state = closed || n < rec.step ? "done" : n === rec.step ? "cur" : "later";
        const b = badge[p.id];
        return (
          <Link key={p.id} to={`/recrutements/${rec.id}/${p.id}`} className={`${state} ${current === p.id ? "on" : ""}`} aria-current={current === p.id ? "page" : undefined}>
            <span className="n">{state === "done" ? "✓" : n}</span>{p.label}
            {b.n !== undefined ? <span className={`count tnum ${b.hot ? "hot" : ""}`}>{b.n}</span> : b.hot ? <span className="count hot" aria-label="À faire">•</span> : null}
          </Link>
        );
      })}
    </nav>
  );
}

function HeaderActions({ rec, onChange }: { rec: RecruitmentDetail; onChange: (r: RecruitmentDetail) => void }) {
  const api = useApi();
  const nav = useNavigate();
  const run = useAction();
  const notify = useToast();
  const upgrade = useUpgrade();
  const hasExport = useHas("export");
  const [ask, setAsk] = useState(false);
  const closed = isClosed(rec.state);
  const publicPath = rec.apply_link ? `/offres/${rec.apply_link.split("/").pop()?.split("?")[0]}` : null;
  const items = [
    ...(rec.apply_link && !closed ? [{ label: "Copier le lien de l'offre", onClick: async () => {
      try { await navigator.clipboard.writeText(rec.apply_link!); notify("Lien copié"); } catch { notify("Copie impossible.", "bad"); }
    } }] : []),
    ...(rec.applications > 0 ? [{ label: "Exporter les candidatures", hint: hasExport ? "Fichier CSV (Excel, Google Sheets)" : "Offre Pro", onClick: async () => {
      if (!hasExport) return upgrade("L'export des candidatures est inclus dans l'offre Pro.");
      const filename = `candidatures-${rec.id.slice(0, 8)}.csv`;
      const csv = api.exportCsv?.(rec.id);
      if (csv) {
        // Démo publiée : la visionneuse bloque les liens de téléchargement et propose son propre enregistrement.
        const dl = await viewerDownloads();
        if (dl) {
          try {
            await dl.save({ filename, data: csv });
            notify("Fichier enregistré");
          } catch (e) {
            if ((e as { code?: string })?.code !== "declined") notify("Téléchargement indisponible ici.", "bad");
          }
          return;
        }
      }
      const url = api.exportUrl(rec.id);
      if (!url) return;
      const a = document.createElement("a");
      a.href = url;
      a.download = filename;
      a.click();
    } }] : []),
    { label: "Historique", hint: "Qui a fait quoi, et quand", onClick: () => nav(`/recrutements/${rec.id}/historique`) },
    ...(!closed ? [{ label: "Abandonner ce recrutement", danger: true, onClick: () => setAsk(true) }] : []),
  ];
  return (
    <>
      {publicPath && !closed && <Link className="btn sm" to={publicPath} target={IS_DEMO ? undefined : "_blank"}><ExternalLink size={14} /> Voir l'offre</Link>}
      <MoreMenu items={items} />
      {ask && (
        <Modal title="Abandonner ce recrutement ?" onClose={() => setAsk(false)}
          sub={rec.applications ? "Chaque candidat recevra une réponse ; vous pourrez relire les messages avant l'envoi." : "L'offre sera retirée."}
          foot={<><button className="btn" onClick={() => setAsk(false)}>Annuler</button>
            <Button variant="danger solid" onClick={async () => {
              const r = await run(() => api.abandon(rec.id));
              if (r) { setAsk(false); onChange(r); nav(`/recrutements/${rec.id}/decision`); }
            }}>Abandonner</Button></>}>
          <p className="muted">L'offre est retirée de Google et des sites où elle est diffusée.</p>
        </Modal>
      )}
    </>
  );
}
