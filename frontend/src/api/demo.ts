/**
 * Démo hors ligne de WayLoop : implémente l'API en mémoire, sans aucun appel réseau.
 *
 * Les sorties du moteur (offre rédigée depuis le formulaire, questions aux candidats,
 * synthèse par règles des 7 candidatures fictives, questions d'entretien, textes envoyés)
 * sont celles du vrai back-end, exportées par backend/scripts/export_demo_fixtures.py.
 * Le formulaire reste modifiable : la fiche, l'offre, les questions et la grille sont alors
 * recalculées ici avec les mêmes règles (portage de form.py, templates.py, compliance.py et
 * question_bank.py). Pour des critères différents de l'exemple, la synthèse s'appuie sur
 * les réponses déclarées seulement.
 */
import { SOURCE_LABELS, STAGE } from "../lib/format";
import type { Api } from "./client";
import { ApiError } from "./client";
import FX from "./demo-fixtures.json";
import ROME from "./demo-rome.json";
import type {
  Agenda, ApplicationDetail, AuditItem, Billing, Comparison, Counts, Criterion, DebriefNote, Evaluation, GridQuestion, InterviewItem,
  Issue, JobForm, Me, Offer, PageId, Profile, Proposal, RecruitmentDetail, RecruitmentSummary, ScreeningQuestion, SentMessage, Slot,
} from "./types";

const fx = FX as any;
const rome = ROME as any;
const BASE = "https://wayloop.example";
const STEPS = ["Offre", "Candidatures", "Entretiens", "Débrief", "Décision"];
const PAGES: PageId[] = ["offre", "candidatures", "entretiens", "debrief", "decision"];
const STATE_LABEL: Record<string, string> = {
  offer_review: "Brouillon", collecting: "Candidatures en cours", shortlist_review: "Sélection à valider",
  scheduling: "Entretiens à organiser", interviewing: "Entretiens en cours", decision: "Décision à prendre", closed: "Clos", abandoned: "Abandonné",
};
const STEP: Record<string, number> = { offer_review: 1, collecting: 2, shortlist_review: 2, scheduling: 3, interviewing: 3, decision: 5, closed: 5, abandoned: 5 };
const KIND_PAGE: Record<string, PageId> = {
  offer: "offre", start_screening: "candidatures", shortlist: "candidatures", invite_manual: "entretiens", availability: "entretiens",
  decision: "decision", closing_messages: "decision", followup: "decision",
};
const LABELS: Record<string, string> = {
  "recruitment.created": "Recrutement créé", "recruitment.transition": "Étape suivante", "offer.proposed": "Offre rédigée",
  "offer.published": "Offre publiée", "proposal.created": "Étape préparée", "proposal.accepted": "Étape validée",
  "proposal.modified": "Étape validée après modification", "proposal.refused": "Étape reportée", "application.received": "Candidature reçue",
  "application.withdrawn": "Candidature retirée par le candidat", "screening.masked": "Informations sans rapport avec le poste masquées",
  "screening.criterion_evaluated": "Critère examiné", "screening.grouped": "Synthèse établie", "shortlist.candidate_added": "Candidat ajouté à la sélection",
  "shortlist.candidate_removed": "Candidat retiré de la sélection", "shortlist.validated": "Sélection validée", "grid.generated": "Grille d'entretien préparée",
  "grid.validated": "Grille d'entretien modifiée", "interview.invited": "Invitation à un entretien", "interview.booked": "Entretien confirmé",
  "interview.cancelled": "Date d'entretien retirée", "interview.attendance": "Présence à l'entretien", "debrief.validated": "Notes d'entretien enregistrées",
  "decision.made": "Décision prise", "message.sent": "E-mail envoyé", "message.bulk_sent": "E-mail groupé envoyé",
  "application.rejected": "Réponse envoyée en cours de processus", "billing.plan_changed": "Changement d'offre", "export.csv": "Export des candidatures",
};
const MESSAGE_KINDS: Record<string, string> = {
  acknowledgment: "Accusé de réception", invitation: "Invitation à un entretien", booking_confirmation: "Entretien confirmé",
  reminder: "Rappel d'entretien", unscheduled: "Entretien à déplacer", bulk: "Message", "closing:hired": "Réponse positive",
  "closing:rejected": "Réponse négative", "closing:rejected_interviewed": "Réponse négative après entretien",
};

let seq = 0;
const uid = (p: string) => `${p}-${(++seq).toString(36)}`;
const now = () => new Date().toISOString();
const clone = <T,>(x: T): T => JSON.parse(JSON.stringify(x));
const wait = (ms = 250) => new Promise((r) => setTimeout(r, ms));
const pl = (n: number, w: string, p?: string) => `${n} ${n > 1 ? p || w + "s" : w}`;
const err400 = (m: string, issues: Issue[] = []) => new ApiError(400, m, false, issues);

/* --- Texte : normalisation et référentiel ROME ---------------------------------------- */
const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").replace(/’/g, "'").replace(/\s+/g, " ").trim();
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
let idx: { app: string[]; comp: string[]; sav: string[] } | null = null;
const romeIdx = () => (idx ??= {
  app: rome.appellations.map((a: [string, string]) => norm(a[0])),
  comp: rome.competences.map((c: string) => norm(c)),
  sav: rome.savoirs.map((s: string[]) => norm(s[0])),
});
function search(query: string, normed: string[], limit: number): number[] {
  const q = norm(query);
  const words = (q.match(/[a-z0-9+#]+/g) || []).filter((w) => w.length > 1);
  if (!words.length) return [];
  const scored: [number, number, number][] = [];
  normed.forEach((label, i) => {
    if (!words.every((w) => label.includes(w))) return;
    const starts = label.startsWith(q);
    const wordStart = words.some((w) => new RegExp(`(?:^|\\s|/)${esc(w)}`).test(label));
    scored.push([starts ? 0 : wordStart ? 1 : 2, label.length, i]);
  });
  scored.sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2]);
  return scored.slice(0, limit).map((x) => x[2]);
}
const SAVOIRS: Record<string, string[]> = {
  logiciels: ["Logiciels, progiciels", "Langages informatiques", "Outils, machines, équipement matériel"],
  habilitations: ["Habilitations"],
};
const COMMUNES: [string, string, string][] = [
  ["Villeurbanne", "69100", "69, Rhône, Auvergne-Rhône-Alpes"], ["Lyon", "69001", "69, Rhône, Auvergne-Rhône-Alpes"],
  ["Vénissieux", "69200", "69, Rhône, Auvergne-Rhône-Alpes"], ["Bron", "69500", "69, Rhône, Auvergne-Rhône-Alpes"],
  ["Paris", "75001", "75, Paris, Île-de-France"], ["Marseille", "13001", "13, Bouches-du-Rhône, Provence-Alpes-Côte d'Azur"],
  ["Toulouse", "31000", "31, Haute-Garonne, Occitanie"], ["Nantes", "44000", "44, Loire-Atlantique, Pays de la Loire"],
  ["Bordeaux", "33000", "33, Gironde, Nouvelle-Aquitaine"], ["Lille", "59000", "59, Nord, Hauts-de-France"],
  ["Strasbourg", "67000", "67, Bas-Rhin, Grand Est"], ["Rennes", "35000", "35, Ille-et-Vilaine, Bretagne"],
  ["Montpellier", "34000", "34, Hérault, Occitanie"], ["Nice", "06000", "06, Alpes-Maritimes, Provence-Alpes-Côte d'Azur"],
  ["Grenoble", "38000", "38, Isère, Auvergne-Rhône-Alpes"], ["Saint-Étienne", "42000", "42, Loire, Auvergne-Rhône-Alpes"],
  ["Dijon", "21000", "21, Côte-d'Or, Bourgogne-Franche-Comté"], ["Angers", "49000", "49, Maine-et-Loire, Pays de la Loire"],
  ["Tours", "37000", "37, Indre-et-Loire, Centre-Val de Loire"], ["Clermont-Ferrand", "63000", "63, Puy-de-Dôme, Auvergne-Rhône-Alpes"],
  ["Rouen", "76000", "76, Seine-Maritime, Normandie"], ["Reims", "51100", "51, Marne, Grand Est"],
  ["Le Mans", "72000", "72, Sarthe, Pays de la Loire"], ["Brest", "29200", "29, Finistère, Bretagne"],
  ["Limoges", "87000", "87, Haute-Vienne, Nouvelle-Aquitaine"], ["Annecy", "74000", "74, Haute-Savoie, Auvergne-Rhône-Alpes"],
];

/* --- Rédaction conforme d'office (portage de compliance.py) ----------------------------- */
type Alert = { rule: string; level: "block" | "warn" | "info"; message: string; match?: string | null; start?: number; replacement?: string | null };
const B = "(?:(?<![\\p{L}\\p{N}_])(?=[\\p{L}\\p{N}_])|(?<=[\\p{L}\\p{N}_])(?![\\p{L}\\p{N}_]))";
const RULES = (fx.rules as any[]).map((r) => ({ ...r, re: new RegExp(r.pattern.replaceAll("\\b", B), "giu") }));
const GENDERED = new RegExp(`${B}(?:assistante|commerciale|vendeuse|serveuse|secr[ée]taire|h[oô]tesse|caissi[eè]re|coiffeuse|conseill[eè]re|charg[ée]e|technicienne|infirmi[eè]re|cuisini[eè]re|livreuse|employ[ée]e)${B}`, "iu");
const HF = /\(?\b(?:h\s*\/\s*f|f\s*\/\s*h)\b\)?|\(e\)|·e|femme\s*\/\s*homme|homme\s*\/\s*femme/i;
const DOUBLE_FORM = /[\p{L}\p{N}_]+\s\/\s[\p{L}\p{N}_]+/u;
const SALARY = /\d[\d\s.,]*\s*(?:k\s*)?(?:€|euros?|eur\b)|\bsmic\b|\bselon\s+(?:la\s+)?convention\b/i;
const EN_WORDS = new Set("the and with you your we are will for our job team skills experience required looking".split(" "));
const SHORT: Record<string, string> = fx.short_messages;

function checkText(text: string, isOffer = true): Alert[] {
  const out: Alert[] = [];
  const taken: [number, number][] = [];
  for (const r of RULES) {
    r.re.lastIndex = 0;
    for (const m of text.matchAll(r.re)) {
      const start = m.index ?? 0;
      if (taken.some(([a, b]) => a <= start && start < b)) continue;
      taken.push([start, start + m[0].length]);
      out.push({ rule: r.id, level: r.level, message: r.message, match: m[0], start, replacement: r.replacement });
    }
  }
  if (isOffer) {
    const first = text.trim().split("\n")[0] || "";
    if (first && !HF.test(first) && !DOUBLE_FORM.test(first) && GENDERED.test(first)) {
      out.push({ rule: "gendered_title", level: "warn", message: "Intitulé au féminin ou au masculin sans mention des deux sexes." });
    }
    if (!SALARY.test(text)) out.push({ rule: "salary_missing", level: "warn", message: SHORT.salary_missing });
    const words = norm(text).match(/[a-z]+/g) || [];
    if (words.length > 30 && words.filter((w) => EN_WORDS.has(w)).length / words.length > 0.08) {
      out.push({ rule: "language", level: "warn", message: SHORT.language });
    }
  }
  const order = { block: 0, warn: 1, info: 2 };
  return out.sort((a, b) => order[a.level] - order[b.level] || (a.start ?? 0) - (b.start ?? 0));
}

function applyReplacement(text: string, a: Alert): string {
  if (a.rule === "gendered_title") {
    const lines = text.split("\n");
    lines[0] = lines[0].trimEnd() + " (H/F)";
    return lines.join("\n");
  }
  if (a.replacement === null || a.replacement === undefined || !a.match) return text;
  const i = text.indexOf(a.match);
  if (i < 0) return text;
  let repl = a.replacement;
  if (repl && a.match[0] === a.match[0].toUpperCase() && a.match[0] !== a.match[0].toLowerCase()) repl = repl[0].toUpperCase() + repl.slice(1);
  return (text.slice(0, i) + repl + text.slice(i + a.match.length)).replace(/[ \t]{2,}/g, " ").replace(/\s+([,.;])/g, "$1").replace(/,\s*,/g, ",");
}

function sanitize(text: string, isOffer: boolean, field: string): [string, Issue[]] {
  let fixed = text;
  for (let n = 0; n < 20; n++) {
    const auto = checkText(fixed, isOffer).filter((a) => a.rule === "gendered_title" || (a.replacement && a.level !== "block"));
    if (!auto.length) break;
    const next = applyReplacement(fixed, auto[0]);
    if (next === fixed) break;
    fixed = next;
  }
  const issues = checkText(fixed, isOffer).filter((a) => a.level !== "info")
    .map((a) => ({ field, rule: a.rule, match: a.match ?? null, message: SHORT[a.rule] || a.message }));
  return [fixed, issues];
}

/* --- Formulaire -> fiche de poste, offre, questions (portage de form.py / templates.py) - */
const KINDS = ["experience", "competence", "diplome", "permis", "langue", "habilitation", "autre"];
const SKILL_LEVELS: Record<number, string> = { 1: "notions", 2: "autonome", 3: "expert" };
const DIPLOMA: Record<number, string> = Object.fromEntries(fx.lists.diploma_levels.map((d: any) => [d.value, d.label]));
const CEFR: string[] = fx.lists.cefr;
const SKILL_ANSWERS: [number, string][] = fx.answers.skill;
const DIPLOMA_ANSWERS: [number, string][] = fx.answers.diploma;
const LANGUAGE_ANSWERS: [string, string][] = fx.answers.language;
const clean = (s: unknown, n = 160) => String(s ?? "").replace(/\s+/g, " ").trim().slice(0, n);
const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
const lowerFirst = (s: string) => (s ? s[0].toLowerCase() + s.slice(1) : s);
const thousands = (v: number) => Math.round(v).toString().replace(/\B(?=(\d{3})+(?!\d))/g, " ");

function criterionLabel(kind: string, p: Record<string, any>): string {
  if (kind === "experience") {
    const y = Number(p.years) || 0;
    const dom = clean(p.domain);
    const base = y ? `${y} an${y > 1 ? "s" : ""} d'expérience` : "Une première expérience";
    return dom ? `${base} en ${dom}` : base;
  }
  if (kind === "competence") return `${clean(p.skill)} (niveau ${SKILL_LEVELS[Number(p.level) || 2] || "autonome"})`;
  if (kind === "diplome") return `${DIPLOMA[Number(p.level) || 4] || "Diplôme"} minimum${clean(p.domain) ? ` en ${clean(p.domain)}` : ""}`;
  if (kind === "permis") return `Permis ${p.category || "B"}`;
  if (kind === "langue") return `${cap(clean(p.language))} niveau ${p.level || "B1"}`;
  if (kind === "habilitation") return clean(p.name);
  return clean(p.text, 200);
}

function validateParams(kind: string, p: Record<string, any>): Record<string, any> {
  if (kind === "experience") {
    const years = Number(p.years) || 0;
    if (years < 0 || years > 30) throw err400("Nombre d'années d'expérience entre 0 et 30.");
    return { years, domain: clean(p.domain, 100) };
  }
  if (kind === "competence") {
    if (!clean(p.skill)) throw err400("Indiquez la compétence attendue.");
    return { skill: clean(p.skill, 100), level: Math.max(1, Math.min(3, Number(p.level) || 2)) };
  }
  if (kind === "diplome") {
    const level = Number(p.level) || 4;
    if (!DIPLOMA[level]) throw err400("Niveau de diplôme inconnu.");
    return { level, domain: clean(p.domain, 100) };
  }
  if (kind === "permis") return { category: String(p.category || "B").toUpperCase() };
  if (kind === "langue") {
    const level = String(p.level || "B1").toUpperCase();
    if (!CEFR.includes(level) || !clean(p.language)) throw err400("Indiquez la langue et un niveau de A1 à C2.");
    return { language: clean(p.language, 40), level };
  }
  if (kind === "habilitation") {
    if (!clean(p.name)) throw err400("Indiquez l'habilitation ou la certification.");
    return { name: clean(p.name, 120) };
  }
  if (!clean(p.text)) throw err400("Décrivez le critère.");
  return { text: clean(p.text, 200) };
}

function buildProfile(form: JobForm): { profile: Profile & Record<string, any>; issues: Issue[] } {
  const issues: Issue[] = [];
  const textField = (v: unknown, field: string, n: number) => {
    const c = clean(v, n);
    if (!c) return "";
    const [fixed, found] = sanitize(c, false, field);
    issues.push(...found);
    return fixed;
  };
  let title = textField(form.title, "title", 140);
  if (title.length < 3) issues.push({ field: "title", message: "Indiquez l'intitulé du poste." });
  const [t2, found] = sanitize(title, true, "title");
  title = t2;
  issues.push(...found.filter((i) => !["salary_missing", "language"].includes(i.rule || "")));
  if (title && !HF.test(title) && !DOUBLE_FORM.test(title)) title = `${title} (H/F)`;

  const criteria: Criterion[] = [];
  (form.criteria || []).forEach((raw, i) => {
    if (!KINDS.includes(raw.kind)) return issues.push({ field: `criteria.${i}`, message: `Type de critère inconnu : ${raw.kind}` });
    let params: Record<string, any>;
    try { params = validateParams(raw.kind, raw.params || {}); } catch (e) { return issues.push({ field: `criteria.${i}`, message: (e as Error).message }); }
    let label = criterionLabel(raw.kind, params);
    const [fixed, f2] = sanitize(label, false, `criteria.${i}`);
    if (f2.length) return issues.push(...f2);
    if (raw.kind === "autre") { params.text = fixed; label = fixed; }
    criteria.push({ id: `c${criteria.length + 1}`, label, kind: raw.kind, required: !!raw.required, params });
  });
  if (criteria.filter((c) => c.required).length > 3) issues.push({ field: "criteria", message: "Gardez au plus 3 critères indispensables : au-delà, on écarte des candidats valables." });

  const has = (v: unknown) => v !== undefined && v !== null && v !== "";
  const period = form.salary_period || "mois";
  let salary: Profile["salary"] = { min: null, max: null, period, text: null };
  if (has(form.salary_min) || has(form.salary_max)) {
    let lo = Number(has(form.salary_min) ? form.salary_min : form.salary_max);
    let hi = Number(has(form.salary_max) ? form.salary_max : form.salary_min);
    if (lo > hi) [lo, hi] = [hi, lo];
    const f = (v: number) => (hi >= 100 ? thousands(v) : v.toFixed(2).replace(".", ","));
    salary = { min: lo, max: hi, period, text: lo === hi ? `${f(lo)} € brut / ${period}` : `${f(lo)} à ${f(hi)} € brut / ${period}` };
  } else issues.push({ field: "salary", message: "Indiquez la rémunération proposée (brut)." });
  const contract = clean(form.contract, 40);
  if (contract && !fx.lists.contracts.includes(contract)) issues.push({ field: "contract", message: "Type de contrat inconnu." });
  const duration = clean(form.contract_duration, 40);
  const remote = ({ non: null, partiel: "Télétravail partiel possible", total: "Poste en télétravail" } as Record<string, string | null>)[form.remote || "non"] ?? null;
  const missions = (form.missions || []).map((m, i) => textField(m, `missions.${i}`, 240)).filter(Boolean).slice(0, 8);
  const benefits = (form.benefits || []).map((b, i) => textField(b, `benefits.${i}`, 120)).filter(Boolean).slice(0, 6);
  const profile = {
    title, rome_code: clean(form.rome_code, 5) || null, rome_label: clean(form.rome_label, 140) || null, missions, criteria, salary,
    hours: textField(form.hours, "hours", 120) || null, location: clean(form.location, 160) || null,
    location_citycode: clean(form.location_citycode, 10) || null,
    contract: (contract && duration ? `${contract} (${duration})` : contract) || null, start_date: clean(form.start_date, 60) || null,
    remote, company_pitch: textField(form.company_pitch, "company_pitch", 600) || null, benefits,
  };
  return { profile, issues };
}

function offerFromProfile(p: Profile, company: string): { short: string; long: string } {
  const title = p.title || "Poste";
  const req = p.criteria.filter((c) => c.required).map((c) => c.label);
  const nice = p.criteria.filter((c) => !c.required).map((c) => c.label);
  const sal = p.salary?.text;
  const missions = p.missions || [];
  const facts = [p.contract, p.location, sal].filter(Boolean);
  let short = `${company} recrute : ${title}`;
  if (facts.length) short += " — " + facts.join(" · ");
  short += ".";
  if (missions.length) short += " Missions : " + missions.slice(0, 3).map(lowerFirst).join("; ") + ".";
  if (req.length) short += " Indispensable : " + req.join(", ") + ".";
  if (p.hours) short += ` Horaires : ${p.hours}.`;
  short += " Réponse assurée à chaque candidature.";
  const lines = [title, "", p.company_pitch || `${company} recrute.`, ""];
  if (missions.length) lines.push("Vos missions", ...missions.map((m) => `- ${m}`), "");
  if (req.length || nice.length) lines.push("Votre profil", ...req.map((r) => `- Indispensable : ${r}`), ...nice.map((n) => `- Apprécié : ${n}`), "");
  lines.push("Conditions");
  for (const [label, key] of [["Contrat", "contract"], ["Horaires", "hours"], ["Lieu", "location"], ["Prise de poste", "start_date"]] as const) {
    if (p[key]) lines.push(`- ${label} : ${p[key]}`);
  }
  if (sal) lines.push(`- Rémunération : ${sal}`);
  if (p.remote) lines.push(`- ${p.remote}`);
  for (const b of p.benefits || []) lines.push(`- ${b}`);
  lines.push("", "Comment se passe le recrutement",
    "- Vous répondez à quelques questions sur les critères du poste et joignez votre CV.",
    "- Vous recevez un accusé de réception dès l'envoi de votre candidature.",
    "- Les entretiens suivent les mêmes questions pour toutes les personnes rencontrées.",
    "- Chaque candidat reçoit une réponse, positive ou non.");
  return { short: short.slice(0, 700), long: lines.join("\n").slice(0, 4000) };
}

function questionsFor(p: Profile): ScreeningQuestion[] {
  return p.criteria.map((c) => {
    const k = c.kind;
    const q = c.params || {};
    const base = { id: c.id, kind: k, required: k !== "autre" };
    if (k === "experience") return { ...base, label: `Combien d'années d'expérience avez-vous en ${q.domain || "ce métier"} ?`, input: "number", min: 0, max: 50, unit: "ans" };
    if (k === "competence") return { ...base, label: `Quel est votre niveau en ${q.skill} ?`, input: "select", options: SKILL_ANSWERS.map(([value, label]) => ({ value, label })) };
    if (k === "diplome") return { ...base, label: "Quel est votre plus haut diplôme obtenu ?", input: "select", options: DIPLOMA_ANSWERS.map(([value, label]) => ({ value, label })) };
    if (k === "permis") return { ...base, label: `Avez-vous le permis ${q.category} ?`, input: "yesno" };
    if (k === "langue") return { ...base, label: `Quel est votre niveau en ${String(q.language).toLowerCase()} ?`, input: "select", options: LANGUAGE_ANSWERS.map(([value, label]) => ({ value, label })), help: "A1-A2 : notions · B1-B2 : courant · C1-C2 : très bonne maîtrise" };
    if (k === "habilitation") return { ...base, label: `Avez-vous « ${q.name} » en cours de validité ?`, input: "yesno" };
    return { ...base, label: q.text || c.label, input: "text", max: 500 };
  }) as ScreeningQuestion[];
}

function cleanAnswers(p: Profile, raw: Record<string, any>): Record<string, any> {
  const out: Record<string, any> = {};
  for (const q of questionsFor(p)) {
    const v = raw[q.id];
    if (v === undefined || v === null || v === "") {
      if (q.required) throw err400(`Merci de répondre à la question : ${q.label}`);
      continue;
    }
    if (q.input === "number") {
      const n = Number(String(v).replace(",", "."));
      if (Number.isNaN(n)) throw err400(`Réponse numérique attendue : ${q.label}`);
      out[q.id] = Math.max(0, Math.min(50, n));
    } else if (q.input === "yesno") out[q.id] = ["true", "1", "oui", "yes"].includes(String(v).toLowerCase());
    else if (q.input === "select") {
      const o = q.options!.find((x) => String(x.value) === String(v));
      if (!o) throw err400(`Réponse non reconnue : ${q.label}`);
      out[q.id] = o.value;
    } else out[q.id] = clean(v, 500);
  }
  return out;
}

function evaluateDeclared(c: Criterion, answer: any): [Evaluation["status"], string] {
  const p = c.params || {};
  if (answer === undefined || answer === null) return ["unknown", "Pas de réponse"];
  if (c.kind === "experience") {
    const need = Number(p.years) || 0;
    const got = Number(answer);
    const txt = `${got} an${got > 1 ? "s" : ""}`;
    if (got >= Math.max(need, need === 0 ? 0.5 : need)) return ["met", txt];
    return [got >= need / 2 && got > 0 ? "partial" : "not_met", txt];
  }
  if (c.kind === "competence" || c.kind === "diplome") {
    const need = Number(p.level) || (c.kind === "competence" ? 2 : 4);
    const got = Number(answer);
    const txt = (c.kind === "competence" ? SKILL_ANSWERS : DIPLOMA_ANSWERS).find(([v]) => v === got)?.[1] || String(got);
    const partial = c.kind === "competence" ? got === need - 1 && got > 0 : got === need - 1;
    return [got >= need ? "met" : partial ? "partial" : "not_met", txt];
  }
  if (c.kind === "permis" || c.kind === "habilitation") return answer ? ["met", "Oui"] : ["not_met", "Non"];
  if (c.kind === "langue") {
    if (answer === "none") return ["not_met", "Ne la parle pas"];
    const need = CEFR.indexOf(p.level || "B1");
    const got = CEFR.indexOf(answer);
    return [got >= need ? "met" : got === need - 1 ? "partial" : "not_met", String(answer)];
  }
  return ["unknown", String(answer)];
}

/** Synthèse sans lecture du CV (démo, critères différents de l'exemple) : réponses déclarées seulement. */
function declaredEval(c: Criterion, answers: Record<string, any> | null): Evaluation {
  const base = { criterion_id: c.id, label: c.label, required: c.required, excerpts: [] as string[] };
  if (!answers || !(c.id in answers)) {
    return { ...base, status: "unknown", justification: "Non renseigné par le candidat : à vérifier dans son CV.", declared: null, evidence: "cv" };
  }
  const [status, declared] = evaluateDeclared(c, answers[c.id]);
  if (c.kind === "autre") return { ...base, status: "unknown", declared, evidence: "declared", justification: "Réponse libre du candidat, à apprécier." };
  return { ...base, status, declared, evidence: "declared",
    justification: status === "met" || status === "partial" ? "Déclaré par le candidat, non retrouvé dans le CV : à vérifier en entretien." : "Selon la réponse du candidat." };
}

function computeGroup(evals: Evaluation[]): string {
  const req = evals.filter((e) => e.required);
  if (!req.length) return "meets";
  const eff = (e: Evaluation) => (e.status === "met" && e.evidence === "inconsistent" ? "partial" : e.status);
  if (req.every((e) => eff(e) === "met")) return "meets";
  if (req.some((e) => ["met", "partial"].includes(eff(e)))) return "partial";
  return "does_not";
}

/* --- Questions d'entretien (portage de question_bank.build_grid) ----------------------- */
function gridGenerate(p: Profile): GridQuestion[] {
  const bank: any[] = fx.question_bank;
  const crit = p.criteria;
  const context = norm([p.title, ...p.missions, ...crit.map((c) => c.label)].join(" "));
  const used = new Set<number>();
  const out: Omit<GridQuestion, "id">[] = [];
  const pick = (text: string): number | null => {
    const t = norm(text);
    let best = 0, bestI: number | null = null;
    bank.forEach((q, i) => {
      if (used.has(i)) return;
      const score = q.themes.filter((th: string) => t.includes(th)).length;
      if (score > best) { best = score; bestI = i; }
    });
    return bestI;
  };
  for (const c of [...crit.filter((c) => c.required), ...crit.filter((c) => !c.required)]) {
    if (out.length >= 4 || ["permis", "diplome", "habilitation"].includes(c.kind)) continue;
    let i: number | null = pick(c.label + " " + context);
    if (i === null) i = used.has(5) ? null : 5;
    if (i === null) continue;
    used.add(i);
    const q = bank[i];
    out.push({ text: q.text.replace("{criterion}", c.label.toLowerCase()), kind: q.kind, criterion_id: c.id, anchors: { ...q.anchors } });
  }
  for (let n = 0; n < 6 && out.length < 5; n++) {
    let i: number | null = pick(context);
    if (i === null) { const j = bank.findIndex((_, k) => !used.has(k)); i = j < 0 ? null : j; }
    if (i === null) break;
    used.add(i);
    const q = bank[i];
    out.push({ text: q.text.replace("en lien avec « {criterion} »", "proche de ce que vous feriez ici"), kind: q.kind, criterion_id: null, anchors: { ...q.anchors } });
  }
  const mes = fx.mise_en_situation;
  if (mes.themes.some((th: string) => context.includes(th))) out.push({ text: mes.text, kind: mes.kind, criterion_id: null, anchors: { ...mes.anchors } });
  return out.slice(0, 6).map((q, i) => ({ ...q, id: `q${i + 1}` }));
}

/* --- Candidats fictifs : réponses par type de critère (si l'exemple est modifié) ----- */
const PERSONAS: Record<string, { diplome: number; langue: string; habilitation: boolean }> = {
  "Camille Martin": { diplome: 5, langue: "B2", habilitation: true }, "Karim Benali": { diplome: 4, langue: "B1", habilitation: true },
  "Julie Moreau": { diplome: 4, langue: "A2", habilitation: false }, "Thomas Petit": { diplome: 3, langue: "none", habilitation: true },
  "Inès Lefèvre": { diplome: 6, langue: "C1", habilitation: false }, "Lucas Garnier": { diplome: 5, langue: "B1", habilitation: false },
  "Sarah Nguyen": { diplome: 5, langue: "B2", habilitation: true },
};
function personaAnswers(name: string, raw: Record<string, any>, crit: Criterion[]): Record<string, any> {
  const p = PERSONAS[name];
  const out: Record<string, any> = {};
  for (const c of crit) {
    if (c.kind === "experience") out[c.id] = raw.c1;
    else if (c.kind === "competence") out[c.id] = raw.c2;
    else if (c.kind === "permis") out[c.id] = raw.c3;
    else if (c.kind === "diplome") out[c.id] = p.diplome;
    else if (c.kind === "langue") out[c.id] = p.langue;
    else if (c.kind === "habilitation") out[c.id] = p.habilitation;
    else out[c.id] = "Oui";
  }
  return out;
}
const critSig = (crit: Criterion[]) => JSON.stringify(crit.map((c) => [c.kind, c.required, c.params]));
const FX_SIG = critSig(fx.profile.criteria);

/* --- Textes envoyés ----------------------------------------------------------------- */
const TZ = "Europe/Paris";
const frDateTime = (iso: string) => {
  const d = new Date(iso);
  const day = d.toLocaleDateString("fr-FR", { timeZone: TZ, weekday: "long", day: "numeric", month: "long" });
  const t = d.toLocaleTimeString("fr-FR", { timeZone: TZ, hour: "numeric", minute: "2-digit" }).replace(":", "h");
  return `${day} à ${t}`;
};

/* --- État de la démo ------------------------------------------------------------------ */
type DApp = ApplicationDetail & { cand_token: string; raw: Record<string, any> | null; fxi: any | null; order: number; sent: SentMessage[] };
type DIv = InterviewItem & { token: string };
type Rec = {
  id: string; title: string; state: string; created_at: string; published_at: string | null; closed_at: string | null; shortlisted_at: string | null;
  profile: Profile; proposals: Proposal[]; offers: Offer[]; grid: RecruitmentDetail["grid"]; apps: DApp[];
  slots: (Slot & { iv: string | null })[]; ivs: DIv[]; outcome: string | null; seconds: number;
  location: string; interview_minutes: number; audit: AuditItem[]; token: string;
};

export function createDemoApi(): Api {
  const recs: Rec[] = [];
  let auditId = 0;
  let plan: "free" | "premium" = "free";
  let interval: "month" | "year" = "year";
  const t = () => Date.now();
  const company = { id: "c1", name: fx.company.name, slug: fx.company.slug, address: fx.company.address,
    headcount: 18, siren: fx.company.siren, naf_code: fx.company.naf_code, headcount_range: fx.company.headcount_range };
  const user = { id: "u1", email: "paul@negoce-durand.example", name: "Paul Durand", phone: "", role: "owner", theme: "light" as "light" | "dark" };
  const has = (f: string) => plan === "premium" && fx.plans.premium.features.includes(f);
  const requireFeature = (f: string) => { if (!has(f)) throw new ApiError(402, `Fonctionnalité incluse dans Premium : ${fx.features[f]}.`, true); };
  const active = () => recs.filter((r) => !["closed", "abandoned"].includes(r.state)).length;
  const me = (): Me => ({
    ...clone(user), company: clone(company),
    app: { name: "WayLoop", demo_mode: true, environment: "demo" },
    plan: { id: plan, name: fx.plans[plan].name, features: [...fx.plans[plan].features], active_recruitments_limit: fx.plans[plan].limit },
  });

  const get = (id: string) => {
    const r = recs.find((x) => x.id === id);
    if (!r) throw new ApiError(404, "Recrutement introuvable.");
    return r;
  };
  const log = (r: Rec, action: string, details: Record<string, any> = {}, actor = "system", subject?: string) => {
    const h = Math.abs([...`${auditId}${action}${JSON.stringify(details)}`].reduce((a, c) => (a * 31 + c.charCodeAt(0)) | 0, 7)).toString(16);
    r.audit.push({ id: ++auditId, at: now(), actor_type: actor, action, label: LABELS[action] || action, entity: null, subject, details, hash: h.padStart(12, "0") });
  };
  const mail = (r: Rec, a: DApp, kind: string, subject: string, body: string) => {
    a.sent.unshift({ id: uid("m"), kind, label: MESSAGE_KINDS[kind] || "Message", subject, body, status: "sent", created_at: now() });
    log(r, "message.sent", { kind, channel: "email", ok: true }, "system", a.name);
  };
  const propose = (r: Rec, kind: string, step: number, title: string, summary: string, payload: any) => {
    if (kind !== "followup") r.proposals.filter((p) => p.kind === kind && p.status === "pending").forEach((p) => (p.status = "superseded"));
    const p: Proposal = { id: uid("p"), kind, step, page: KIND_PAGE[kind], title, summary, payload, status: "pending", created_at: now() };
    r.proposals.push(p);
    log(r, "proposal.created", { kind });
    return p;
  };
  const close = (r: Rec, p: Proposal, status: "accepted" | "modified" | "refused", details: Record<string, any> = {}) => {
    if (p.status !== "pending") throw new ApiError(409, "Cette étape a déjà été traitée.");
    p.status = status;
    p.decided_at = now();
    log(r, `proposal.${status}`, { kind: p.kind, ...details }, "user");
  };
  const go = (r: Rec, to: string, actor = "system") => { if (r.state !== to) { log(r, "recruitment.transition", { from: r.state, to }, actor); r.state = to; } };
  const pending = (r: Rec, kind: string) => r.proposals.find((p) => p.kind === kind && p.status === "pending");
  const first = (a: DApp) => a.name.split(" ")[0];
  const render = (r: Rec, tpl: string, a: DApp) => tpl.replaceAll("{prénom}", first(a)).replaceAll("{prenom}", first(a))
    .replaceAll("{nom}", a.name.split(" ").slice(1).join(" ")).replaceAll("{poste}", r.profile.title || r.title)
    .replaceAll("{entreprise}", company.name).replaceAll("{lien}", `${BASE}/candidat/${a.cand_token}`).replaceAll("Bonjour ,", "Bonjour,");
  const isOpen = (r: Rec) => !!r.published_at && ["collecting", "shortlist_review", "scheduling", "interviewing"].includes(r.state);
  const happened = (iv: DIv) => iv.status === "attended" || (iv.status === "booked" && !!iv.start && Date.parse(iv.start) < t());
  const noted = (r: Rec, iv: DIv) => r.apps.find((a) => a.id === iv.application_id)?.debrief?.status === "validated";

  const stepOf = (r: Rec) => {
    if (r.state !== "interviewing") return STEP[r.state];
    if (pending(r, "decision")) return 5;
    const ivs = r.ivs.filter((i) => i.status !== "cancelled");
    if (ivs.some((i) => happened(i) && !noted(r, i))) return 4;
    if (ivs.some((i) => i.status === "invited" || (i.status === "booked" && !happened(i)))) return 3;
    return ivs.length ? 4 : 3;
  };
  const mainPending = (r: Rec) => {
    const cur = STEP[r.state];
    return r.proposals.filter((p) => p.status === "pending")
      .sort((a, b) => Number(a.step !== cur) - Number(b.step !== cur) || a.step - b.step || Date.parse(b.created_at) - Date.parse(a.created_at))[0];
  };

  /* Offre et grille */
  const offerOf = (r: Rec) => r.offers[r.offers.length - 1] || null;
  const saveOffer = (r: Rec, short: string, long: string, by: "system" | "user") => {
    const [l, i1] = sanitize(long, true, "long");
    const [s, i2] = sanitize(short, false, "short");
    const issues = [...i1, ...i2];
    if (issues.length) throw err400(issues[0].match ? `Retirez « ${issues[0].match} » : ${issues[0].message}` : issues[0].message, issues);
    const prev = offerOf(r);
    const o: Offer = { id: uid("o"), version: r.offers.length + 1, short: s, long: l, status: "draft", channels: [], created_by: by, created_at: now() };
    if (prev?.status === "published") { o.status = "published"; o.channels = prev.channels; prev.status = "replaced"; }
    r.offers.push(o);
    log(r, "offer.proposed", { version: o.version, by });
    return o;
  };
  const sameAsExample = (r: Rec) => critSig(r.profile.criteria) === FX_SIG;

  /* Candidatures */
  const receive = (r: Rec, d: { name: string; email: string; source: string; message?: string | null; cv_filename?: string | null;
    cv_text?: string | null; pool_consent?: boolean; raw: Record<string, any> | null; fxi?: any }) => {
    const a: DApp = {
      id: uid("a"), name: d.name, source: d.source, status: "received", group: null, shortlisted: false, rescued: false,
      created_at: now(), screened: false, has_cv: !!d.cv_filename, pool_consent: !!d.pool_consent, anonymized: false,
      evaluations: [], interview: null, debrief_status: null, email: d.email, phone: null, message: d.message || null,
      facts: [], cv_filename: d.cv_filename || null, cv_text: d.cv_text || d.message || null, cv_link: null,
      debrief: null, has_answers: !!d.raw, answers: [], cand_token: uid("c"), raw: d.raw, fxi: d.fxi || null, order: r.apps.length, sent: [],
    };
    r.apps.push(a);
    log(r, "application.received", { source: a.source, has_cv: a.has_cv }, "candidate", a.name);
    const [subj, body] = fx.texts.acknowledgment;
    mail(r, a, "acknowledgment", subj, body.replaceAll("{prénom}", first(a)).replaceAll("{lien_donnees}", `${BASE}/candidat/${a.cand_token}`)
      .replaceAll("{lien_notice}", `${BASE}/confidentialite/${company.slug}`));
    afterNew(r, a);
    return a;
  };
  const afterNew = (r: Rec, a: DApp) => {
    if (r.state === "collecting") {
      const n = r.apps.filter((x) => x.status !== "withdrawn").length;
      const p = pending(r, "start_screening");
      if (n >= 5 && !p) propose(r, "start_screening", 2, `${n} candidatures reçues`, fx.start_screening.summary, { count: n });
      else if (p) { p.title = `${n} candidatures reçues`; p.payload = { count: n }; }
    } else if (["shortlist_review", "scheduling", "interviewing"].includes(r.state)) screenApp(r, a);
  };
  const screenApp = (r: Rec, a: DApp) => {
    a.screened = true;
    if (a.status === "received") a.status = "screened";
    if (a.fxi && sameAsExample(r)) {
      a.evaluations = clone(a.fxi.evaluations);
      a.group = a.fxi.group;
    } else {
      a.evaluations = r.profile.criteria.map((c) => declaredEval(c, a.raw));
      a.group = !a.raw && !a.cv_text ? "unreadable" : computeGroup(a.evaluations);
    }
    log(r, "screening.masked", { categories: { identite: 2, contact: 1 } }, "system", a.name);
    for (const e of a.evaluations) log(r, "screening.criterion_evaluated", { criterion_id: e.criterion_id, status: e.status, evidence: e.evidence }, "system", a.name);
    log(r, "screening.grouped", { group: a.group }, "system", a.name);
  };
  const runScreening = async (r: Rec) => {
    await wait(500);
    const apps = r.apps.filter((a) => a.status !== "withdrawn");
    if (!apps.length) throw err400("Aucune candidature pour l'instant.");
    apps.filter((a) => !a.screened).forEach((a) => screenApp(r, a));
    if (r.state === "collecting") go(r, "shortlist_review");
    const c = (g: string) => apps.filter((a) => a.group === g).length;
    const unconfirmed = (a: DApp) => a.evaluations.filter((e) => e.required && ["declared", "inconsistent"].includes(e.evidence || "")).length;
    const desired = (a: DApp) => a.evaluations.filter((e) => !e.required && e.status === "met").length;
    const meets = apps.filter((a) => a.group === "meets").sort((x, y) => unconfirmed(x) - unconfirmed(y) || desired(y) - desired(x) || x.order - y.order);
    const confirmed = meets.filter((a) => unconfirmed(a) === 0);
    const proposed = (confirmed.length >= 3 ? confirmed : meets).slice(0, 8).map((a) => a.id);
    const m = c("meets");
    let summary = `${m} candidat${m > 1 ? "s" : ""} rempli${m > 1 ? "ssent" : "t"} vos critères indispensables, ${c("partial")} en partie.`;
    summary += proposed.length ? ` ${proposed.length} ${proposed.length > 1 ? "sont pré-cochés" : "est pré-coché"} : validez ou ajustez.` : " Choisissez qui rencontrer.";
    propose(r, "shortlist", 2, "Sélection à valider", summary, { application_ids: proposed });
  };

  /* Entretiens */
  const newIv = (r: Rec, a: DApp): DIv => {
    const iv: DIv = { id: uid("i"), application_id: a.id, name: a.name, recruitment_id: r.id, recruitment_title: r.title, status: "invited",
      start: null, end: null, location: r.location, invited_at: now(), token: uid("rdv") };
    r.ivs.push(iv);
    a.status = "invited";
    log(r, "interview.invited", {}, "system", a.name);
    return iv;
  };
  const suggestRanges = () => {
    const d = new Date(t());
    const days = (8 - d.getDay()) % 7 || 7;
    const monday = new Date(d.getFullYear(), d.getMonth(), d.getDate() + days);
    const out: { start: string; end: string }[] = [];
    for (const off of [1, 3]) for (const [h1, h2] of [[9, 12], [14, 17]]) {
      const s = new Date(monday); s.setDate(monday.getDate() + off); s.setHours(h1, 0, 0, 0);
      const e = new Date(s); e.setHours(h2);
      out.push({ start: s.toISOString(), end: e.toISOString() });
    }
    return out.slice(0, 3);
  };
  const addSlots = (r: Rec, ranges: { start: string; end: string }[]) => {
    let n = 0;
    for (const rg of ranges) {
      let x = new Date(rg.start).getTime();
      const end = new Date(rg.end).getTime();
      while (x + r.interview_minutes * 60000 <= end) {
        if (x > t()) { r.slots.push({ id: uid("s"), start: new Date(x).toISOString(), end: new Date(x + r.interview_minutes * 60000).toISOString(), iv: null }); n++; }
        x += (r.interview_minutes + 15) * 60000;
      }
    }
    return n;
  };
  const freeSlots = (r: Rec) => r.slots.filter((s) => !s.iv && Date.parse(s.start) > t() + 2 * 3600_000);
  const inviteWithBooking = (r: Rec) => {
    let n = 0;
    for (const a of r.apps.filter((x) => x.shortlisted && x.status === "shortlisted")) {
      const iv = newIv(r, a);
      const [subj, b] = fx.texts.invitation;
      mail(r, a, "invitation", subj, b.replaceAll("{prénom}", first(a)).replaceAll("{lien_rdv}", `${BASE}/rdv/${iv.token}`));
      n++;
    }
    return n;
  };
  const confirm = (r: Rec, iv: DIv, by: string) => {
    const a = r.apps.find((x) => x.id === iv.application_id)!;
    a.status = "booked";
    log(r, "interview.booked", {}, by, a.name);
    mail(r, a, "booking_confirmation", `Entretien confirmé : ${frDateTime(iv.start!)}`,
      `Bonjour ${first(a)},\n\nVotre entretien pour le poste « ${r.profile.title} » est confirmé : ${frDateTime(iv.start!)}.\nLieu : ${iv.location || "précisé par l'entreprise"}\n\nVous recevrez un rappel la veille. Pour déplacer ou annuler : ${BASE}/rdv/${iv.token}\n\nL'entretien suit les mêmes questions pour toutes les personnes rencontrées, toutes liées au poste.\n\n${company.name}`);
  };
  const book = (r: Rec, iv: DIv, slotId: string) => {
    const s = r.slots.find((x) => x.id === slotId);
    if (!s) throw new ApiError(404, "Créneau introuvable.");
    if (s.iv && s.iv !== iv.id) throw new ApiError(409, "Ce créneau vient d'être pris. Choisissez-en un autre.");
    r.slots.filter((x) => x.iv === iv.id).forEach((x) => (x.iv = null));
    s.iv = iv.id;
    Object.assign(iv, { start: s.start, end: s.end, status: "booked", booked_at: now(), location: r.location });
    confirm(r, iv, "candidate");
  };
  const release = (r: Rec, iv: DIv) => r.slots.filter((s) => s.iv === iv.id).forEach((s) => (s.iv = null));
  const maybeDecision = (r: Rec) => {
    if (r.state !== "interviewing") return;
    const met = r.apps.filter((a) => a.shortlisted && !["withdrawn", "rejected"].includes(a.status));
    const ivsOf = (a: DApp) => r.ivs.filter((i) => i.application_id === a.id);
    const waiting = met.filter((a) => ivsOf(a).some((i) => ["invited", "booked"].includes(i.status)));
    const done = met.filter((a) => a.debrief?.status === "validated");
    const toNote = met.filter((a) => ivsOf(a).some((i) => i.status === "attended") && a.debrief?.status !== "validated");
    if (done.length && !waiting.length && !toNote.length && !pending(r, "decision")) {
      propose(r, "decision", 5, "Comparez et choisissez", `${pl(done.length, "entretien")} ${done.length > 1 ? "notés" : "noté"} : le comparatif est prêt.`,
        { application_ids: done.map((a) => a.id) });
    }
  };

  /* Décision */
  const comparison = (r: Rec): Comparison => {
    const qs = r.grid?.questions || [];
    const cands = r.apps.filter((a) => a.shortlisted && !["withdrawn", "rejected"].includes(a.status)).map((a) => {
      const notes = a.debrief?.notes || {};
      const scores = Object.fromEntries(qs.map((q) => [q.id, notes[q.id]?.score ?? null]));
      const filled = Object.values(scores).filter(Boolean) as number[];
      return { application_id: a.id, name: a.name, debrief_status: a.debrief?.status || null, scores,
        notes: Object.fromEntries(qs.map((q) => [q.id, notes[q.id]?.notes ?? null])), total: filled.length ? filled.reduce((x, y) => x + y, 0) : null,
        answered: filled.length, overall: a.debrief?.overall };
    });
    return { questions: qs.map((q) => ({ id: q.id, text: q.text })), candidates: cands, max_total: 3 * qs.length };
  };
  const decide = (r: Rec, appId: string | null) => {
    if (r.state === "interviewing") go(r, "decision", "user");
    else if (r.state !== "decision") throw err400("La décision se prend après les entretiens.");
    const p = pending(r, "decision");
    if (p) close(r, p, "accepted", { hired: !!appId });
    log(r, "decision.made", { outcome: appId ? "hired" : "abandoned" }, "user");
    const kinds: Record<string, number> = { hired: 0, rejected_interviewed: 0, rejected: 0 };
    const msgs = r.apps.filter((a) => !["withdrawn", "rejected"].includes(a.status) && !a.anonymized).map((a) => {
      const kind = a.id === appId ? "hired" : a.status === "interviewed" || r.ivs.some((i) => i.application_id === a.id && i.status === "attended") ? "rejected_interviewed" : "rejected";
      kinds[kind]++;
      return { application_id: a.id, kind };
    });
    const templates: Record<string, any> = {};
    for (const k of Object.keys(kinds)) if (kinds[k]) {
      const [subject, body] = fx.texts[`closing_${k}`];
      templates[k] = { subject, body, count: kinds[k] };
    }
    propose(r, "closing_messages", 5, "Réponses aux candidats", `${pl(msgs.length, "message")} ${msgs.length > 1 ? "prêts" : "prêt"} : chaque candidat reçoit une réponse. Relisez puis envoyez.`,
      { messages: msgs, templates, hired: appId });
  };
  const withdrawOffer = (r: Rec) => {
    const o = offerOf(r);
    if (o) { o.status = "closed"; o.channels = o.channels.map((c) => ({ ...c, status: "closed", at: now() })); }
  };

  const counts = (r: Rec): Counts => {
    const apps = r.apps.filter((a) => a.status !== "withdrawn");
    const ivs = r.ivs.filter((i) => i.status !== "cancelled");
    const met = apps.filter((a) => a.shortlisted && a.status !== "rejected");
    return {
      applications: apps.length, unscreened: apps.filter((a) => !a.screened).length, shortlisted: met.length, interviews: ivs.length,
      to_schedule: ivs.filter((i) => i.status === "invited").length,
      upcoming: ivs.filter((i) => i.status === "booked" && i.start && Date.parse(i.start) >= t()).length,
      to_note: met.filter((a) => r.ivs.some((i) => i.application_id === a.id && happened(i)) && a.debrief?.status !== "validated").length,
      noted: met.filter((a) => a.debrief?.status === "validated").length,
    };
  };
  const summary = (r: Rec): RecruitmentSummary => {
    const m = mainPending(r);
    const step = stepOf(r);
    const label = r.state === "interviewing" && step === 4 ? "Entretiens à noter" : r.state === "interviewing" && step === 5 ? STATE_LABEL.decision : STATE_LABEL[r.state];
    return { id: r.id, title: r.title, state: r.state, state_label: label,
      step, page: PAGES[step - 1], created_at: r.created_at, published_at: r.published_at, closed_at: r.closed_at,
      applications: r.apps.filter((a) => a.status !== "withdrawn").length, outcome: r.outcome,
      pending: m ? { id: m.id, kind: m.kind, title: m.title, page: KIND_PAGE[m.kind] } : null };
  };
  const detail = (r: Rec): RecruitmentDetail => {
    const apps = r.apps.filter((a) => a.status !== "withdrawn");
    const groups: Record<string, number> = {};
    const sources: Record<string, number> = {};
    apps.forEach((a) => { groups[a.group || "unscreened"] = (groups[a.group || "unscreened"] || 0) + 1; sources[a.source] = (sources[a.source] || 0) + 1; });
    return clone({
      ...summary(r), steps: STEPS, profile: r.profile,
      pending: r.proposals.filter((p) => p.status === "pending"), history: r.proposals.filter((p) => p.status !== "pending").slice(-30),
      offer: offerOf(r), grid: r.grid, groups, counts: counts(r), busy: [],
      apply_link: r.published_at ? `${BASE}/offres/${r.token}` : null,
      interview_location: r.location, interview_minutes: r.interview_minutes, free_slots: freeSlots(r).length, sources,
    }) as RecruitmentDetail;
  };
  const answersView = (r: Rec, raw: Record<string, any> | null) => {
    if (!raw) return [];
    return questionsFor(r.profile).filter((q) => q.id in raw).map((q) => {
      const c = r.profile.criteria.find((x) => x.id === q.id)!;
      const [, txt] = evaluateDeclared(c, raw[q.id]);
      return { question: q.label, answer: q.input === "text" ? String(raw[q.id]) : txt };
    });
  };
  const item = (r: Rec, a: DApp): ApplicationDetail => {
    const { cand_token: _t, raw, fxi: _f, order: _o, sent, ...rest } = a;
    void _t; void _f; void _o;
    const iv = r.ivs.filter((x) => x.application_id === a.id).slice(-1)[0];
    return clone({ ...rest, answers: answersView(r, raw), messages: sent,
      interview: iv ? { id: iv.id, status: iv.status, start: iv.start, end: iv.end, location: iv.location } : null,
      debrief_status: a.debrief?.status || null });
  };
  const ivView = (r: Rec, iv: DIv): InterviewItem => {
    const { token: _t, ...rest } = iv;
    void _t;
    return clone({ ...rest, recruitment_title: r.title, debrief_status: r.apps.find((a) => a.id === iv.application_id)?.debrief?.status || null,
      self_booking: r.slots.length > 0 });
  };

  const publish = (r: Rec) => {
    if (r.state !== "offer_review") throw err400("L'offre est déjà publiée.");
    const o = offerOf(r)!;
    o.status = "published";
    o.channels = [{ id: "google", label: "Google pour l'emploi", status: "online", at: now() }];
    r.published_at = now();
    const p = pending(r, "offer");
    if (p) close(r, p, "accepted");
    go(r, "collecting", "user");
    log(r, "offer.published", { channels: ["google"] }, "user");
    // Démo : les candidatures fictives « arrivent » (réponses aux questions + CV).
    for (const f of fx.applications) {
      receive(r, { name: f.name, email: f.email, source: f.source, cv_filename: f.cv_filename, cv_text: f.cv_text, pool_consent: f.pool_consent,
        raw: sameAsExample(r) ? f.raw_answers : personaAnswers(f.name, f.raw_answers, r.profile.criteria), fxi: f });
    }
  };

  const accept = async (id: string, pid: string, body: Record<string, any> = {}) => {
    await wait();
    const r = get(id);
    const p = r.proposals.find((x) => x.id === pid);
    if (!p) throw new ApiError(404, "Étape introuvable.");
    switch (p.kind) {
      case "offer": publish(r); break;
      case "start_screening": close(r, p, "accepted"); await runScreening(r); break;
      case "shortlist": {
        const proposed: string[] = p.payload.application_ids;
        const sel: string[] = (body.application_ids || proposed).filter((x: string) => r.apps.some((a) => a.id === x && a.status !== "withdrawn"));
        if (!sel.length) throw err400("Choisissez au moins une personne à rencontrer.");
        const added = sel.filter((x) => !proposed.includes(x));
        const removed = proposed.filter((x) => !sel.includes(x));
        close(r, p, added.length || removed.length ? "modified" : "accepted", { added: added.length, removed: removed.length, selected: sel.length });
        for (const a of r.apps) {
          if (sel.includes(a.id)) {
            a.shortlisted = true;
            if (["received", "screened", "not_shortlisted"].includes(a.status)) a.status = "shortlisted";
            a.rescued = a.group !== "meets";
            if (added.includes(a.id)) log(r, "shortlist.candidate_added", { group_suggested: a.group }, "user", a.name);
          } else if (["received", "screened"].includes(a.status)) a.status = "not_shortlisted";
        }
        r.shortlisted_at = now();
        log(r, "shortlist.validated", { selected: sel.length }, "user");
        go(r, "scheduling", "user");
        if (has("scheduling")) {
          propose(r, "availability", 3, "Vos disponibilités pour les entretiens", "Indiquez vos créneaux une fois : les candidats choisissent le leur, avec confirmation et rappel.",
            { suggested: suggestRanges(), location: r.location, minutes: r.interview_minutes });
        } else {
          const [subject, b] = fx.texts.invitation_manual;
          propose(r, "invite_manual", 3, "Invitez les candidats retenus", `Un e-mail est prêt pour ${sel.length > 1 ? `les ${sel.length} personnes` : "la personne"} à rencontrer. Vous fixerez ensuite les dates ici.`,
            { application_ids: sel, subject, body: b });
        }
        break;
      }
      case "invite_manual": {
        const subject = String(body.subject ?? p.payload.subject).trim();
        const text = String(body.body ?? p.payload.body).trim();
        const targets = r.apps.filter((x) => x.shortlisted && x.status === "shortlisted");
        if (!targets.length) throw err400("Personne à inviter : ajoutez au moins une candidature à la sélection.");
        close(r, p, subject === p.payload.subject && text === p.payload.body ? "accepted" : "modified");
        for (const a of targets) { mail(r, a, "invitation", render(r, subject, a), render(r, text, a)); newIv(r, a); }
        log(r, "message.bulk_sent", { kind: "invitation", count: targets.length }, "user");
        go(r, "interviewing", "user");
        break;
      }
      case "availability": {
        const ranges: { start: string; end: string }[] = body.ranges || p.payload.suggested;
        if (!ranges.length) throw err400("Indiquez au moins une plage de disponibilité.");
        if (body.location) r.location = body.location;
        if (body.minutes) r.interview_minutes = body.minutes;
        close(r, p, body.ranges ? "modified" : "accepted");
        if (!addSlots(r, ranges)) throw err400("Aucun créneau futur dans ces plages.");
        inviteWithBooking(r);
        go(r, "interviewing", "user");
        // Démo : les candidats réservent tout seuls, sauf le dernier (pour essayer la page de réservation).
        r.ivs.slice(0, -1).forEach((iv) => { const s = freeSlots(r)[0]; if (s) book(r, iv, s.id); });
        break;
      }
      case "decision":
        if (!("application_id" in body)) throw err400("Choisissez la personne à recruter, ou indiquez que vous ne recrutez pas.");
        decide(r, body.application_id ?? null);
        break;
      case "closing_messages": {
        const tpl = { ...p.payload.templates };
        let modified = false;
        for (const [k, v] of Object.entries(body.templates || {}) as [string, any][]) {
          if (tpl[k] && (v.subject !== tpl[k].subject || v.body !== tpl[k].body)) { tpl[k] = { ...tpl[k], subject: v.subject, body: v.body }; modified = true; }
        }
        close(r, p, modified ? "modified" : "accepted");
        for (const m of p.payload.messages) {
          const a = r.apps.find((x) => x.id === m.application_id)!;
          if (a.anonymized || a.status === "withdrawn") continue;
          const tp = tpl[m.kind];
          mail(r, a, `closing:${m.kind}`, tp.subject, render(r, tp.body, a));
          a.status = m.kind === "hired" ? "hired" : "rejected";
          if (m.kind !== "hired") r.ivs.filter((iv) => iv.application_id === a.id && ["invited", "booked"].includes(iv.status)).forEach((iv) => { release(r, iv); iv.status = "cancelled"; });
        }
        r.outcome = p.payload.hired ? "hired" : "abandoned";
        r.closed_at = now();
        withdrawOffer(r);
        go(r, "closed", "user");
        break;
      }
      case "followup":
        close(r, p, "accepted", { still_there: !!body.still_there });
        log(r, "followup.answered", { months: p.payload.months, still_there: !!body.still_there }, "user");
        break;
      default:
        close(r, p, "accepted");
    }
    return detail(r);
  };

  const findIv = (token: string) => {
    for (const r of recs) { const iv = r.ivs.find((x) => x.token === token || x.id === token); if (iv) return { r, iv }; }
    throw new ApiError(404, "Lien de rendez-vous introuvable.");
  };
  const findApp = (aid: string) => {
    for (const r of recs) { const a = r.apps.find((x) => x.id === aid || x.cand_token === aid); if (a) return { r, a }; }
    throw new ApiError(404, "Candidature introuvable.");
  };
  const exportCache = new Map<string, string>();
  /** Même contenu que l'export du serveur : libellés lisibles, formules neutralisées. */
  const csvFor = (id: string): string | null => {
    if (!has("export")) return null;
    const r = recs.find((x) => x.id === id);
    if (!r) return null;
    const q = (s: unknown) => {
      const t = String(s ?? "");
      return `"${(/^[=+\-@]/.test(t) ? "'" + t : t).replaceAll('"', '""')}"`;
    };
    const crit: Record<string, string> = { met: "Remplit", partial: "En partie", not_met: "Non", unknown: "Non établi" };
    const groups: Record<string, string> = { meets: "Remplit les critères indispensables", partial: "En partie",
      does_not: "Ne les remplit pas", unreadable: "CV à lire" };
    const day = (iso: string) => new Date(iso).toLocaleDateString("fr-FR");
    const rows = [["Nom", "E-mail", "Provenance", "Reçue le", "Synthèse", "Étape", ...r.profile.criteria.map((c) => c.label)].map(q).join(";"),
      ...[...r.apps].filter((a) => !a.anonymized).sort((a, b) => a.created_at.localeCompare(b.created_at)).map((a) =>
        [a.name, a.email, SOURCE_LABELS[a.source] || a.source, day(a.created_at), groups[a.group || ""] || "",
          STAGE[a.status]?.label || a.status,
          ...r.profile.criteria.map((c) => crit[a.evaluations.find((e) => e.criterion_id === c.id)?.status || ""] || "")].map(q).join(";"))];
    return "﻿" + rows.join("\n");
  };

  const api: Api = {
    demo: true,
    me: async () => me(),
    signup: async () => ({ demo_link: null }),
    requestLink: async () => ({ demo_link: null }),
    exchange: async () => ({ redirect: "/" }),
    logout: async () => {},

    listRecruitments: async () => recs.map(summary),
    previewForm: async (form) => {
      const { profile, issues } = buildProfile(form);
      const offer = profile.title.length >= 3 ? offerFromProfile(profile, company.name) : null;
      return { offer, questions: questionsFor(profile), issues, criteria: profile.criteria };
    },
    createRecruitment: async (form, doPublish) => {
      await wait(400);
      if (plan === "free" && active() >= 1) {
        throw new ApiError(402, "L'offre Gratuit permet 1 recrutement actif à la fois. Clôturez le recrutement en cours ou passez à Premium pour en ouvrir d'autres.", true);
      }
      const { profile, issues } = buildProfile(form);
      if (issues.length) throw err400(issues[0].match ? `Retirez « ${issues[0].match} » : ${issues[0].message}` : issues[0].message, issues);
      const r: Rec = { id: uid("r"), title: profile.title, state: "offer_review", created_at: now(), published_at: null, closed_at: null, shortlisted_at: null,
        profile, proposals: [], offers: [], grid: null, apps: [], slots: [], ivs: [], outcome: null, seconds: 0, location: company.address,
        interview_minutes: 45, audit: [], token: uid("offre") };
      recs.unshift(r);
      log(r, "recruitment.created", { criteria: profile.criteria.length, rome_code: profile.rome_code }, "user");
      const sameText = sameAsExample(r) && profile.title === fx.profile.title;
      const o = sameText ? fx.offer : offerFromProfile(profile, company.name);
      saveOffer(r, o.short, o.long, "system");
      const questions = sameText ? clone(fx.grid.questions) : gridGenerate(profile);
      r.grid = { id: uid("g"), version: 1, questions, status: "validated" };
      log(r, "grid.generated", { questions: questions.length });
      if (doPublish) publish(r);
      else propose(r, "offer", 1, "Offre prête à publier", "Relisez-la si vous le souhaitez, puis publiez-la : elle part partout en un clic.", { offer_id: offerOf(r)!.id });
      return detail(r);
    },
    getRecruitment: async (id) => detail(get(id)),
    publish: async (id) => { await wait(300); const r = get(id); publish(r); return detail(r); },
    editOffer: async (id, short, long) => {
      await wait(200);
      const r = get(id);
      if (!["offer_review", "collecting"].includes(r.state)) throw err400("L'offre n'est plus modifiable une fois la sélection commencée.");
      saveOffer(r, short.trim(), long.trim(), "user");
      return detail(r);
    },
    accept,
    refuse: async (id, pid) => {
      const r = get(id);
      const p = r.proposals.find((x) => x.id === pid)!;
      if (p.kind !== "start_screening") throw err400("Cette étape ne se refuse pas.");
      close(r, p, "refused");
      return detail(r);
    },
    startScreening: async (id) => {
      const r = get(id);
      if (!["collecting", "shortlist_review"].includes(r.state)) throw err400("La sélection se prépare une fois l'offre publiée.");
      const p = pending(r, "start_screening");
      if (p) close(r, p, "accepted");
      await runScreening(r);
      return detail(r);
    },
    abandon: async (id) => {
      const r = get(id);
      r.proposals.filter((p) => p.status === "pending").forEach((p) => (p.status = "superseded"));
      if (r.published_at && r.apps.some((a) => !a.anonymized)) {
        if (r.state !== "decision") { log(r, "recruitment.transition", { from: r.state, to: "decision", reason: "abandon" }, "user"); r.state = "decision"; }
        decide(r, null);
      } else { r.outcome = "abandoned"; r.closed_at = now(); go(r, "abandoned", "user"); withdrawOffer(r); }
      return detail(r);
    },
    bulk: async (id, b) => {
      await wait(300);
      const r = get(id);
      const targets = r.apps.filter((a) => b.application_ids.includes(a.id) && a.status !== "withdrawn" && !a.anonymized);
      if (!targets.length) throw err400("Sélectionnez au moins une candidature.");
      if (b.action === "email") {
        if ((b.subject || "").trim().length < 3 || (b.body || "").trim().length < 10) throw err400("Écrivez un objet et un message.");
        targets.forEach((a) => mail(r, a, "bulk", render(r, b.subject!, a), render(r, b.body!, a)));
        log(r, "message.bulk_sent", { count: targets.length, kind: "bulk" }, "user");
        return { done: targets.length };
      }
      if (b.action === "reject") {
        const todo = targets.filter((a) => !["hired", "rejected", "withdrawn"].includes(a.status));
        if (!todo.length) throw err400("Ces candidatures ont déjà reçu une réponse.");
        const [ds, db] = fx.texts.rejection;
        for (const a of todo) {
          mail(r, a, "closing:rejected", render(r, b.subject || ds, a), render(r, b.body || db, a));
          r.ivs.filter((iv) => iv.application_id === a.id && ["invited", "booked"].includes(iv.status)).forEach((iv) => { release(r, iv); iv.status = "cancelled"; });
          a.status = "rejected";
          a.shortlisted = false;
          log(r, "application.rejected", { group_suggested: a.group }, "user", a.name);
        }
        maybeDecision(r);
        return { done: todo.length };
      }
      if (["offer_review", "collecting", "shortlist_review"].includes(r.state)) throw err400("Validez d'abord la sélection proposée ; vous pourrez ensuite ajouter des candidats.");
      if (["closed", "abandoned", "decision"].includes(r.state)) throw err400("Ce recrutement n'accepte plus de nouveaux entretiens.");
      const added = targets.filter((x) => ["received", "screened", "not_shortlisted"].includes(x.status));
      for (const a of added) {
        a.shortlisted = true; a.rescued = a.group !== "meets"; a.status = "shortlisted";
        log(r, "shortlist.candidate_added", { group_suggested: a.group }, "user", a.name);
      }
      let invited = 0, toSchedule = 0;
      if (added.length && r.state === "interviewing") {
        if (has("scheduling") && freeSlots(r).length) invited = inviteWithBooking(r);
        else {
          for (const a of added) { newIv(r, a); toSchedule++; }
          if (b.subject && b.body) added.forEach((a) => mail(r, a, "invitation", render(r, b.subject!, a), render(r, b.body!, a)));
        }
      }
      return { done: added.length, invited, to_schedule: toSchedule };
    },
    mailTemplates: async () => clone(fx.mail_templates),
    exportCsv: (id) => csvFor(id),
    exportUrl: (id) => {
      const csv = csvFor(id);
      if (csv === null) return null;
      const old = exportCache.get(id);
      if (old) URL.revokeObjectURL(old);
      const url = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
      exportCache.set(id, url);
      return url;
    },

    refJobs: async (q) => ({
      results: search(q, romeIdx().app, 24).slice(0, 12).map((i) => {
        const [label, code] = rome.appellations[i];
        return { label, rome_code: code, rome_label: rome.fiches[code] || "", domain: rome.domains[code.slice(0, 3)] || "" };
      }),
      attribution: rome.attribution,
    }),
    refSkills: async (q) => ({ results: search(q, romeIdx().comp, 12).map((i) => rome.competences[i]), attribution: rome.attribution }),
    refKnowledge: async (q, categorie) => {
      const allowed = categorie ? SAVOIRS[categorie] : null;
      const out = search(q, romeIdx().sav, allowed ? 400 : 12).map((i) => rome.savoirs[i]).filter((s: string[]) => !allowed || allowed.includes(s[2]))
        .slice(0, 12).map((s: string[]) => ({ label: s[0], category: s[1], subcategory: s[2] }));
      return { results: out, attribution: rome.attribution };
    },
    refAddresses: async (q) => {
      const n = norm(q);
      return { results: COMMUNES.filter(([city, pc]) => norm(city).includes(n) || pc.startsWith(n) || n.includes(norm(city)))
        .slice(0, 6).map(([city, postcode, context]) => ({ label: city, city, postcode, context, type: "municipality" })) };
    },
    refLists: async () => clone(fx.lists),
    companySearch: async (q) => {
      const n = norm(q);
      if (["negoce", "durand"].some((w) => n.includes(w))) {
        return { results: [{ siren: company.siren, name: "NÉGOCE DURAND", display_name: "Négoce Durand", address: company.address, naf_code: company.naf_code, headcount_range: company.headcount_range }] };
      }
      return { results: [], error: "Démo : l'annuaire des entreprises n'est pas interrogé (essayez « Durand »)." };
    },

    billing: async (): Promise<Billing> => {
      const end = new Date();
      if (interval === "year") end.setFullYear(end.getFullYear() + 1); else end.setMonth(end.getMonth() + 1);
      return { plan, plan_name: fx.plans[plan].name, status: plan === "premium" ? "active" : null, interval: plan === "premium" ? interval : null,
        period_end: plan === "premium" ? end.toISOString() : null, features: [...fx.plans[plan].features],
        usage: { active_recruitments: active(), limit: fx.plans[plan].limit }, billing_mode: "demo", prices: clone(fx.prices),
        trial_days: 14, has_customer: false, catalog: clone(fx.features) };
    },
    checkout: async (iv) => { await wait(300); plan = "premium"; interval = iv; recs.forEach((r) => log(r, "billing.plan_changed", { plan }, "user")); return { url: "/abonnement?statut=ok" }; },
    portal: async () => { throw new ApiError(400, "Pas de portail de paiement dans la démo."); },
    cancelDemo: async () => { plan = "free"; },

    listApplications: async (id) => { const r = get(id); return r.apps.filter((a) => a.status !== "withdrawn").map((a) => item(r, a)); },
    getApplication: async (aid) => { const { r, a } = findApp(aid); return item(r, a); },
    saveGrid: async (id, questions) => {
      const r = get(id);
      if (r.apps.some((a) => a.debrief)) throw new ApiError(409, "Des entretiens sont déjà notés avec ces questions : gardez les mêmes pour tous.");
      r.grid!.questions = questions.filter((q: GridQuestion) => q.text.trim()).map((q: GridQuestion, i: number) => ({ ...q, id: `q${i + 1}` }));
      log(r, "grid.validated", { edited: true }, "user");
      return detail(r);
    },
    gridPrintUrl: () => null,
    agenda: async (): Promise<Agenda> => {
      const all = recs.filter((r) => !["closed", "abandoned"].includes(r.state)).flatMap((r) => r.ivs.map((iv) => ({ r, iv })));
      const view = (x: { r: Rec; iv: DIv }) => ivView(x.r, x.iv);
      return {
        upcoming: all.filter(({ iv }) => iv.status === "booked" && iv.start && Date.parse(iv.start) >= t() - 2 * 3600_000).sort((a, b) => a.iv.start!.localeCompare(b.iv.start!)).map(view),
        to_schedule: all.filter(({ iv }) => iv.status === "invited").map(view),
        to_note: all.filter(({ r, iv }) => (iv.status === "attended" || (iv.status === "booked" && iv.start && Date.parse(iv.start) < t() - 2 * 3600_000)) && !noted(r, iv)).map(view),
      };
    },
    listInterviews: async (id) => {
      const r = get(id);
      return { interviews: r.ivs.filter((iv) => iv.status !== "cancelled").sort((a, b) => (a.start || "9").localeCompare(b.start || "9")).map((iv) => ivView(r, iv)),
        free_slots: freeSlots(r).map(({ id: sid, start, end }) => ({ id: sid, start, end })), online: r.slots.length > 0 };
    },
    addSlots: async (id, ranges) => {
      requireFeature("scheduling");
      const r = get(id);
      const created = addSlots(r, ranges);
      if (!created) throw err400("Aucun créneau à venir dans ces plages.");
      return { created };
    },
    schedule: async (iid, start, location) => {
      await wait(200);
      const { r, iv } = findIv(iid);
      if (["closed", "abandoned", "decision"].includes(r.state)) throw err400("Ce recrutement n'accepte plus d'entretiens.");
      if (!["invited", "booked"].includes(iv.status)) throw err400("Cet entretien a déjà eu lieu ou a été annulé.");
      if (Date.parse(start) < t() - 3600_000) throw err400("Choisissez une date à venir.");
      release(r, iv);
      Object.assign(iv, { start, end: new Date(Date.parse(start) + r.interview_minutes * 60000).toISOString(), location: (location || "").trim() || r.location,
        status: "booked", booked_at: now() });
      confirm(r, iv, "user");
      return ivView(r, iv);
    },
    attendance: async (iid, attended) => {
      const { r, iv } = findIv(iid);
      iv.status = attended ? "attended" : "no_show";
      const a = r.apps.find((x) => x.id === iv.application_id)!;
      if (attended) a.status = "interviewed";
      log(r, "interview.attendance", { attended }, "user", a.name);
      maybeDecision(r);
      return ivView(r, iv);
    },
    cancelInterview: async (iid) => {
      const { r, iv } = findIv(iid);
      if (!["invited", "booked"].includes(iv.status)) throw err400("Cet entretien a déjà eu lieu ou a été annulé.");
      const when = iv.start;
      release(r, iv);
      Object.assign(iv, { status: "invited", start: null, end: null });
      const a = r.apps.find((x) => x.id === iv.application_id)!;
      a.status = "invited";
      log(r, "interview.cancelled", {}, "user", a.name);
      if (when) mail(r, a, "unscheduled", `Entretien à déplacer — ${r.profile.title}`, `Bonjour ${first(a)},\n\nL'entretien prévu ${frDateTime(when)} pour le poste « ${r.profile.title} » doit être déplacé. Toutes nos excuses.\n\nNous revenons vers vous très vite pour convenir d'une nouvelle date.\n\n${company.name}`);
      return ivView(r, iv);
    },
    saveNotes: async (aid, notes, overall) => {
      await wait(200);
      const { r, a } = findApp(aid);
      if (!a.shortlisted) throw err400("Cette personne n'est pas dans la liste des entretiens.");
      const qs = r.grid?.questions || [];
      const cleanNotes: Record<string, DebriefNote> = Object.fromEntries(qs.map((q) => {
        const n = notes?.[q.id] || {};
        return [q.id, { score: [1, 2, 3].includes(n.score) ? n.score : null, notes: String(n.notes || "").slice(0, 1000), quote: n.quote ?? null }];
      }));
      a.debrief = { notes: cleanNotes, overall: (overall || "").slice(0, 600), status: "validated" };
      if (["booked", "invited"].includes(a.status)) a.status = "interviewed";
      r.ivs.filter((iv) => iv.application_id === a.id && ["booked", "invited"].includes(iv.status)).forEach((iv) => (iv.status = "attended"));
      log(r, "debrief.validated", { scored: Object.values(cleanNotes).filter((n) => n.score).length }, "user", a.name);
      maybeDecision(r);
      return item(r, a);
    },
    comparison: async (id) => comparison(get(id)),
    openDecision: async (id) => {
      const r = get(id);
      if (r.state === "interviewing") go(r, "decision", "user");
      else if (r.state !== "decision") throw err400("La décision se prend après les entretiens.");
      return detail(r);
    },
    decide: async (id, appId) => { await wait(); const r = get(id); decide(r, appId); return detail(r); },

    audit: async (id) => clone(get(id).audit),
    metrics: async () => {
      const median = (xs: number[]) => { if (!xs.length) return null; const s = [...xs].sort((a, b) => a - b); const k = Math.floor(s.length / 2); return s.length % 2 ? s[k] : (s[k - 1] + s[k]) / 2; };
      const per = recs.map((r) => {
        const planned = r.ivs.filter((i) => ["booked", "attended", "no_show"].includes(i.status));
        const attended = r.ivs.filter((i) => i.status === "attended");
        const apps = r.apps.filter((a) => a.status !== "withdrawn");
        return { id: r.id, title: r.title, state: r.state, published: !!r.published_at, applications: apps.length,
          applications_by_source: apps.reduce((m: Record<string, number>, a) => ({ ...m, [a.source]: (m[a.source] || 0) + 1 }), {}),
          rescued: apps.filter((a) => a.shortlisted && a.rescued).length, interviews_planned: planned.length, interviews_attended: attended.length,
          attendance_rate: planned.length ? attended.length / planned.length : null, hired: r.outcome === "hired",
          days_to_close: r.closed_at && r.published_at ? Math.round((Date.parse(r.closed_at) - Date.parse(r.published_at)) / 8_640_000) / 10 : null };
      });
      const closed = per.filter((m) => ["closed", "abandoned"].includes(m.state));
      const sources: Record<string, number> = {};
      per.forEach((m) => Object.entries(m.applications_by_source).forEach(([k, v]) => (sources[k] = (sources[k] || 0) + v)));
      const planned = per.reduce((s, m) => s + m.interviews_planned, 0);
      return {
        summary: {
          recruitments: per.length, active: per.length - closed.length, hired: closed.filter((m) => m.hired).length,
          applications_per_offer_median: median(per.filter((m) => m.published).map((m) => m.applications)),
          days_to_close_median: median(closed.filter((m) => m.hired && m.days_to_close !== null).map((m) => m.days_to_close as number)),
          attendance_rate: planned ? per.reduce((s, m) => s + m.interviews_attended, 0) / planned : null,
          hire_rate: closed.length ? closed.filter((m) => m.hired).length / closed.length : null, sources,
        },
        recruitments: per,
      };
    },
    saveSettings: async (b) => {
      Object.assign(company, { name: b.company_name ?? company.name, siren: b.siren ?? company.siren, naf_code: b.naf_code ?? company.naf_code,
        headcount_range: b.headcount_range ?? company.headcount_range, address: b.address ?? company.address });
      Object.assign(user, { name: b.name ?? user.name, phone: b.phone ?? user.phone, theme: b.theme === "dark" || b.theme === "light" ? b.theme : user.theme });
    },
    active: async (rid, seconds) => { const r = recs.find((x) => x.id === rid); if (r) r.seconds += seconds; },

    publicOffer: async (token) => {
      const r = recs.find((x) => x.token === token && x.published_at);
      if (!r) throw new ApiError(404, "Offre introuvable.");
      return { title: r.title, company: company.name, company_slug: company.slug, long: offerOf(r)?.long || "", open: isOpen(r),
        profile: { location: r.profile.location, contract: r.profile.contract, hours: r.profile.hours, salary: r.profile.salary, remote: r.profile.remote, start_date: r.profile.start_date },
        questions: questionsFor(r.profile) };
    },
    apply: async (token, form) => {
      await wait(400);
      const r = recs.find((x) => x.token === token);
      if (!r || !r.published_at) throw new ApiError(404, "Offre introuvable.");
      if (!isOpen(r)) throw new ApiError(410, "Cette offre n'est plus ouverte aux candidatures.");
      if (String(form.get("website") || "")) return;
      const email = String(form.get("email") || "").trim().toLowerCase();
      if (r.apps.some((a) => a.email === email && a.status !== "withdrawn")) throw new ApiError(409, "Vous avez déjà postulé à cette offre avec cette adresse e-mail.");
      let raw: Record<string, any> = {};
      try { raw = JSON.parse(String(form.get("answers") || "{}")); } catch { raw = {}; }
      const answers = cleanAnswers(r.profile, raw);
      const cv = form.get("cv") as File | null;
      const message = String(form.get("message") || "");
      if (!cv?.size && message.trim().length <= 30) throw err400("Joignez un CV, ou présentez votre parcours dans le message.");
      const cvText = cv && cv.size && (cv.type.startsWith("text") || cv.name.endsWith(".txt")) ? await cv.text() : null;
      receive(r, { name: `${form.get("first_name")} ${form.get("last_name")}`.trim(), email, source: String(form.get("src") || "lien"),
        message: message || null, cv_filename: cv?.size ? cv.name : null, cv_text: cvText, pool_consent: form.get("pool_consent") === "true", raw: answers });
    },
    privacy: async () => ({ company: company.name, text: fx.texts.privacy }),
    booking: async (token) => {
      const { r, iv } = findIv(token);
      const a = r.apps.find((x) => x.id === iv.application_id)!;
      const online = has("scheduling") && r.slots.length > 0;
      const closed = ["closed", "abandoned"].includes(r.state) || ["cancelled", "attended", "no_show"].includes(iv.status);
      return { title: r.title, company: company.name, status: iv.status, first_name: first(a), minutes: r.interview_minutes, location: iv.location || r.location,
        start: iv.start, closed, mode: online ? "online" : "manual", slots: closed || !online ? [] : freeSlots(r).map(({ id, start, end }) => ({ id, start, end })) };
    },
    book: async (token, slotId) => { const { r, iv } = findIv(token); book(r, iv, slotId); return { start: iv.start }; },
    cancelBooking: async (token) => {
      const { r, iv } = findIv(token);
      if (!["invited", "booked"].includes(iv.status)) throw err400("Cet entretien a déjà eu lieu ou a été annulé.");
      release(r, iv);
      Object.assign(iv, { status: "invited", start: null, end: null });
      const a = r.apps.find((x) => x.id === iv.application_id)!;
      a.status = "invited";
      log(r, "interview.cancelled", {}, "candidate", a.name);
    },
    candidate: async (token) => {
      const { r, a } = findApp(token);
      if (a.anonymized) throw new ApiError(404, "Lien invalide, ou données déjà supprimées.");
      const [fn, ...rest] = a.name.split(" ");
      const due = new Date(); due.setMonth(due.getMonth() + 24);
      return { company: company.name, company_slug: company.slug, first_name: fn, last_name: rest.join(" "), email: a.email, phone: null, pool_consent: a.pool_consent,
        deletion_due: due.toISOString(), applications: [{ title: r.title, status: a.status, sent_at: a.created_at, cv_filename: a.cv_filename,
          evaluations: a.evaluations.map((e) => ({ label: e.label, status: e.status, justification: e.justification })) }] };
    },
    withdraw: async (token) => {
      const { r, a } = findApp(token);
      a.status = "withdrawn"; a.anonymized = true; a.name = "Candidat supprimé"; a.email = null; a.cv_text = null; a.raw = null; a.sent = [];
      log(r, "application.withdrawn", {}, "candidate");
    },
    demoFastForward: async (id) => {
      // Démo : les entretiens prévus passent à la veille (même heure), comme s'ils avaient eu lieu.
      const r = get(id);
      for (const iv of r.ivs.filter((i) => i.status === "booked" && i.start)) {
        const d = new Date(iv.start!);
        const y = new Date(t() - 86_400_000);
        d.setFullYear(y.getFullYear(), y.getMonth(), y.getDate());
        iv.start = d.toISOString();
        iv.end = new Date(d.getTime() + r.interview_minutes * 60000).toISOString();
      }
      return detail(r);
    },
  };
  return api;
}
