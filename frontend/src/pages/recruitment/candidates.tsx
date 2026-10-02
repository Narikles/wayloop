import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { AlertTriangle, Mail, Search, UserPlus, UserX } from "lucide-react";
import type { ApplicationItem, Criterion, MailTemplate, RecruitmentDetail } from "../../api/types";
import { IS_DEMO, useAction, useApi, useHas, useLoad } from "../../lib/ctx";
import { fmtDate, fmtShort, GROUPS, shortLabel, SOURCE_LABELS, STAGE } from "../../lib/format";
import { Badge, Button, Card, CriteriaTable, Drawer, ErrorBox, Field, Modal, Notice, Segmented, Spinner, StatusIcon } from "../../ui/kit";

export function GroupBadge({ g }: { g: string | null }) {
  const m = GROUPS.find((x) => x.id === g);
  if (!m) return <Badge>Nouvelle</Badge>;
  return <Badge tone={m.tone} dot>{m.short}</Badge>;
}

const ordered = (crit: Criterion[]) => [...crit.filter((c) => c.required), ...crit.filter((c) => !c.required)];

export function CandidatesTable({ apps, criteria, selected, onSelect, onOpen, showStage = true }: {
  apps: ApplicationItem[]; criteria: Criterion[]; selected?: string[]; onSelect?: (ids: string[]) => void; onOpen: (id: string) => void; showStage?: boolean;
}) {
  const cols = ordered(criteria);
  const screened = apps.some((a) => a.evaluations.length);
  const all = selected && apps.length > 0 && apps.every((a) => selected.includes(a.id));
  const toggle = (id: string, v: boolean) => onSelect?.(v ? [...(selected || []), id] : (selected || []).filter((x) => x !== id));
  return (
    <div className="table-wrap">
      <table className="table">
        <thead>
          <tr>
            {onSelect && <th className="w-check"><input type="checkbox" className="cb" aria-label="Tout sélectionner" checked={!!all}
              onChange={(e) => onSelect(e.target.checked ? Array.from(new Set([...(selected || []), ...apps.map((a) => a.id)])) : (selected || []).filter((x) => !apps.some((a) => a.id === x)))} /></th>}
            <th>Candidat</th>
            {screened && cols.map((c) => <th key={c.id} className={`crit hide-sm ${c.required ? "" : "opt"}`} title={`${c.label} (${c.required ? "indispensable" : "souhaité"})`}><span>{shortLabel(c)}</span></th>)}
            {screened && <th>Synthèse</th>}
            {showStage && <th className="hide-sm">Étape</th>}
          </tr>
        </thead>
        <tbody>
          {apps.map((a) => {
            const ev = Object.fromEntries(a.evaluations.map((e) => [e.criterion_id, e]));
            const unconfirmed = a.evaluations.filter((e) => e.required && (e.evidence === "declared" || e.evidence === "inconsistent") && e.status !== "not_met").length;
            const inconsistent = a.evaluations.some((e) => e.evidence === "inconsistent");
            return (
              <tr key={a.id} className={`clickable ${selected?.includes(a.id) ? "selected" : ""}`} onClick={() => onOpen(a.id)}>
                {onSelect && <td className="w-check" onClick={(e) => e.stopPropagation()}>
                  <input type="checkbox" className="cb" aria-label={`Sélectionner ${a.name}`} checked={!!selected?.includes(a.id)} onChange={(e) => toggle(a.id, e.target.checked)} />
                </td>}
                <td><div className="cell-title"><b>{a.name}</b><span className="xs muted">{SOURCE_LABELS[a.source] || a.source} · {fmtDate(a.created_at)}{a.rescued ? " · repêché(e)" : ""}</span></div></td>
                {screened && cols.map((c) => (
                  <td key={c.id} className={`crit hide-sm ${c.required ? "" : "opt"}`}>
                    {ev[c.id] ? <span title={`${c.label} : ${ev[c.id].declared ? `déclaré ${ev[c.id].declared}` : ev[c.id].justification}`}><StatusIcon status={ev[c.id].status} size={20} /></span> : <span className="subtle">—</span>}
                  </td>
                ))}
                {screened && <td>
                  <div className="row" style={{ gap: 6 }}>
                    <GroupBadge g={a.group} />
                    {inconsistent ? <Badge tone="warn"><AlertTriangle size={12} /> À vérifier</Badge>
                      : unconfirmed ? <Badge title="Déclaré par le candidat, non retrouvé dans son CV">{unconfirmed} à vérifier</Badge> : null}
                  </div>
                </td>}
                {showStage && <td className="hide-sm"><Badge tone={STAGE[a.status]?.tone}>{STAGE[a.status]?.label || a.status}</Badge></td>}
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

export function useFilteredApps(apps: ApplicationItem[] | null) {
  const [group, setGroup] = useState("all");
  const [q, setQ] = useState("");
  const list = useMemo(() => (apps || []).filter((a) => (group === "all" || (a.group || "unscreened") === group) && a.name.toLowerCase().includes(q.toLowerCase())), [apps, group, q]);
  const counts = useMemo(() => {
    const c: Record<string, number> = { all: (apps || []).length };
    (apps || []).forEach((a) => (c[a.group || "unscreened"] = (c[a.group || "unscreened"] || 0) + 1));
    return c;
  }, [apps]);
  const groups = GROUPS.filter((g) => counts[g.id]);
  const toolbar = (
    <div className="row between" style={{ width: "100%" }}>
      {groups.length > 0 ? (
        <Segmented label="Filtrer" value={group} onChange={setGroup}
          items={[{ id: "all", label: <>Toutes <span className="tnum muted">{counts.all}</span></> },
            ...groups.map((g) => ({ id: g.id, label: <>{g.short} <span className="tnum muted">{counts[g.id]}</span></> }))]} />
      ) : <span className="strong">{counts.all} candidature{counts.all > 1 ? "s" : ""}</span>}
      {(apps?.length || 0) > 10 && <div className="input-group" style={{ width: 220 }}><Search size={16} /><input className="input" placeholder="Rechercher" value={q} onChange={(e) => setQ(e.target.value)} /></div>}
    </div>
  );
  return { list, toolbar };
}

export type BulkMode = "email" | "reject" | "invite";

export function BulkModal({ rec, ids, mode, onClose, onDone }: { rec: RecruitmentDetail; ids: string[]; mode: BulkMode; onClose: () => void; onDone: () => void }) {
  const api = useApi();
  const run = useAction();
  const [tpls] = useLoad<MailTemplate[]>(() => api.mailTemplates(), []);
  const [tpl, setTpl] = useState(mode === "invite" ? "invitation_manuelle" : "point_etape");
  const [subject, setSubject] = useState("");
  const [body, setBody] = useState("");
  useEffect(() => {
    if (mode !== "reject" && tpls) {
      const t = tpls.find((x) => x.id === tpl) || tpls[0];
      setSubject(t.subject);
      setBody(t.body);
    }
  }, [tpls, tpl, mode]);
  const n = ids.length;
  const title = mode === "email" ? `Écrire à ${n} candidat${n > 1 ? "s" : ""}` : mode === "invite" ? `Inviter en entretien — ${n} candidat${n > 1 ? "s" : ""}`
    : `Ne pas retenir ${n} candidature${n > 1 ? "s" : ""}`;
  const sub = mode === "reject" ? "Chaque personne reçoit une réponse courtoise, sans motif personnel. Elle ne recevra pas d'autre message à la fin."
    : mode === "invite" ? "Demandez leurs disponibilités ; vous fixerez ensuite la date dans la page Entretiens."
      : "Chaque candidat reçoit un message personnel ; les réponses arrivent dans votre boîte mail.";
  return (
    <Modal size="lg" onClose={onClose} title={title} sub={sub}
      foot={<><button className="btn" onClick={onClose}>Annuler</button>
        <Button variant={mode === "reject" ? "danger solid" : "primary"} onClick={async () => {
          const action = mode === "invite" ? "shortlist" : mode;
          const r = await run(() => api.bulk(rec.id, { application_ids: ids, action, subject: subject || undefined, body: body || undefined }),
            mode === "email" ? "Messages envoyés" : mode === "invite" ? "Invitation envoyée" : "Réponses envoyées");
          if (r) onDone();
        }}>{mode === "reject" ? "Envoyer les réponses" : `Envoyer ${n > 1 ? `les ${n} messages` : "le message"}`}</Button></>}>
      {mode === "email" && (
        <Field label="Modèle">
          <select className="select" value={tpl} onChange={(e) => setTpl(e.target.value)}>
            {(tpls || []).filter((t) => t.id !== "invitation_manuelle").map((t) => <option key={t.id} value={t.id}>{t.label}</option>)}
          </select>
        </Field>
      )}
      <Field label="Objet"><input className="input" value={subject} placeholder={mode === "reject" ? "Message par défaut" : ""} onChange={(e) => setSubject(e.target.value)} /></Field>
      <Field label="Message" hint={<>Remplacés pour chacun : <span className="kbd">{"{prénom}"}</span> <span className="kbd">{"{poste}"}</span> <span className="kbd">{"{entreprise}"}</span></>}>
        <textarea className="textarea" rows={9} value={body} placeholder={mode === "reject" ? "Message par défaut" : ""} onChange={(e) => setBody(e.target.value)} />
      </Field>
    </Modal>
  );
}

/** Ajoute des candidats aux entretiens : lien de réservation (Premium) ou invitation relue (Gratuit). */
export function useInvite(rec: RecruitmentDetail, onDone: () => Promise<void> | void) {
  const api = useApi();
  const run = useAction();
  const scheduling = useHas("scheduling");
  const [modal, setModal] = useState<string[] | null>(null);
  const canInvite = ["scheduling", "interviewing"].includes(rec.state);
  const invite = async (ids: string[]) => {
    if (rec.state === "scheduling" || (scheduling && rec.free_slots > 0)) {
      const r = await run(() => api.bulk(rec.id, { application_ids: ids, action: "shortlist" }),
        rec.state === "scheduling" ? "Ajouté à la sélection : invité avec les autres" : "Invitation envoyée avec le lien de réservation");
      if (r) await onDone();
    } else setModal(ids);
  };
  const node = modal && <BulkModal rec={rec} ids={modal} mode="invite" onClose={() => setModal(null)} onDone={async () => { setModal(null); await onDone(); }} />;
  return { canInvite, invite, node };
}

export function CandidateDrawer({ id, rec, onClose, onChanged }: { id: string; rec: RecruitmentDetail; onClose: () => void; onChanged?: () => void }) {
  const api = useApi();
  const [a, err] = useLoad(() => api.getApplication(id), [id]);
  const [modal, setModal] = useState<"email" | "reject" | null>(null);
  const done = () => { onChanged?.(); onClose(); };
  const { canInvite, invite, node } = useInvite(rec, done);
  const final = a && ["rejected", "hired", "withdrawn"].includes(a.status);
  return (
    <Drawer onClose={onClose}
      title={a ? a.name : "Candidat"}
      sub={a && <div className="row" style={{ gap: 6 }}><GroupBadge g={a.group} /><Badge tone={STAGE[a.status]?.tone}>{STAGE[a.status]?.label}</Badge><span className="xs muted">{SOURCE_LABELS[a.source] || a.source} · {fmtShort(a.created_at)}</span></div>}
      actions={a && !final && <>
        {canInvite && !a.shortlisted && <button className="btn sm" onClick={() => invite([a.id])}><UserPlus size={14} /> Inviter</button>}
        <button className="btn sm" onClick={() => setModal("email")}><Mail size={14} /> Écrire</button>
        <button className="btn sm" onClick={() => setModal("reject")}><UserX size={14} /> Ne pas retenir</button>
      </>}>
      <ErrorBox msg={err} />
      {!a && !err && <Spinner />}
      {a && (
        <>
          <Card title="Critère par critère">
            {a.evaluations.length ? <CriteriaTable evals={a.evaluations} /> : <p className="muted">La synthèse sera prête avec la sélection.</p>}
          </Card>
          <Card title="Coordonnées">
            <dl className="dl">
              <dt>E-mail</dt><dd>{a.email || "—"}</dd>
              <dt>Téléphone</dt><dd>{a.phone || "—"}</dd>
              <dt>Autres postes</dt><dd>{a.pool_consent ? "Accepte d'être recontacté(e)" : "Non"}</dd>
            </dl>
          </Card>
          {a.message && <Card title="Message"><p className="pre">{a.message}</p></Card>}
          <Card title={<span className="row">CV {a.cv_filename && <span className="muted small">· {a.cv_filename}</span>}</span>}
            actions={a.cv_link && !IS_DEMO ? <a className="btn sm" href={a.cv_link} target="_blank" rel="noreferrer">Ouvrir le fichier</a> : undefined}>
            {a.cv_text ? <div className="pre small" style={{ maxHeight: 360, overflowY: "auto" }}>{a.cv_text}</div> : <p className="muted">Pas de texte lisible.</p>}
          </Card>
          {!!a.messages?.length && (
            <Card title="E-mails envoyés" flush>
              <ul className="note-list">
                {a.messages.map((m) => (
                  <li key={m.id}>
                    <details className="fold" style={{ padding: "12px 16px", borderBottom: "1px solid var(--line)" }}>
                      <summary><span style={{ flex: 1 }}>{m.label}</span><span className="xs muted tnum">{fmtShort(m.created_at)}</span>{m.status !== "sent" && <Badge tone="bad">Échec</Badge>}</summary>
                      <div className="stack sm" style={{ marginTop: 10 }}>{m.subject && <b className="small strong">{m.subject}</b>}<MessageBody text={m.body} /></div>
                    </details>
                  </li>
                ))}
              </ul>
            </Card>
          )}
          {modal && <BulkModal rec={rec} ids={[a.id]} mode={modal} onClose={() => setModal(null)} onDone={() => { setModal(null); done(); }} />}
          {node}
        </>
      )}
    </Drawer>
  );
}

export function SelectionBar({ count, children, onClear }: { count: number; children: React.ReactNode; onClear: () => void }) {
  return (
    <div className="bulkbar">
      <span className="strong tnum" style={{ color: "inherit" }}>{count} sélectionné{count > 1 ? "s" : ""}</span>
      <span style={{ flex: 1 }} />
      {children}
      <button className="btn sm" onClick={onClear}>Annuler</button>
    </div>
  );
}

export function NoCandidates() {
  return <Notice>Aucune candidature pour l'instant. Partagez le lien de l'offre : les candidatures arrivent ici.</Notice>;
}

/** Corps d'un e-mail, liens cliquables (dans la démo, ils ouvrent la page candidat correspondante). */
export function MessageBody({ text }: { text: string }) {
  const parts = text.split(/(https?:\/\/[^\s]+)/g);
  return (
    <div className="pre small muted">
      {parts.map((p, i) => {
        if (!/^https?:\/\//.test(p)) return <span key={i}>{p}</span>;
        const path = p.replace(/^https?:\/\/[^/]+/, "");
        return IS_DEMO && /^\/(offres|rdv|candidat|confidentialite)\//.test(path)
          ? <Link key={i} to={path}>{p}</Link>
          : <a key={i} href={p} target="_blank" rel="noreferrer">{p}</a>;
      })}
    </div>
  );
}
