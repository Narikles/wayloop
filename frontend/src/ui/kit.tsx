import { useEffect, useRef, useState, type ReactNode } from "react";
import { AlertTriangle, Check, CircleHelp, Info, Lock, Minus, MoreHorizontal, OctagonAlert, X, Infinity as Loop } from "lucide-react";
import type { Evaluation, Issue } from "../api/types";
import { useAction, useUpgrade } from "../lib/ctx";

export function Logo({ size = 30 }: { size?: number }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }} aria-hidden>
      <Loop size={size * 0.62} strokeWidth={2.4} />
    </span>
  );
}

export function Button(props: {
  children?: ReactNode;
  onClick?: () => Promise<unknown> | unknown;
  variant?: "primary" | "ghost" | "link" | "danger" | "danger solid" | "";
  size?: "sm" | "lg" | "";
  icon?: ReactNode;
  iconOnly?: boolean;
  disabled?: boolean;
  type?: "button" | "submit";
  title?: string;
  className?: string;
  done?: string;
}) {
  const [busy, setBusy] = useState(false);
  const run = useAction();
  return (
    <button
      type={props.type || "button"}
      title={props.title}
      aria-label={props.iconOnly ? props.title : undefined}
      className={`btn ${props.variant || ""} ${props.size || ""} ${props.iconOnly ? "icon" : ""} ${props.className || ""}`}
      disabled={props.disabled || busy}
      onClick={async () => {
        if (!props.onClick) return;
        setBusy(true);
        await run(async () => props.onClick!(), props.done);
        setBusy(false);
      }}
    >
      {busy ? <span className="spinner" aria-hidden /> : props.icon}
      {!props.iconOnly && props.children}
    </button>
  );
}

export function Badge({ children, tone = "", dot, wrap, title }: { children: ReactNode; tone?: string; dot?: boolean; wrap?: boolean; title?: string }) {
  return <span className={`badge ${tone} ${wrap ? "wrap" : ""}`} title={title}>{dot && <span className="d" />}{children}</span>;
}

export function PremiumTag({ label = "Pro" }: { label?: string }) {
  return <span className="lock"><Lock size={11} strokeWidth={2.5} />{label}</span>;
}

/** Bouton qui ouvre la fenêtre des offres au lieu d'agir, si la fonctionnalité est verrouillée. */
export function LockedButton({ children, reason, size = "" }: { children: ReactNode; reason: string; size?: "sm" | "lg" | "" }) {
  const upgrade = useUpgrade();
  return (
    <button className={`btn ${size}`} onClick={() => upgrade(reason)} type="button">
      <Lock size={14} /> {children}
    </button>
  );
}

export function Card({ title, sub, actions, children, foot, className = "", bodyClass = "", id, flush }: {
  title?: ReactNode; sub?: ReactNode; actions?: ReactNode; children?: ReactNode; foot?: ReactNode; className?: string; bodyClass?: string; id?: string;
  /** Contenu collé aux bords (tableau, liste). */
  flush?: boolean;
}) {
  return (
    <section className={`card ${className}`} id={id}>
      {(title || actions) && (
        <div className="card-head">
          <div className="t">{typeof title === "string" ? <h3>{title}</h3> : title}{sub && <span className="muted small">{sub}</span>}</div>
          {actions && <div className="actions">{actions}</div>}
        </div>
      )}
      {children !== undefined && children !== null && children !== false && <div className={`card-body ${flush ? "flush" : ""} ${bodyClass}`}>{children}</div>}
      {foot && <div className="card-foot">{foot}</div>}
    </section>
  );
}

export function PageHeader({ title, sub, crumbs, actions }: { title: ReactNode; sub?: ReactNode; crumbs?: ReactNode; actions?: ReactNode }) {
  return (
    <header className="page-head">
      <div className="titles">
        {crumbs && <div className="crumbs">{crumbs}</div>}
        <h1>{title}</h1>
        {sub && <div className="muted">{sub}</div>}
      </div>
      {actions && <div className="actions">{actions}</div>}
    </header>
  );
}

export function Field({ label, hint, error, children, htmlFor }: { label?: ReactNode; hint?: ReactNode; error?: ReactNode; children: ReactNode; htmlFor?: string }) {
  return (
    <div className="field">
      {label && <label className="lbl" htmlFor={htmlFor}>{label}</label>}
      {children}
      {hint && !error && <span className="hint">{hint}</span>}
      {error && <span className="err">{error}</span>}
    </div>
  );
}

/** Mention à retirer, affichée sous le champ concerné, avec le geste qui la retire. */
export function IssueLine({ issue, onRemove }: { issue: Issue; onRemove?: () => void }) {
  return (
    <span className="issue" role="alert">
      <AlertTriangle size={14} />
      <span>{issue.match ? <>« {issue.match} » : </> : null}{issue.message}</span>
      {onRemove && issue.match && <button type="button" className="btn link sm" onClick={onRemove}>Retirer</button>}
    </span>
  );
}

/** Retire une mention d'un texte (même règle que le serveur) : la phrase entière si, sans la mention,
 * il n'en reste presque rien (« Idéalement moins de 30 ans. » disparaît en entier). */
export function removeMention(text: string, match: string): string {
  const i = text.indexOf(match);
  if (i < 0) return text;
  const bounds = /[.!?\n]/g;
  let start = 0;
  let end = text.length;
  for (const m of text.matchAll(bounds)) {
    const k = m.index ?? 0;
    if (k < i) start = k + 1;
    else if (k >= i + match.length) { end = text[k] === "\n" ? k : k + 1; break; }
  }
  const rest = (text.slice(start, i) + text.slice(i + match.length, end)).replace(/[.!?,;:\s]+/g, " ").trim();
  const wholeLine = (start === 0 || text[start - 1] === "\n") && text[end] === "\n";
  const out = rest.split(" ").filter(Boolean).length < 3
    ? text.slice(0, start) + text.slice(wholeLine ? end + 1 : end)
    : text.slice(0, i) + text.slice(i + match.length);
  return out.replace(/[ \t]{2,}/g, " ").replace(/\s+([,.;])/g, "$1").replace(/(^|\n)[ \t]*[,;][ \t]*/g, "$1").replace(/\n[ \t]+/g, "\n").replace(/^\s+|[ \t]+$/g, "");
}

export function Notice({ tone = "", title, children, icon, actions }: { tone?: "ok" | "warn" | "bad" | "brand" | ""; title?: ReactNode; children?: ReactNode; icon?: ReactNode; actions?: ReactNode }) {
  const ic = icon ?? (tone === "ok" ? <Check size={16} /> : tone === "bad" ? <OctagonAlert size={16} /> : tone === "warn" ? <AlertTriangle size={16} /> : <Info size={16} />);
  return (
    <div className={`notice ${tone}`} role={tone === "bad" ? "alert" : undefined}>
      {ic}
      <div className="nb">{title && <span className="nt">{title}</span>}{children && <div>{children}</div>}{actions && <div className="row" style={{ marginTop: 8, gap: 8 }}>{actions}</div>}</div>
    </div>
  );
}

export function ErrorBox({ msg }: { msg: string | null }) {
  if (!msg) return null;
  return <Notice tone="bad" title="Impossible de charger">{msg}</Notice>;
}

export function Spinner({ label }: { label?: string }) {
  return <div className="row muted" role="status"><span className="spinner" /> {label || "Chargement…"}</div>;
}

export function Skeleton({ h = 16, w = "100%" }: { h?: number; w?: number | string }) {
  return <div className="skeleton" style={{ height: h, width: w }} />;
}

export function Empty({ icon, title, children, action }: { icon?: ReactNode; title: string; children?: ReactNode; action?: ReactNode }) {
  return (
    <div className="empty">
      {icon && <div className="ic">{icon}</div>}
      <h3>{title}</h3>
      {children && <p style={{ maxWidth: 440 }}>{children}</p>}
      {action}
    </div>
  );
}

export function Stat({ label, value, hint, icon }: { label: string; value: ReactNode; hint?: ReactNode; icon?: ReactNode }) {
  return (
    <div className="card stat">
      <span className="k">{icon}{label}</span>
      <span className="v">{value}</span>
      {hint && <span className="h">{hint}</span>}
    </div>
  );
}

export function Tabs<T extends string>({ value, onChange, items }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode; count?: number }[] }) {
  return (
    <div className="tabs" role="tablist">
      {items.map((t) => (
        <button key={t.id} role="tab" aria-selected={value === t.id} className={value === t.id ? "on" : ""} onClick={() => onChange(t.id)}>
          {t.label}{t.count !== undefined && <span className="count tnum">{t.count}</span>}
        </button>
      ))}
    </div>
  );
}

export function Segmented<T extends string>({ value, onChange, items, label }: { value: T; onChange: (v: T) => void; items: { id: T; label: ReactNode }[]; label?: string }) {
  return (
    <div className="seg" role="radiogroup" aria-label={label}>
      {items.map((t) => (
        <button key={t.id} type="button" role="radio" aria-checked={value === t.id} className={value === t.id ? "on" : ""} onClick={() => onChange(t.id)}>{t.label}</button>
      ))}
    </div>
  );
}

export function Modal({ title, sub, children, foot, onClose, size = "" }: { title: ReactNode; sub?: ReactNode; children: ReactNode; foot?: ReactNode; onClose: () => void; size?: "lg" | "" }) {
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <div className="overlay" onMouseDown={(e) => e.target === e.currentTarget && onClose()}>
      <div className={`modal ${size}`} role="dialog" aria-modal="true">
        <div className="card-head">
          <div className="t"><h2>{title}</h2>{sub && <span className="muted small">{sub}</span>}</div>
          <button className="btn ghost sm icon" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        <div className="card-body">{children}</div>
        {foot && <div className="card-foot">{foot}</div>}
      </div>
    </div>
  );
}

export function Drawer({ title, sub, actions, children, onClose }: { title: ReactNode; sub?: ReactNode; actions?: ReactNode; children: ReactNode; onClose: () => void }) {
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const k = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", k);
    ref.current?.focus();
    return () => window.removeEventListener("keydown", k);
  }, [onClose]);
  return (
    <>
      <div className="drawer-back" onClick={onClose} />
      <aside className="drawer" role="dialog" aria-modal="true" tabIndex={-1} ref={ref}>
        <div className="drawer-head">
          <div className="stack sm" style={{ minWidth: 0, flex: 1 }}>{typeof title === "string" ? <h2>{title}</h2> : title}{sub}</div>
          {actions && <div className="drawer-actions">{actions}</div>}
          <button className="btn ghost sm icon drawer-close" onClick={onClose} aria-label="Fermer"><X size={18} /></button>
        </div>
        <div className="drawer-body">{children}</div>
      </aside>
    </>
  );
}

/** Menu « ⋯ » : actions secondaires, rangées hors de la vue principale. */
export function MoreMenu({ items, label = "Plus d'actions" }: { items: { label: ReactNode; hint?: string; danger?: boolean; onClick: () => void }[]; label?: string }) {
  const [open, setOpen] = useState(false);
  const box = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent) => box.current && !box.current.contains(e.target as Node) && setOpen(false);
    const esc = (e: KeyboardEvent) => e.key === "Escape" && setOpen(false);
    document.addEventListener("mousedown", close);
    window.addEventListener("keydown", esc);
    return () => { document.removeEventListener("mousedown", close); window.removeEventListener("keydown", esc); };
  }, [open]);
  return (
    <div className="menu" ref={box}>
      <button className="btn sm icon" aria-label={label} aria-expanded={open} onClick={() => setOpen(!open)}><MoreHorizontal size={16} /></button>
      {open && (
        <div className="menu-list" role="menu">
          {items.map((it, i) => (
            <button key={i} role="menuitem" className={`menu-item ${it.danger ? "danger" : ""}`} onClick={() => { setOpen(false); it.onClick(); }}>
              <span>{it.label}</span>{it.hint && <span className="xs muted">{it.hint}</span>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

const STATUS_LABEL: Record<string, string> = { met: "Remplit", partial: "En partie", not_met: "Ne remplit pas", unknown: "Non établi" };
export function StatusIcon({ status, size = 22 }: { status: string; size?: number }) {
  const ic = status === "met" ? <Check size={size * 0.6} strokeWidth={3} /> : status === "partial" ? <Minus size={size * 0.6} strokeWidth={3} />
    : status === "not_met" ? <X size={size * 0.6} strokeWidth={3} /> : <CircleHelp size={size * 0.6} strokeWidth={2.5} />;
  return <span className={`status-icon ${status}`} style={{ width: size, height: size }} title={STATUS_LABEL[status]} aria-label={STATUS_LABEL[status]}>{ic}</span>;
}

const EVIDENCE: Record<string, [string, string]> = {
  confirmed: ["Confirmé par le CV", "ok"], declared: ["Déclaré, non retrouvé dans le CV", ""], inconsistent: ["À vérifier : le CV diffère", "warn"],
  cv: ["D'après le CV", "brand"],
};
export function EvidenceBadge({ e }: { e: Evaluation }) {
  if (!e.evidence) return null;
  const [l, t] = EVIDENCE[e.evidence] || [e.evidence, ""];
  return <Badge tone={t} wrap>{l}</Badge>;
}

/** Synthèse critère par critère : exigé, réponse du candidat, ce que montre le CV. */
export function CriteriaTable({ evals }: { evals: Evaluation[] }) {
  return (
    <ul className="crit-list">
      {evals.map((e) => (
        <li key={e.criterion_id}>
          <StatusIcon status={e.status} />
          <div className="stack sm" style={{ flex: 1, minWidth: 0 }}>
            <div className="row between top" style={{ gap: 8 }}>
              <span><b className="strong">{e.label}</b> <span className="xs muted">· {e.required ? "indispensable" : "souhaité"}</span></span>
              <EvidenceBadge e={e} />
            </div>
            {e.declared && <span className="small">Réponse : <b className="strong">{e.declared}</b></span>}
            {e.excerpts.map((x, i) => <span className="quote" key={i}>« <mark className="cv">{x}</mark> »</span>)}
            {!e.excerpts.length && e.justification && <span className="small muted">{e.justification}</span>}
          </div>
        </li>
      ))}
    </ul>
  );
}

/** Rend le texte d'une offre (texte brut) avec titres et listes. */
export function OfferText({ text, skipTitle, small }: { text: string; skipTitle?: string; small?: boolean }) {
  const blocks = text.trim().split(/\n\s*\n/).map((b) => b.split("\n").map((l) => l.trimEnd()).filter(Boolean)).filter((b) => b.length);
  if (skipTitle && blocks[0]?.length === 1 && blocks[0][0].trim() === skipTitle.trim()) blocks.shift();
  const isItem = (l: string) => /^\s*[-•]\s+/.test(l);
  return (
    <div className={`offer-text ${small ? "small" : ""}`}>
      {blocks.map((b, i) => {
        const shortHead = b[0].length <= 40 && !/[.!?:;,]$/.test(b[0]);
        const head = !isItem(b[0]) && b.length > 1 && (b.slice(1).every(isItem) || shortHead) ? b[0] : null;
        const rest = head ? b.slice(1) : b;
        return (
          <section key={i}>
            {head && <h3>{head}</h3>}
            {rest.every(isItem)
              ? <ul>{rest.map((l, j) => <li key={j}>{l.replace(/^\s*[-•]\s+/, "")}</li>)}</ul>
              : rest.map((l, j) => <p key={j}>{l}</p>)}
          </section>
        );
      })}
    </div>
  );
}

/** Avancement en 5 étapes, en miniature (listes de recrutements). */
export function MiniSteps({ step, closed }: { step: number; closed?: boolean }) {
  return (
    <span className="mini-steps" aria-label={closed ? "Terminé" : `Étape ${step} sur 5`}>
      {[1, 2, 3, 4, 5].map((n) => <span key={n} className={closed || n < step ? "done" : n === step ? "cur" : ""} />)}
    </span>
  );
}
