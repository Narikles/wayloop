/**
 * Démo hors ligne : portage de l'assistant de rédaction par règles (backend/app/modules/assistant.py).
 *
 * Les exemples proposés à l'écran rejouent exactement la sortie du back-end (exportée dans
 * demo-fixtures.json) ; une autre phrase est lue ici avec les mêmes règles et les mêmes
 * données (familles de métiers, logiciels, langues, contrats). La démo n'appelle aucune IA.
 */
import FX from "./demo-fixtures.json";
import type { JobForm } from "./types";

const A = (FX as any).assistant;
const norm = (s: string) => s.toLowerCase().normalize("NFD").replace(/\p{M}/gu, "").replace(/’/g, "'").replace(/\s+/g, " ").trim();
const esc = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
const re = (p: string, flags = "") => new RegExp(p, flags);

type Crit = { kind: string; required: boolean; params: Record<string, any> };
type Fam = { pattern: string; domain: string; missions: string[]; criteria: [string, Record<string, any>][]; question: string };

const SOFTWARE: Record<string, string> = A.software;
const LANG_WORDS: Record<string, string> = A.lang_words;
const LANG_LEVELS: Record<string, string> = A.lang_levels;
const SENIORITY: Record<string, number> = A.seniority;
const ABBREV: Record<string, string> = A.abbreviations;
const FAMILIES: Fam[] = A.families;
const CEFR = ["A1", "A2", "B1", "B2", "C1", "C2"];
const PERMIS = ["AM", "A1", "A2", "A", "B", "BE", "C1", "C1E", "C", "CE", "D1", "D1E", "D", "DE"];
const NOT_PLACES = /\d|\b(?:cdi|cdd|interim|alternance|apprenti|stage|saisonnier|freelance|independant|permis|teletravail|remote|hybride|temps|partiel|plein|week|nuit|soir|debutant|junior|senior|confirme|experimente|bac|caces|habilitation|haccp|sst|niveau|salaire|brut|net|variable|prime|asap|urgent|poste|equipe|anglais|espagnol|allemand|italien|experience|ans?|mois|h\/f|f\/h)\b/;
const PLACE = "[A-ZÉÈÂÎÔ][a-zà-ÿ'’]+(?:[ -](?:sur|en|lès|les|de|du|la|le|d'|l')?[ -]?[A-ZÉÈÂÎÔ][a-zà-ÿ'’]+){0,3}";

function salary(text: string): { salary_min: number; salary_max: number; salary_period: string } | null {
  const t = text.replace(/ | /g, " ");
  const num = "(\\d{1,3}(?:[ .]\\d{3})+|\\d+(?:[.,]\\d{1,2})?)";
  const rng = re(num + "\\s*(k)?\\s*(?:€|euros?|eur)?\\s*(?:-|–|à|a|/)\\s*" + num + "\\s*(k)?\\s*(?:€|euros?|eur|k€)", "i").exec(t);
  const single = rng ? null : re(num + "\\s*(k)?\\s*(?:€|euros?\\b|eur\\b)|" + num + "\\s*(k)(?=\\s|$|[,;+])", "i").exec(t);
  if (!rng && !single) return null;
  const val = (s: string) => (/^\d{1,3}(?:[ .]\d{3})+$/.test(s) ? Number(s.replace(/[ .]/g, "")) : Number(s.replace(",", ".")));
  let lo: number, hi: number, k: boolean, end: number;
  if (rng) { k = !!(rng[2] || rng[4]); lo = val(rng[1]); hi = val(rng[3]); end = rng.index + rng[0].length; }
  else { k = !!(single![2] || single![4]); lo = hi = val(single![1] || single![3]); end = single!.index + single![0].length; }
  if (k) { lo *= 1000; hi *= 1000; }
  const after = norm(t.slice(end, end + 25));
  let period: string;
  if (/^\s*(?:brut\s*)?(?:\/|par|de l')?\s*(?:h\b|heure|horaire)/.test(after)) period = "heure";
  else if (/^\s*(?:brut\s*)?(?:\/|par)?\s*(?:an\b|annuel|annee)/.test(after) || k) period = "an";
  else if (/^\s*(?:brut\s*)?(?:\/|par)?\s*mois|^\s*mensuel/.test(after)) period = "mois";
  else period = hi < 100 ? "heure" : hi >= 10000 ? "an" : "mois";
  if (lo > hi) [lo, hi] = [hi, lo];
  return { salary_min: Math.round(lo * 100) / 100, salary_max: Math.round(hi * 100) / 100, salary_period: period };
}

function years(t: string): number | null {
  for (const m of t.matchAll(/(\d{1,2})\s*(?:ans?|annees?)\b/g)) {
    const before = t.slice(Math.max(0, (m.index ?? 0) - 14), m.index);
    if (/\bmoins de\b|\bplus de\b|\bage\b|\bagee?s? de\b|\bentre\b/.test(before)) continue;
    return Math.max(0, Math.min(30, Number(m[1])));
  }
  return null;
}

function family(text: string): Fam | null {
  const t = norm(text);
  return FAMILIES.find((f) => re(norm(f.pattern)).test(t)) || null;
}

function cleanTitle(seg: string): string {
  const words: string[] = [];
  for (let w of seg.trim().split(/\s+/)) {
    const nw = norm(w).replace(/^[.,;:]+|[.,;:]+$/g, "");
    if (!nw || nw in SENIORITY || ["h/f", "(h/f)", "f/h", "(f/h)", "h-f"].includes(nw)) continue;
    if (nw.includes("/") && nw.split("/").every((x) => x in SOFTWARE)) w = nw.split("/").map((x) => SOFTWARE[x]).join("/");
    else if (nw in SOFTWARE) w = SOFTWARE[nw];
    words.push(ABBREV[nw] || w);
  }
  while (words.length && ["en", "a", "de", "du", "pour", "avec", "et", "sur", "-"].includes(norm(words[words.length - 1]))) words.pop();
  const title = words.join(" ").replace(/^[\s\-–,]+|[\s\-–,]+$/g, "");
  return title ? title[0].toUpperCase() + title.slice(1) : "";
}

function isPlace(s: string): boolean {
  const n = norm(s);
  if (!n || n in SOFTWARE || n.split(" ")[0] in LANG_WORDS || NOT_PLACES.test(n.replace(/\(?\d{5}\)?/g, ""))) return false;
  return re(`^${PLACE}(?:\\s*\\(?\\d{2,5}\\)?)?$`).test(s.trim());
}

function location(text: string, segments: string[], used: Set<number>, title: string): string | null {
  for (let i = 0; i < segments.length; i++) {
    if (used.has(i)) continue;
    const s = segments[i].trim().replace(/^(?:à|a|sur|bas[ée]e? (?:à|a)|secteur(?: de)?|r[ée]gion(?: de)?)\s+/i, "");
    if ((/\b\d{5}\b/.test(s) && !/€|euros?|\bk\b/i.test(s)) || isPlace(s)) { used.add(i); return s; }
  }
  const m = re(`\\b(?:à|sur|bas[ée]e? à|secteur(?: de)?)\\s+(${PLACE})`).exec(text);
  if (m && isPlace(m[1])) return m[1];
  const tw = new Set((title.match(/[\wÀ-ÿ'’]+/g) || []).map(norm));
  for (const mm of text.matchAll(re(PLACE, "g"))) {
    if ((mm.index ?? 0) === 0 || tw.has(norm(mm[0].split(" ")[0]))) continue;
    if (isPlace(mm[0])) return mm[0];
  }
  return null;
}

const key = (c: Crit) => `${c.kind}:${norm(String(c.params.skill || c.params.language || c.params.category || c.params.name || c.params.text || c.params.domain || ""))}`;
function dedupe(cs: Crit[]): Crit[] {
  const seen = new Set<string>();
  return cs.filter((c) => (seen.has(key(c)) ? false : (seen.add(key(c)), true)));
}
function capRequired(cs: Crit[]): Crit[] {
  let n = 0;
  return cs.map((c) => (c.required && ++n > 3 ? { ...c, required: false } : c));
}

/** Brouillon par règles : mêmes résultats que le back-end sur les exemples, mêmes règles ailleurs. */
export function parseBrief(brief: string): { form: JobForm; notes: string[] } {
  const text = brief.replace(/\s+/g, " ").trim();
  const ex = A.examples[text];
  if (ex) return { form: stripPrivate(ex[0]), notes: ex[1] };
  const t = norm(text);
  const notes: string[] = [];
  const form: JobForm & Record<string, any> = { title: "", missions: [], criteria: [], benefits: [], questions: [], remote: "non" };
  const segments = text.split(/[,;\n]| - | – |\|/).map((s) => s.trim()).filter(Boolean);
  const used = new Set<number>();
  const sal = salary(text);
  if (sal) {
    Object.assign(form, sal);
    segments.forEach((s, i) => { if (salary(s)) used.add(i); });
    if (/(?:€|euros?|\bk)\s*(?:\/\s*mois\s*)?net\b|\bnet\s*(?:\/|par)?\s*mois\b/.test(t)) notes.push("Montant indiqué en net : l'offre affiche un salaire brut, corrigez-le à l'étape « Les conditions ».");
  } else notes.push("Rémunération à indiquer (obligatoire dans l'offre).");
  const contract = (A.contract_words as [string, string][]).find(([p]) => re(p).test(t))?.[1] || null;
  form.contract = contract || "CDI";
  if (!contract) notes.push("Type de contrat non précisé : CDI proposé par défaut.");
  if (contract && ["CDD", "Intérim", "Saisonnier", "Stage", "Alternance"].includes(contract)) {
    const m = /(\d{1,2})\s*(mois|semaines?|jours?|ans?)\b/.exec(t);
    if (m && /^(mois|semaine|jour)/.test(m[2])) form.contract_duration = `${m[1]} ${m[2]}`;
  }
  if (/full remote|100\s*%\s*(?:teletravail|remote)|teletravail (?:total|complet)/.test(t)) form.remote = "total";
  else if (/teletravail|remote|hybride/.test(t)) form.remote = "partiel";
  const hours: string[] = [];
  if (/temps partiel|mi-temps|mi temps/.test(t)) hours.push("Temps partiel");
  const h = /\b(\d{2})\s*h(?:eures)?\b(?!\s*\d)/.exec(t);
  if (h && Number(h[1]) >= 15 && Number(h[1]) <= 48) hours.push(`${h[1]} h par semaine`);
  for (const [p, l] of [[/week-?ends?/, "travail le week-end"], [/\bde nuit\b|\bnuits?\b/, "travail de nuit"], [/\bsoir(?:ee)?s?\b/, "service du soir"]] as [RegExp, string][]) if (p.test(t)) hours.push(l);
  if (hours.length) { const j = hours.join(", "); form.hours = j[0].toUpperCase() + j.slice(1); }
  if (/des que possible|asap|immediat/.test(t)) form.start_date = "Dès que possible";

  let titleSeg = segments[0] || text;
  used.add(0);
  titleSeg = titleSeg.replace(/\s(?:à|a|sur)\s+[A-ZÉÈÂÎÔ].*$/, "").replace(re(A.title_cut, "i"), "").trim().replace(/\d.*$/, "").trim();
  const title = cleanTitle(titleSeg) || "Poste à pourvoir";
  form.title = title;
  const fam = family(title) || family(text);

  const explicit: Crit[] = [];
  let y = years(t);
  if (y === null) { const w = Object.keys(SENIORITY).find((w) => re(`\\b${esc(norm(w))}\\b`).test(t)); y = w ? SENIORITY[w] : null; }
  const domain = fam?.domain || norm(title);
  if (y) explicit.push({ kind: "experience", required: true, params: { years: y, domain } });
  const skills: string[] = [];
  for (const [k, canon] of Object.entries(SOFTWARE)) if (re(`(?<![\\w+#.])${esc(k)}(?![\\w+#])`).test(t) && !skills.includes(canon)) skills.push(canon);
  skills.slice(0, 3).forEach((s) => explicit.push({ kind: "competence", required: true, params: { skill: s, level: 2 } }));
  const langRe = re(`\\b(${Object.keys(LANG_WORDS).join("|")})\\b(?:\\s+(?:niveau\\s+)?([abc][12]|${Object.keys(LANG_LEVELS).join("|")})\\b)?`, "g");
  for (const m of t.matchAll(langRe)) {
    const lvl = (m[2] || "").toUpperCase();
    const level = CEFR.includes(lvl) ? lvl : LANG_LEVELS[(m[2] || "").toLowerCase()] || "B1";
    const end = (m.index ?? 0) + m[0].length;
    explicit.push({ kind: "langue", required: /exig|indispensable|obligatoire|imperatif/.test(t.slice(end, end + 30)), params: { language: LANG_WORDS[m[1]], level } });
  }
  for (const m of t.matchAll(/permis\s+(?:de conduire\s+)?([a-z]{1,2}e?)\b/g)) {
    let cat = m[1].toUpperCase();
    if (["DE", "DU", "D"].includes(cat) && /^permis\s+d[eu]\b/.test(t.slice(m.index))) cat = "B";
    const end = (m.index ?? 0) + m[0].length;
    if (PERMIS.includes(cat)) explicit.push({ kind: "permis", required: /exig|indispensable|obligatoire/.test(t.slice(end, end + 25)), params: { category: cat } });
  }
  for (const [p, level] of A.diplomas as [string, number][]) if (re(norm(p)).test(t)) { explicit.push({ kind: "diplome", required: false, params: { level, domain: "" } }); break; }
  for (const [p, name] of A.habilitations as [string, string | null][]) {
    const m = re(norm(p)).exec(t);
    if (!m) continue;
    const n = name ?? `CACES${m[1] ? ` ${m[1].toUpperCase().replace(/\s/g, "")}` : ""}${m[2] ? ` catégorie ${m[2].toUpperCase()}` : ""}`;
    explicit.push({ kind: "habilitation", required: true, params: { name: n } });
  }
  const exp = dedupe(explicit);
  const extra: Crit[] = [];
  if (y === null && fam) extra.push({ kind: "experience", required: false, params: { years: 1, domain: fam.domain } });
  for (const [kind, params] of fam?.criteria || []) {
    if (["diplome", "habilitation", "langue", "permis"].includes(kind) && exp.some((c) => c.kind === kind)) continue;
    extra.push({ kind, required: false, params: { ...params } });
  }
  form.criteria = capRequired(dedupe([...exp, ...extra])).slice(0, 6);
  if (fam) form.missions = [...fam.missions];
  else notes.push("Ajoutez 3 ou 4 missions : ce que la personne fera au quotidien.");
  const loc = location(text, segments, used, title);
  if (loc) form.location = loc; else notes.push("Lieu de travail à préciser.");
  const de = /^[aeiouyhâàéèêîôûAEIOUYHÂÀÉÈÊÎÔÛ]/.test(title) ? "d'" : "de ";
  const where = form.location ? ` à ${form.location}` : "";
  let summary = `Nous recherchons une personne pour le poste ${de}${title}${where}, en ${form.contract}${form.contract_duration ? ` (${form.contract_duration})` : ""}.`;
  if (form.missions.length) summary += " Au quotidien : " + form.missions.slice(0, 3).map((m) => m[0].toLowerCase() + m.slice(1)).join(" ; ") + ".";
  form.summary = summary;
  const qs: string[] = [];
  const sk = form.criteria.filter((c) => c.kind === "competence").map((c) => c.params.skill);
  if (sk.length) qs.push(`Décrivez une réalisation récente où vous avez utilisé ${sk[0]} : le contexte, votre rôle et le résultat.`);
  if (fam) qs.push(fam.question);
  if (form.missions.length) { const m = form.missions[0]; qs.push(`Comment vous y prenez-vous pour « ${m[0].toLowerCase() + m.slice(1)} » ? Donnez un exemple concret.`); }
  const e = form.criteria.find((c) => c.kind === "experience");
  if (e && qs.length < 3) qs.push(`Quelle situation difficile avez-vous rencontrée en ${e.params.domain}, et comment l'avez-vous résolue ?`);
  if (qs.length < 3) qs.push("Quelle réalisation professionnelle récente vous rend le plus fier ou la plus fière, et pourquoi ?");
  if (qs.length < 3) qs.push("Qu'est-ce qui vous intéresse dans ce poste ?");
  form.questions = qs.slice(0, 3);
  return { form: stripPrivate(form), notes };
}

function stripPrivate(f: any): JobForm {
  const { _explicit, ...rest } = f;
  void _explicit;
  return { ...rest, benefits: rest.benefits || [], missions: rest.missions || [], criteria: rest.criteria || [], questions: rest.questions || [] } as JobForm;
}
