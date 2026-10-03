import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowLeft, ArrowRight, Award, BookOpen, Car, Clock, GraduationCap, Languages, MessageSquareText, Plus, RotateCcw, Send, Sparkles, Trash2, Wrench } from "lucide-react";
import { ApiError } from "../api/client";
import type { AddressRef, Draft, FormPreview, Issue, JobForm, JobRef, KnowledgeRef, RefLists } from "../api/types";
import { IS_DEMO, useApi, useDebounced, useLoad, useSession, useToast, useUpgrade } from "../lib/ctx";
import { Combobox } from "../ui/Combobox";
import { Button, Card, Field, IssueLine, Notice, OfferText, PageHeader, Segmented, removeMention } from "../ui/kit";

type Crit = JobForm["criteria"][number];

export const DEMO_FORM: JobForm = {
  title: "Assistant commercial / Assistante commerciale", rome_code: "D1401", rome_label: "Assistant commercial / Assistante commerciale",
  missions: ["Établir les devis et suivre leur transformation", "Relancer les clients", "Préparer et suivre les commandes jusqu'à la livraison", "Répondre au téléphone et orienter les appels"],
  criteria: [
    { kind: "experience", required: true, params: { years: 2, domain: "administration des ventes" } },
    { kind: "competence", required: true, params: { skill: "Excel", level: 2 } },
    { kind: "permis", required: false, params: { category: "B" } },
  ],
  contract: "CDI", hours: "35 h, du lundi au vendredi", salary_min: 2100, salary_max: 2400, salary_period: "mois",
  location: "Villeurbanne (69100)", location_citycode: "69266", start_date: "Dès que possible", remote: "non",
  company_pitch: "Négoce Durand distribue des matériaux de construction aux artisans de la région lyonnaise depuis 1987. Nous sommes 18 personnes.",
  benefits: ["Tickets restaurant", "Mutuelle prise en charge à 60 %"],
  questions: [],
};

const EMPTY: JobForm = { title: "", missions: [""], criteria: [], contract: "CDI", salary_period: "mois", remote: "non", benefits: [], questions: [], summary: "" };

const EXAMPLES = [
  "Dev Python junior, 3 ans, Lyon, 2500-3000 €",
  "Serveur en CDD 6 mois à Annecy, 1 900 € brut, week-ends",
  "Assistant commercial ADV, 2 ans, Excel, Villeurbanne, 2 100 à 2 400 € par mois",
  "Électricien bâtiment confirmé, CDI, Nantes, 32-36 k€, habilitation électrique",
];
const MAX_QUESTIONS = 3;

const KINDS: { kind: string; label: string; icon: React.ReactNode; params: Record<string, any> }[] = [
  { kind: "experience", label: "Expérience", icon: <Clock size={16} />, params: { years: 2, domain: "" } },
  { kind: "competence", label: "Compétence, logiciel", icon: <Wrench size={16} />, params: { skill: "", level: 2 } },
  { kind: "diplome", label: "Diplôme", icon: <GraduationCap size={16} />, params: { level: 5, domain: "" } },
  { kind: "permis", label: "Permis", icon: <Car size={16} />, params: { category: "B" } },
  { kind: "langue", label: "Langue", icon: <Languages size={16} />, params: { language: "Anglais", level: "B1" } },
  { kind: "habilitation", label: "Habilitation", icon: <Award size={16} />, params: { name: "" } },
  { kind: "autre", label: "Autre", icon: <BookOpen size={16} />, params: { text: "" } },
];

const STEPS = ["Le poste", "Les critères", "Les conditions", "Aperçu"];
const stepOfField = (field: string | null) => {
  if (!field) return 3;
  if (field === "title" || field === "summary" || field.startsWith("missions")) return 0;
  if (field.startsWith("criteria") || field.startsWith("questions")) return 1;
  return 2;
};

function clean(f: JobForm): JobForm {
  return { ...f, missions: f.missions.filter((m) => m.trim()), questions: (f.questions || []).filter((q) => q.trim()),
    salary_min: f.salary_min === "" ? undefined : f.salary_min, salary_max: f.salary_max === "" ? undefined : f.salary_max };
}

/** Une phrase → brouillon complet du formulaire (assistant IA, ou règles si l'IA n'est pas configurée). */
function AssistantCard({ draft, onDraft, onReset }: { draft: Draft | null; onDraft: (d: Draft) => void; onReset: () => void }) {
  const api = useApi();
  const { me } = useSession();
  const notify = useToast();
  const [brief, setBrief] = useState("");
  const [busy, setBusy] = useState(false);
  const ai = !!me?.app.ai_assistant;
  const go = async (text = brief) => {
    if (text.trim().length < 4) return;
    setBusy(true);
    try {
      onDraft(await api.draft(text.trim()));
    } catch (e) {
      notify((e as Error).message, "bad");
    } finally {
      setBusy(false);
    }
  };
  if (draft) {
    return (
      <Notice tone="brand" icon={<Sparkles size={16} />}
        title={draft.engine === "ia" ? "Brouillon rédigé par l'assistant IA : relisez chaque étape avant de publier." : "Brouillon préparé à partir de votre phrase : relisez chaque étape avant de publier."}
        actions={<button className="btn sm" onClick={onReset}><RotateCcw size={14} /> Repartir d'une autre phrase</button>}>
        {draft.notes.length > 0 && <ul style={{ margin: "4px 0 0", paddingLeft: 18 }}>{draft.notes.map((n) => <li key={n}>{n}</li>)}</ul>}
      </Notice>
    );
  }
  return (
    <Card className="highlight" title={<><span className="eyebrow">Gagnez une heure</span><h2>Décrivez le poste en une phrase</h2></>}
      sub={ai ? "L'assistant IA rédige l'offre, propose les critères clés et trois questions de présélection. Vous relisez tout avant de publier."
        : "Le brouillon se prépare à partir de votre phrase : offre, critères clés, trois questions de présélection. Vous relisez tout avant de publier."}>
      <form className="row" style={{ flexWrap: "nowrap" }} onSubmit={(e) => { e.preventDefault(); void go(); }}>
        <input className="input" aria-label="Le poste en une phrase" placeholder="Ex. Dev Python junior, 3 ans, Lyon, 2500-3000 €" value={brief}
          onChange={(e) => setBrief(e.target.value)} maxLength={1200} />
        <button className="btn primary" type="submit" disabled={busy || brief.trim().length < 4}>{busy ? <span className="spinner" /> : <Sparkles size={16} />} Préparer</button>
      </form>
      <div className="chips">
        {EXAMPLES.map((x) => <button key={x} type="button" className="chip" disabled={busy} onClick={() => { setBrief(x); void go(x); }}>{x}</button>)}
      </div>
      <span className="xs muted">N'indiquez ni nom de personne ni critère personnel (âge, situation de famille…).{ai ? " Seule cette phrase est envoyée à notre fournisseur d'IA, jamais une donnée de candidat." : ""} Vous pouvez aussi remplir le formulaire vous-même, ci-dessous.</span>
    </Card>
  );
}

export default function NewRecruitment() {
  const api = useApi();
  const nav = useNavigate();
  const notify = useToast();
  const upgrade = useUpgrade();
  const { touch } = useSession();
  const [f, setF] = useState<JobForm>(IS_DEMO ? DEMO_FORM : EMPTY);
  const [step, setStep] = useState(0);
  const [tried, setTried] = useState<boolean[]>([false, false, false, false]);
  const [lists] = useLoad<RefLists>(() => api.refLists(), []);
  const [billing] = useLoad(() => api.billing(), []);
  const atLimit = !!billing?.usage.limit && billing.usage.active_recruitments >= billing.usage.limit;
  const [preview, setPreview] = useState<FormPreview | null>(null);
  const [serverIssues, setServerIssues] = useState<Issue[] | null>(null);
  const [busy, setBusy] = useState<"publish" | "draft" | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const debounced = useDebounced(f, 400);
  const set = <K extends keyof JobForm>(k: K, v: JobForm[K]) => { setServerIssues(null); setF((x) => ({ ...x, [k]: v })); };

  useEffect(() => {
    api.previewForm(clean(debounced)).then(setPreview).catch(() => {});
  }, [api, debounced]);

  const issues = serverIssues || preview?.issues || [];
  const at = (field: string) => issues.filter((i) => i.field === field && (i.match || tried[stepOfField(field)]));
  const stepHasIssue = (n: number) => issues.some((i) => stepOfField(i.field) === n && (i.match || tried[n]));
  const required = f.criteria.filter((c) => c.required).length;
  const canNext = [f.title.trim().length >= 3, required <= 3, true, true][step];

  const next = async () => {
    setTried((t) => t.map((v, i) => (i === step ? true : v)));
    let current = issues;
    try {
      const fresh = await api.previewForm(clean(f)); // pas d'aperçu en retard sur la saisie
      setPreview(fresh);
      current = serverIssues || fresh.issues;
    } catch {
      /* aperçu indisponible : on garde le dernier */
    }
    if (canNext && !current.some((i) => stepOfField(i.field) === step)) setStep(step + 1);
  };

  const submit = async (publish: boolean) => {
    setTried([true, true, true, true]);
    if (atLimit) return upgrade("Avec l'offre Gratuit, un recrutement à la fois. Clôturez celui en cours ou passez à l'offre Pro.");
    setBusy(publish ? "publish" : "draft");
    try {
      const r = await api.createRecruitment(clean(f), publish);
      touch();
      notify(publish ? "Offre publiée" : "Brouillon enregistré");
      nav(`/recrutements/${r.id}/${publish ? "candidatures" : "offre"}`);
    } catch (e) {
      if (e instanceof ApiError && e.issues.length) {
        setServerIssues(e.issues);
        setStep(stepOfField(e.issues[0].field));
      } else if (e instanceof ApiError && (e.status === 402 || e.upgrade)) upgrade(e.message);
      else notify((e as Error).message, "bad");
    } finally {
      setBusy(null);
    }
  };

  const applyDraft = (d: Draft) => {
    setDraft(d);
    setF({ ...EMPTY, ...d.form, missions: d.form.missions.length ? d.form.missions : [""], questions: d.form.questions || [],
      benefits: d.form.benefits || [], summary: d.form.summary || "" });
    setServerIssues(d.issues.length ? d.issues : null);
    setTried([false, false, false, false]);
    setStep(0);
  };

  return (
    <main className="content">
      <PageHeader crumbs={<><Link to="/recrutements">Recrutements</Link> / Nouveau</>} title="Nouveau recrutement" />
      {atLimit && (
        <Notice tone="warn" title="Un recrutement est déjà en cours"
          actions={<><Link className="btn sm" to="/recrutements">Voir le recrutement en cours</Link><Button size="sm" variant="primary" onClick={() => upgrade()}>Passer à Pro</Button></>}>
          L'offre Gratuit permet un recrutement à la fois. Vous pouvez préparer celui-ci dès maintenant.
        </Notice>
      )}
      <div className="wizard stack lg">
        <AssistantCard draft={draft} onDraft={applyDraft} onReset={() => { setDraft(null); setF(EMPTY); setServerIssues(null); setStep(0); }} />
        <ol className="wizard-steps" aria-label="Étapes">
          {STEPS.map((s, i) => (
            <li key={s} className={i === step ? "on" : i < step ? "done" : ""} aria-current={i === step ? "step" : undefined}
              onClick={() => i < step && setStep(i)}>
              <span className="n">{i < step && !stepHasIssue(i) ? "✓" : i + 1}</span><span className="lbl">{s}</span>
            </li>
          ))}
        </ol>

        {step === 0 && (
          <Card title="Le poste" sub="L'intitulé et ce que la personne fera au quotidien.">
            <Field label="Intitulé du poste" htmlFor="title" hint={f.rome_code ? <>Métier : {f.rome_label}</> : "Choisissez dans la liste des métiers, ou saisissez librement."}
              error={at("title").map((i, k) => <IssueLine key={k} issue={i} onRemove={() => set("title", removeMention(f.title, i.match!))} />)}>
              <Combobox<JobRef> id="title" value={f.title} placeholder="Ex. assistant commercial, serveur, chef d'équipe…"
                onChange={(v) => { setServerIssues(null); setF((x) => ({ ...x, title: v, rome_code: undefined, rome_label: undefined })); }}
                onPick={(j) => { setServerIssues(null); setF((x) => ({ ...x, title: j.label, rome_code: j.rome_code, rome_label: j.rome_label })); }}
                search={async (q) => (await api.refJobs(q)).results}
                render={(j) => <><b>{j.label}</b><span className="xs muted">{j.domain}</span></>}
                footer="Référentiel des métiers ROME — France Travail" />
            </Field>
            <Field label="Le poste en quelques lignes" htmlFor="summary" hint="Facultatif : le contexte du poste, ce qui le rend intéressant."
              error={at("summary").map((i, k) => <IssueLine key={k} issue={i} onRemove={() => set("summary", removeMention(f.summary || "", i.match!))} />)}>
              <textarea id="summary" className={`textarea ${at("summary").length ? "has-issue" : ""}`} rows={3} value={f.summary || ""}
                onChange={(e) => set("summary", e.target.value)} placeholder="Ex. Vous rejoignez une équipe de quatre personnes qui développe notre outil de facturation." />
            </Field>
            <div className="stack sm">
              <span className="lbl strong small">Missions</span>
              {f.missions.map((m, i) => (
                <div className="stack sm" key={i}>
                  <div className="row" style={{ flexWrap: "nowrap" }}>
                    <input className={`input ${at(`missions.${i}`).length ? "has-issue" : ""}`} aria-label={`Mission ${i + 1}`} value={m} placeholder="Ex. Établir les devis"
                      onChange={(e) => set("missions", f.missions.map((x, j) => (j === i ? e.target.value : x)))} />
                    <button className="btn ghost icon" aria-label="Retirer la mission" onClick={() => set("missions", f.missions.filter((_, j) => j !== i))}><Trash2 size={16} /></button>
                  </div>
                  {at(`missions.${i}`).map((iss, k) => <IssueLine key={k} issue={iss} onRemove={() => set("missions", f.missions.map((x, j) => (j === i ? removeMention(x, iss.match!) : x)))} />)}
                </div>
              ))}
              <div className="row">
                <button className="btn sm" onClick={() => set("missions", [...f.missions, ""])}><Plus size={14} /> Ajouter une mission</button>
                <div style={{ flex: "1 1 260px" }}><MissionSuggest onPick={(s) => set("missions", [...f.missions.filter((x) => x.trim()), s])} /></div>
              </div>
            </div>
          </Card>
        )}

        {step === 1 && (
          <Card title="Les critères" sub="Chaque critère devient une question posée au candidat. Deux ou trois indispensables suffisent."
            actions={<span className={`badge ${required > 3 ? "bad" : required ? "brand" : ""}`}>{required}/3 indispensables</span>}>
            {at("criteria").map((i, k) => <IssueLine key={k} issue={i} />)}
            {f.criteria.map((c, i) => (
              <CriterionEditor key={i} c={c} lists={lists} issues={at(`criteria.${i}`)}
                onChange={(nc) => set("criteria", f.criteria.map((x, j) => (j === i ? nc : x)))}
                onRemove={() => set("criteria", f.criteria.filter((_, j) => j !== i))} />
            ))}
            <div className="stack sm">
              <span className="small muted">Ajouter un critère</span>
              <div className="kinds">
                {KINDS.map((k) => (
                  <button key={k.kind} className="btn sm" onClick={() => set("criteria", [...f.criteria, { kind: k.kind, required: required < 2, params: { ...k.params } }])}>
                    {k.icon} {k.label}
                  </button>
                ))}
              </div>
            </div>
            <hr className="sep" />
            <QuestionsEditor questions={f.questions || []} issues={issues.filter((i) => i.field?.startsWith("questions."))}
              onChange={(q) => set("questions", q)} />
          </Card>
        )}

        {step === 2 && (
          <Card title="Les conditions" sub="Ce que vous proposez. Tout apparaît dans l'offre.">
            <div className="grid c2">
              <Field label="Contrat" htmlFor="contract">
                <select id="contract" className="select" value={f.contract} onChange={(e) => set("contract", e.target.value)}>
                  {(lists?.contracts || ["CDI", "CDD"]).map((c) => <option key={c}>{c}</option>)}
                </select>
              </Field>
              {["CDD", "Intérim", "Saisonnier", "Stage", "Alternance"].includes(f.contract || "") ? (
                <Field label="Durée" htmlFor="duration"><input id="duration" className="input" placeholder="Ex. 6 mois" value={f.contract_duration || ""} onChange={(e) => set("contract_duration", e.target.value)} /></Field>
              ) : <Field label="Prise de poste" htmlFor="start"><input id="start" className="input" placeholder="Ex. Dès que possible" value={f.start_date || ""} onChange={(e) => set("start_date", e.target.value)} /></Field>}
            </div>
            <Field label="Salaire brut" error={at("salary").map((i, k) => <IssueLine key={k} issue={i} />)}>
              <div className="row" style={{ flexWrap: "nowrap" }}>
                <input className="input tnum" type="number" min={0} aria-label="Minimum" placeholder="Min." value={f.salary_min ?? ""} onChange={(e) => set("salary_min", e.target.value === "" ? "" : Number(e.target.value))} />
                <span className="muted">à</span>
                <input className="input tnum" type="number" min={0} aria-label="Maximum" placeholder="Max." value={f.salary_max ?? ""} onChange={(e) => set("salary_max", e.target.value === "" ? "" : Number(e.target.value))} />
                <select className="select" style={{ flex: "0 0 120px" }} aria-label="Période" value={f.salary_period} onChange={(e) => set("salary_period", e.target.value)}>
                  <option value="mois">€ / mois</option><option value="an">€ / an</option><option value="heure">€ / heure</option>
                </select>
              </div>
            </Field>
            <div className="grid c2">
              <Field label="Lieu de travail" htmlFor="loc">
                <Combobox<AddressRef> id="loc" value={f.location || ""} placeholder="Commune" minChars={3}
                  onChange={(v) => setF((x) => ({ ...x, location: v, location_citycode: undefined }))}
                  onPick={(a) => setF((x) => ({ ...x, location: `${a.city || a.label}${a.postcode ? ` (${a.postcode})` : ""}`, location_citycode: a.citycode }))}
                  search={async (q) => (await api.refAddresses(q, true)).results}
                  render={(a) => <><b>{a.label}</b><span className="xs muted">{a.postcode} · {a.context}</span></>}
                  footer="Base adresse nationale" />
              </Field>
              <Field label="Horaires" htmlFor="hours" error={at("hours").map((i, k) => <IssueLine key={k} issue={i} onRemove={() => set("hours", removeMention(f.hours || "", i.match!))} />)}>
                <input id="hours" className="input" placeholder="Ex. 35 h, du lundi au vendredi" value={f.hours || ""} onChange={(e) => set("hours", e.target.value)} />
              </Field>
            </div>
            <Field label="Télétravail">
              <Segmented label="Télétravail" value={(f.remote || "non") as "non" | "partiel" | "total"} onChange={(v) => set("remote", v)}
                items={[{ id: "non", label: "Non" }, { id: "partiel", label: "Partiel" }, { id: "total", label: "Total" }]} />
            </Field>
            <BenefitsField benefits={f.benefits} issues={issues.filter((i) => i.field?.startsWith("benefits."))} onChange={(b) => set("benefits", b)} />
            <Field label="Votre entreprise en deux phrases" htmlFor="pitch" hint="Facultatif, mais les candidats y sont sensibles."
              error={at("company_pitch").map((i, k) => <IssueLine key={k} issue={i} onRemove={() => set("company_pitch", removeMention(f.company_pitch || "", i.match!))} />)}>
              <textarea id="pitch" className={`textarea ${at("company_pitch").length ? "has-issue" : ""}`} rows={3} value={f.company_pitch || ""} onChange={(e) => set("company_pitch", e.target.value)}
                placeholder="Ce que vous faites, depuis quand, combien vous êtes." />
            </Field>
          </Card>
        )}

        {step === 3 && <PreviewStep preview={preview} issues={issues} goTo={setStep} />}

        <div className="wizard-foot">
          {step > 0 ? <button className="btn" onClick={() => setStep(step - 1)}><ArrowLeft size={16} /> Précédent</button> : <span />}
          {step < 3 ? (
            <button className="btn primary" disabled={!canNext} onClick={next}>Suivant <ArrowRight size={16} /></button>
          ) : (
            <div className="row">
              <button className="btn" disabled={!!busy} onClick={() => submit(false)}>{busy === "draft" && <span className="spinner" />} Enregistrer en brouillon</button>
              <button className="btn primary lg" disabled={!!busy || issues.length > 0} onClick={() => submit(true)}>
                {busy === "publish" ? <span className="spinner" /> : <Send size={16} />} Publier l'offre
              </button>
            </div>
          )}
        </div>
      </div>
    </main>
  );
}

function PreviewStep({ preview, issues, goTo }: { preview: FormPreview | null; issues: Issue[]; goTo: (n: number) => void }) {
  const [tab, setTab] = useState<"offer" | "questions">("offer");
  return (
    <Card title="Aperçu" sub="L'offre telle qu'elle sera publiée, et les questions posées aux candidats."
      actions={<Segmented label="Aperçu" value={tab} onChange={setTab} items={[{ id: "offer", label: "Offre" }, { id: "questions", label: `Questions · ${preview?.questions.length ?? 0}` }]} />}>
      {issues.length > 0 && (
        <Notice tone="warn" title="À revoir avant de publier">
          <div className="stack sm">
            {issues.map((i, k) => (
              <span key={k}>{i.match ? <>« {i.match} » : </> : null}{i.message} <button className="btn link" onClick={() => goTo(stepOfField(i.field))}>Corriger</button></span>
            ))}
          </div>
        </Notice>
      )}
      {!preview?.offer ? <p className="muted">Indiquez l'intitulé du poste pour voir l'offre.</p> : tab === "offer" ? (
        <div style={{ maxHeight: 520, overflowY: "auto" }}><OfferText text={preview.offer.long} /></div>
      ) : preview.questions.length ? (
        <ol className="stack" style={{ margin: 0, paddingLeft: 18 }}>
          {preview.questions.map((q) => <li key={q.id}><span className="strong">{q.label}</span><br /><span className="xs muted">{q.input === "yesno" ? "Oui / Non" : q.input === "number" ? "Nombre d'années" : q.input === "select" ? q.options!.map((o) => o.label).join(" · ") : "Réponse libre"}</span></li>)}
        </ol>
      ) : <p className="muted">Aucun critère : les candidats envoient seulement leur CV.</p>}
      <span className="xs muted">À la publication, l'offre est mise en ligne avec son lien de candidature et diffusée sur Google pour l'emploi ; les textes pour LinkedIn, Indeed et France Travail sont prêts à copier dans la page Offre.</span>
    </Card>
  );
}

/** Questions de présélection à réponse libre : techniques, liées au métier, jamais notées. */
function QuestionsEditor({ questions, issues, onChange }: { questions: string[]; issues: Issue[]; onChange: (q: string[]) => void }) {
  return (
    <div className="stack sm">
      <div className="row between">
        <span className="lbl strong small row" style={{ gap: 8 }}><MessageSquareText size={16} /> Questions de présélection</span>
        <span className="xs muted">{questions.length}/{MAX_QUESTIONS}</span>
      </div>
      <span className="small muted">Posées au candidat quand il postule (réponse libre, quelques lignes). Vous lisez les réponses telles quelles : elles ne sont jamais notées.</span>
      {questions.map((q, i) => (
        <div className="stack sm" key={i}>
          <div className="row" style={{ flexWrap: "nowrap", alignItems: "flex-start" }}>
            <textarea className={`textarea q-text ${issues.some((x) => x.field === `questions.${i}`) ? "has-issue" : ""}`} aria-label={`Question ${i + 1}`} value={q} rows={2}
              placeholder="Ex. Comment organisez-vous vos tests avant de livrer une fonctionnalité ?"
              onChange={(e) => onChange(questions.map((x, j) => (j === i ? e.target.value : x)))} />
            <button className="btn ghost icon" aria-label="Retirer la question" onClick={() => onChange(questions.filter((_, j) => j !== i))}><Trash2 size={16} /></button>
          </div>
          {issues.filter((x) => x.field === `questions.${i}`).map((iss, k) => <IssueLine key={k} issue={{ ...iss, match: null }} />)}
        </div>
      ))}
      {questions.length < MAX_QUESTIONS && <button className="btn sm" style={{ alignSelf: "flex-start" }} onClick={() => onChange([...questions, ""])}><Plus size={14} /> Ajouter une question</button>}
    </div>
  );
}

function BenefitsField({ benefits, issues, onChange }: { benefits: string[]; issues: Issue[]; onChange: (b: string[]) => void }) {
  const [v, setV] = useState("");
  const add = () => { if (v.trim()) { onChange([...benefits, v.trim()]); setV(""); } };
  return (
    <Field label="Avantages" hint="Facultatif.">
      <div className="row" style={{ flexWrap: "nowrap" }}>
        <input className="input" value={v} placeholder="Ex. Tickets restaurant" onChange={(e) => setV(e.target.value)}
          onKeyDown={(e) => { if (e.key === "Enter") { e.preventDefault(); add(); } }} />
        <button className="btn" disabled={!v.trim()} onClick={add}>Ajouter</button>
      </div>
      {benefits.length > 0 && <div className="row" style={{ gap: 6 }}>{benefits.map((b, i) => (
        <button key={i} className="badge" onClick={() => onChange(benefits.filter((_, j) => j !== i))} title="Retirer">{b} ×</button>
      ))}</div>}
      {issues.map((i, k) => {
        const n = Number(i.field?.split(".")[1]);
        return <IssueLine key={k} issue={i} onRemove={() => onChange(benefits.map((b, j) => (j === n ? removeMention(b, i.match!) : b)).filter((b) => b.trim()))} />;
      })}
    </Field>
  );
}

function MissionSuggest({ onPick }: { onPick: (s: string) => void }) {
  const api = useApi();
  const [q, setQ] = useState("");
  return (
    <Combobox<string> value={q} onChange={setQ} placeholder="Chercher une mission type (ex. devis)"
      onPick={(s) => { onPick(s); setQ(""); }} search={async (x) => (await api.refSkills(x)).results}
      render={(s) => <span>{s}</span>} footer="Compétences du ROME — France Travail" />
  );
}

/** Retire une mention des paramètres texte d'un critère ; sinon, le critère est retiré. */
function fixCriterion(c: Crit, match: string): Crit | null {
  const params = { ...c.params };
  let changed = false;
  for (const [k, v] of Object.entries(params)) {
    if (typeof v === "string" && v.includes(match)) { params[k] = removeMention(v, match); changed = true; }
  }
  return changed ? { ...c, params } : null;
}

function CriterionEditor({ c, lists, issues, onChange, onRemove }: { c: Crit; lists: RefLists | null; issues: Issue[]; onChange: (c: Crit) => void; onRemove: () => void }) {
  const api = useApi();
  const p = c.params;
  const setP = (k: string, v: unknown) => onChange({ ...c, params: { ...p, [k]: v } });
  const meta = useMemo(() => KINDS.find((k) => k.kind === c.kind)!, [c.kind]);
  return (
    <div className="card" style={{ boxShadow: "none", background: "var(--surface-2)" }}>
      <div className="card-body" style={{ gap: 12, padding: 14 }}>
        <div className="row between">
          <span className="row strong small" style={{ gap: 8 }}>{meta.icon} {meta.label}</span>
          <div className="row">
            <label className="switch small"><input type="checkbox" checked={c.required} onChange={(e) => onChange({ ...c, required: e.target.checked })} /> Indispensable</label>
            <button className="btn ghost sm icon" aria-label="Retirer le critère" onClick={onRemove}><Trash2 size={15} /></button>
          </div>
        </div>
        {c.kind === "experience" && (
          <div className="row">
            <input className="input tnum" type="number" min={0} max={30} style={{ flex: "0 0 80px" }} aria-label="Années" value={p.years} onChange={(e) => setP("years", Number(e.target.value))} />
            <span className="muted nowrap">an(s) minimum en</span>
            <input className="input" style={{ flex: "1 1 220px" }} aria-label="Domaine" placeholder="Ex. administration des ventes" value={p.domain} onChange={(e) => setP("domain", e.target.value)} />
          </div>
        )}
        {c.kind === "competence" && (
          <div className="grid c2">
            <Combobox<KnowledgeRef | string> value={p.skill} placeholder="Ex. Excel, Sage, devis…" onChange={(v) => setP("skill", v)}
              onPick={(k) => setP("skill", typeof k === "string" ? k : k.label)}
              search={async (q) => [...(await api.refKnowledge(q, "logiciels")).results.slice(0, 6), ...(await api.refSkills(q)).results.slice(0, 6)]}
              render={(k) => typeof k === "string" ? <span>{k}</span> : <><b>{k.label}</b><span className="xs muted">{k.subcategory}</span></>}
              footer="ROME — France Travail" />
            <select className="select" aria-label="Niveau" value={p.level} onChange={(e) => setP("level", Number(e.target.value))}>
              <option value={1}>Niveau : notions</option><option value={2}>Niveau : autonome</option><option value={3}>Niveau : expert</option>
            </select>
          </div>
        )}
        {c.kind === "diplome" && (
          <div className="grid c2">
            <select className="select" aria-label="Niveau" value={p.level} onChange={(e) => setP("level", Number(e.target.value))}>
              {(lists?.diploma_levels || []).map((d) => <option key={d.value} value={d.value}>{d.label} minimum</option>)}
            </select>
            <input className="input" aria-label="Domaine" placeholder="Domaine (facultatif)" value={p.domain} onChange={(e) => setP("domain", e.target.value)} />
          </div>
        )}
        {c.kind === "permis" && (
          <select className="select" aria-label="Catégorie" value={p.category} onChange={(e) => setP("category", e.target.value)} style={{ maxWidth: 220 }}>
            {(lists?.permis || ["B"]).map((x) => <option key={x} value={x}>Permis {x}</option>)}
          </select>
        )}
        {c.kind === "langue" && (
          <div className="grid c2">
            <select className="select" aria-label="Langue" value={p.language} onChange={(e) => setP("language", e.target.value)}>
              {(lists?.languages || ["Anglais"]).map((x) => <option key={x}>{x}</option>)}
            </select>
            <select className="select" aria-label="Niveau" value={p.level} onChange={(e) => setP("level", e.target.value)}>
              {(lists?.cefr || ["B1"]).map((x) => <option key={x} value={x}>Niveau {x} minimum</option>)}
            </select>
          </div>
        )}
        {c.kind === "habilitation" && (
          <Combobox<KnowledgeRef> value={p.name} placeholder="Ex. CACES R489, habilitation électrique, SST" onChange={(v) => setP("name", v)}
            onPick={(k) => setP("name", k.label)} search={async (q) => (await api.refKnowledge(q, "habilitations")).results}
            render={(k) => <><b>{k.label}</b><span className="xs muted">{k.subcategory}</span></>} footer="ROME — France Travail" />
        )}
        {c.kind === "autre" && (
          <input className="input" aria-label="Critère" placeholder="Ex. Disponible le samedi matin" value={p.text} onChange={(e) => setP("text", e.target.value)} />
        )}
        {issues.map((i, k) => {
          const fixed = i.match ? fixCriterion(c, i.match) : null;
          return <IssueLine key={k} issue={i} onRemove={fixed ? () => onChange(fixed) : i.match ? onRemove : undefined} />;
        })}
      </div>
    </div>
  );
}
