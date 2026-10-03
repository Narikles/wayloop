import type { Criterion, PageId, PipelineStage } from "../api/types";

const TZ = "Europe/Paris";

export function fmtDateTime(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
}
export function fmtShort(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleString("fr-FR", { timeZone: TZ, day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
}
export function fmtDate(iso?: string | null) {
  if (!iso) return "—";
  return new Date(iso).toLocaleDateString("fr-FR", { timeZone: TZ, day: "numeric", month: "short", year: "numeric" });
}
export function fmtTime(iso: string) {
  return new Date(iso).toLocaleTimeString("fr-FR", { timeZone: TZ, hour: "2-digit", minute: "2-digit" });
}
export function fmtDay(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
}
export function fmtDayShort(iso: string) {
  return new Date(iso).toLocaleDateString("fr-FR", { timeZone: TZ, weekday: "short", day: "numeric", month: "short" });
}
export function fmtEuro(n: number) {
  return n.toLocaleString("fr-FR", { minimumFractionDigits: n % 1 ? 2 : 0, maximumFractionDigits: 2 }) + " €";
}
export function relDays(iso?: string | null) {
  if (!iso) return "";
  const d = Math.round((Date.now() - Date.parse(iso)) / 86400000);
  return d <= 0 ? "aujourd'hui" : d === 1 ? "hier" : `il y a ${d} j`;
}
/** Valeur d'un champ <input type="datetime-local"> (heure de Paris) → ISO avec fuseau. */
export function localInputToIso(v: string): string {
  return new Date(v).toISOString();
}
/** Date proposée par défaut : le prochain jour ouvré, à 10 h. */
export function nextBusinessDay(): Date {
  const d = new Date(Date.now() + 86400000);
  while (d.getDay() === 0 || d.getDay() === 6) d.setDate(d.getDate() + 1);
  d.setHours(10, 0, 0, 0);
  return d;
}
export function isoToLocalInput(iso?: string | null): string {
  const d = iso ? new Date(iso) : nextBusinessDay();
  const p = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())}T${p(d.getHours())}:${p(d.getMinutes())}`;
}
export const plural = (n: number, w: string, p?: string) => `${n} ${n > 1 ? p || w + "s" : w}`;
export const initials = (name?: string | null) =>
  (name || "?").split(/\s+/).filter(Boolean).slice(0, 2).map((x) => x[0]!.toUpperCase()).join("");

export const SOURCE_LABELS: Record<string, string> = {
  lien: "Lien direct", google: "Google", france_travail: "France Travail", apec: "Apec", linkedin: "LinkedIn", indeed: "Indeed",
  jooble: "Jooble", talent: "Talent.com", adzuna: "Adzuna", jobijoba: "Jobijoba", optioncarriere: "Optioncarrière", jobrapido: "Jobrapido",
  page_carriere: "Page de l'offre", email: "E-mail", telephone: "Téléphone", spontanee: "Candidature spontanée",
  recommandation: "Recommandation", salon: "Salon, forum", local: "Relais locaux", autre: "Autre",
};
/** Provenances proposées pour une candidature ajoutée à la main. */
export const MANUAL_SOURCES: { id: string; label: string }[] = [
  { id: "linkedin", label: "LinkedIn (message)" }, { id: "email", label: "E-mail" }, { id: "telephone", label: "Téléphone" },
  { id: "indeed", label: "Indeed" }, { id: "france_travail", label: "France Travail" }, { id: "spontanee", label: "Candidature spontanée" },
  { id: "recommandation", label: "Recommandation" }, { id: "salon", label: "Salon, forum" }, { id: "local", label: "Relais locaux" },
  { id: "autre", label: "Autre" },
];
export const STAGE: Record<string, { label: string; tone: string }> = {
  received: { label: "Reçue", tone: "" }, screened: { label: "À évaluer", tone: "" },
  not_shortlisted: { label: "Réponse à envoyer", tone: "warn" }, shortlisted: { label: "Présélectionnée", tone: "brand" },
  invited: { label: "Invitée", tone: "brand" }, booked: { label: "Entretien prévu", tone: "brand" },
  interviewed: { label: "Entretien fait", tone: "violet" }, hired: { label: "Embauchée", tone: "ok" },
  rejected: { label: "Refusée", tone: "" }, withdrawn: { label: "Retirée", tone: "" },
};
/** Colonnes du pipeline (Reçu → À évaluer → Présélectionné → Entretien → Refusé / Embauché). */
export const PIPELINE: { id: PipelineStage; label: string; hint: string }[] = [
  { id: "recu", label: "Reçu", hint: "Nouvelles candidatures, pas encore ouvertes" },
  { id: "a_evaluer", label: "À évaluer", hint: "Ouvertes, en attente de votre choix" },
  { id: "preselectionne", label: "Présélectionné", hint: "À rencontrer en entretien" },
  { id: "entretien", label: "Entretien", hint: "Date fixée ou entretien fait" },
  { id: "refuse", label: "Refusé", hint: "Remercié ou réponse à envoyer" },
  { id: "embauche", label: "Embauché", hint: "Personne recrutée" },
];
export const GROUPS: { id: string; label: string; short: string; tone: string }[] = [
  { id: "meets", label: "Remplissent les critères indispensables", short: "Remplit", tone: "ok" },
  { id: "partial", label: "Les remplissent en partie", short: "En partie", tone: "warn" },
  { id: "does_not", label: "Ne les remplissent pas", short: "Ne remplit pas", tone: "bad" },
  { id: "unreadable", label: "CV à lire vous-même", short: "À lire", tone: "" },
];
export const STATE_TONE: Record<string, string> = {
  offer_review: "", collecting: "ok", shortlist_review: "warn", scheduling: "warn", interviewing: "brand", decision: "warn",
  closed: "", abandoned: "",
};
export const PAGES: { id: PageId; label: string }[] = [
  { id: "offre", label: "Offre" }, { id: "candidatures", label: "Candidatures" }, { id: "entretiens", label: "Entretiens" },
  { id: "debrief", label: "Débrief" }, { id: "decision", label: "Décision" },
];
export const isClosed = (state: string) => state === "closed" || state === "abandoned";

/** Libellé court d'un critère, pour les en-têtes de tableau. */
export function shortLabel(c: Criterion): string {
  const p = c.params || {};
  switch (c.kind) {
    case "experience": return p.years ? `Expérience ${p.years} an${p.years > 1 ? "s" : ""}` : "Expérience";
    case "competence": return String(p.skill || "Compétence");
    case "diplome": return "Diplôme";
    case "permis": return `Permis ${p.category || "B"}`;
    case "langue": return `${p.language || "Langue"} ${p.level || ""}`.trim();
    case "habilitation": return String(p.name || "Habilitation");
    default: return c.label.length > 22 ? c.label.slice(0, 20) + "…" : c.label;
  }
}
