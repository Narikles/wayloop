import type {
  AddressRef,
  Agenda,
  ApplicationDetail,
  ApplicationItem,
  AuditItem,
  Billing,
  BulkResult,
  CandidateData,
  CompanyRef,
  Comparison,
  FormPreview,
  InterviewItem,
  Issue,
  JobForm,
  JobRef,
  KnowledgeRef,
  MailTemplate,
  Me,
  Metrics,
  PublicBooking,
  PublicOffer,
  RecruitmentDetail,
  RecruitmentSummary,
  RefLists,
  Slot,
} from "./types";

export class ApiError extends Error {
  status: number;
  upgrade: boolean;
  issues: Issue[];
  constructor(status: number, message: string, upgrade = false, issues: Issue[] = []) {
    super(message);
    this.status = status;
    this.upgrade = upgrade;
    this.issues = issues;
  }
}

/** Contrat de l'API : implémenté par le vrai serveur (HttpApi) et par la démo hors ligne (DemoApi). */
export interface Api {
  demo: boolean;
  me(): Promise<Me>;
  signup(body: Record<string, any>): Promise<{ demo_link?: string | null }>;
  requestLink(email: string): Promise<{ demo_link?: string | null }>;
  exchange(token: string, next?: string | null): Promise<{ redirect: string }>;
  logout(): Promise<void>;

  listRecruitments(): Promise<RecruitmentSummary[]>;
  createRecruitment(form: JobForm, publish: boolean): Promise<RecruitmentDetail>;
  previewForm(form: JobForm): Promise<FormPreview>;
  getRecruitment(id: string): Promise<RecruitmentDetail>;
  publish(id: string): Promise<RecruitmentDetail>;
  editOffer(id: string, short: string, long: string): Promise<RecruitmentDetail>;
  accept(id: string, proposalId: string, body?: Record<string, any>): Promise<RecruitmentDetail>;
  refuse(id: string, proposalId: string): Promise<RecruitmentDetail>;
  startScreening(id: string): Promise<RecruitmentDetail>;
  abandon(id: string): Promise<RecruitmentDetail>;
  bulk(id: string, body: { application_ids: string[]; action: "email" | "reject" | "shortlist"; subject?: string; body?: string }): Promise<BulkResult>;
  mailTemplates(): Promise<MailTemplate[]>;
  exportUrl(id: string): string | null;
  /** Démo seulement : contenu du CSV, pour l'enregistrer par la visionneuse quand le lien direct est bloqué. */
  exportCsv?(id: string): string | null;

  refJobs(q: string): Promise<{ results: JobRef[]; attribution: string }>;
  refSkills(q: string): Promise<{ results: string[]; attribution: string }>;
  refKnowledge(q: string, categorie?: string): Promise<{ results: KnowledgeRef[]; attribution: string }>;
  refAddresses(q: string, communes?: boolean): Promise<{ results: AddressRef[]; error?: string }>;
  refLists(): Promise<RefLists>;
  companySearch(q: string): Promise<{ results: CompanyRef[]; error?: string }>;

  billing(): Promise<Billing>;
  checkout(interval: "month" | "year"): Promise<{ url: string }>;
  portal(): Promise<{ url: string }>;
  cancelDemo(): Promise<void>;

  listApplications(id: string): Promise<ApplicationItem[]>;
  getApplication(aid: string): Promise<ApplicationDetail>;
  saveGrid(id: string, questions: any[]): Promise<RecruitmentDetail>;
  gridPrintUrl(id: string): string | null;
  agenda(): Promise<Agenda>;
  listInterviews(id: string): Promise<{ interviews: InterviewItem[]; free_slots: Slot[]; online: boolean }>;
  addSlots(id: string, ranges: { start: string; end: string }[]): Promise<{ created: number }>;
  schedule(iid: string, start: string, location?: string | null): Promise<InterviewItem>;
  attendance(iid: string, attended: boolean): Promise<InterviewItem>;
  cancelInterview(iid: string): Promise<InterviewItem>;
  saveNotes(aid: string, notes: Record<string, any>, overall: string): Promise<ApplicationDetail>;
  comparison(id: string): Promise<Comparison>;
  openDecision(id: string): Promise<RecruitmentDetail>;
  decide(id: string, applicationId: string | null): Promise<RecruitmentDetail>;

  audit(id: string): Promise<AuditItem[]>;
  metrics(): Promise<Metrics>;
  saveSettings(body: Record<string, any>): Promise<void>;
  active(recruitmentId: string, seconds: number): Promise<void>;

  publicOffer(token: string): Promise<PublicOffer>;
  apply(token: string, form: FormData): Promise<void>;
  privacy(slug: string): Promise<{ company: string; text: string }>;
  booking(token: string): Promise<PublicBooking>;
  book(token: string, slotId: string): Promise<{ start: string | null }>;
  cancelBooking(token: string): Promise<void>;
  candidate(token: string): Promise<CandidateData>;
  withdraw(token: string): Promise<void>;
  /** Démo seulement : avance l'horloge au lendemain des entretiens prévus. */
  demoFastForward?(id: string): Promise<RecruitmentDetail>;
}

async function req<T>(method: string, url: string, body?: unknown): Promise<T> {
  const init: RequestInit = { method, credentials: "same-origin", headers: {} };
  if (body instanceof FormData) {
    init.body = body;
  } else if (body !== undefined) {
    init.body = JSON.stringify(body);
    (init.headers as Record<string, string>)["Content-Type"] = "application/json";
  }
  const r = await fetch(url, init);
  if (!r.ok) {
    let msg = `Erreur ${r.status}`;
    let upgrade = false;
    let issues: Issue[] = [];
    try {
      const j = await r.json();
      if (typeof j.detail === "string") msg = j.detail;
      else if (Array.isArray(j.detail)) msg = "Formulaire incomplet : vérifiez les champs.";
      upgrade = !!j.upgrade;
      issues = Array.isArray(j.issues) ? j.issues : [];
    } catch {
      /* réponse non JSON */
    }
    throw new ApiError(r.status, msg, upgrade, issues);
  }
  const ct = r.headers.get("content-type") || "";
  return (ct.includes("json") ? r.json() : (undefined as T)) as Promise<T>;
}

export const HttpApi: Api = {
  demo: false,
  me: () => req("GET", "/api/auth/me"),
  signup: (b) => req("POST", "/api/auth/signup", b),
  requestLink: (email) => req("POST", "/api/auth/request-link", { email }),
  exchange: (token, next) => req("POST", "/api/auth/exchange", { token, next: next || undefined }),
  logout: () => req("POST", "/api/auth/logout"),

  listRecruitments: () => req("GET", "/api/recruitments"),
  createRecruitment: (form, publish) => req("POST", "/api/recruitments", { form, publish }),
  previewForm: (form) => req("POST", "/api/recruitments/preview", { form }),
  getRecruitment: (id) => req("GET", `/api/recruitments/${id}`),
  publish: (id) => req("POST", `/api/recruitments/${id}/publish`),
  editOffer: (id, short, long) => req("PUT", `/api/recruitments/${id}/offer`, { short, long }),
  accept: (id, pid, body = {}) => req("POST", `/api/recruitments/${id}/proposals/${pid}/accept`, { body }),
  refuse: (id, pid) => req("POST", `/api/recruitments/${id}/proposals/${pid}/refuse`),
  startScreening: (id) => req("POST", `/api/recruitments/${id}/screening`),
  abandon: (id) => req("POST", `/api/recruitments/${id}/abandon`),
  bulk: (id, body) => req("POST", `/api/recruitments/${id}/bulk`, body),
  mailTemplates: () => req("GET", "/api/mail-templates"),
  exportUrl: (id) => `/api/recruitments/${id}/export.csv`,

  refJobs: (q) => req("GET", `/api/referentiels/metiers?q=${encodeURIComponent(q)}`),
  refSkills: (q) => req("GET", `/api/referentiels/competences?q=${encodeURIComponent(q)}`),
  refKnowledge: (q, categorie) => req("GET", `/api/referentiels/savoirs?q=${encodeURIComponent(q)}${categorie ? `&categorie=${categorie}` : ""}`),
  refAddresses: (q, communes) => req("GET", `/api/referentiels/adresses?q=${encodeURIComponent(q)}${communes ? "&communes=true" : ""}`),
  refLists: () => req("GET", "/api/referentiels/listes"),
  companySearch: (q) => req("GET", `/api/public/entreprises?q=${encodeURIComponent(q)}`),

  billing: () => req("GET", "/api/billing"),
  checkout: (interval) => req("POST", "/api/billing/checkout", { interval }),
  portal: () => req("POST", "/api/billing/portal"),
  cancelDemo: () => req("POST", "/api/billing/cancel-demo"),

  listApplications: (id) => req("GET", `/api/recruitments/${id}/applications`),
  getApplication: (aid) => req("GET", `/api/applications/${aid}`),
  saveGrid: (id, questions) => req("PUT", `/api/recruitments/${id}/grid`, { questions }),
  gridPrintUrl: (id) => `/api/recruitments/${id}/grid/print`,
  agenda: () => req("GET", "/api/interviews"),
  listInterviews: (id) => req("GET", `/api/recruitments/${id}/interviews`),
  addSlots: (id, ranges) => req("POST", `/api/recruitments/${id}/slots`, { ranges }),
  schedule: (iid, start, location) => req("POST", `/api/interviews/${iid}/schedule`, { start, location: location || undefined }),
  attendance: (iid, attended) => req("POST", `/api/interviews/${iid}/attendance`, { attended }),
  cancelInterview: (iid) => req("POST", `/api/interviews/${iid}/cancel`),
  saveNotes: (aid, notes, overall) => req("PUT", `/api/applications/${aid}/debrief`, { notes, overall }),
  comparison: (id) => req("GET", `/api/recruitments/${id}/comparison`),
  openDecision: (id) => req("POST", `/api/recruitments/${id}/decision/open`),
  decide: (id, application_id) => req("POST", `/api/recruitments/${id}/decision`, { application_id }),

  audit: (id) => req("GET", `/api/recruitments/${id}/audit`),
  metrics: () => req("GET", "/api/metrics"),
  saveSettings: (b) => req("PUT", "/api/settings", b),
  active: (recruitment_id, seconds) => req("POST", "/api/telemetry/active", { recruitment_id, seconds }),

  publicOffer: (token) => req("GET", `/api/public/offers/${token}`),
  apply: (token, form) => req("POST", `/api/public/offers/${token}/apply`, form),
  privacy: (slug) => req("GET", `/api/public/privacy/${slug}`),
  booking: (token) => req("GET", `/api/public/booking/${token}`),
  book: (token, slot_id) => req("POST", `/api/public/booking/${token}`, { slot_id }),
  cancelBooking: (token) => req("POST", `/api/public/booking/${token}/cancel`),
  candidate: (token) => req("GET", `/api/public/candidate/${token}`),
  withdraw: (token) => req("POST", `/api/public/candidate/${token}/withdraw`),
};
