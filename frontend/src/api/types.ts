export type Criterion = { id: string; label: string; kind: string; required: boolean; params?: Record<string, any> };

export type Profile = {
  title: string;
  missions: string[];
  criteria: Criterion[];
  salary: { min?: number | null; max?: number | null; period?: string | null; text?: string | null };
  hours?: string | null;
  location?: string | null;
  contract?: string | null;
  start_date?: string | null;
  remote?: string | null;
  rome_code?: string | null;
  rome_label?: string | null;
  company_pitch?: string | null;
  benefits?: string[];
};

export type ScreeningQuestion = {
  id: string;
  kind: string;
  label: string;
  input: "number" | "select" | "yesno" | "text";
  required: boolean;
  options?: { value: string | number; label: string }[];
  min?: number;
  max?: number;
  unit?: string;
  help?: string;
};

export type JobForm = {
  title: string;
  rome_code?: string;
  rome_label?: string;
  missions: string[];
  criteria: { kind: string; required: boolean; params: Record<string, any> }[];
  contract?: string;
  contract_duration?: string;
  hours?: string;
  salary_min?: number | "";
  salary_max?: number | "";
  salary_period?: string;
  location?: string;
  location_citycode?: string;
  start_date?: string;
  remote?: string;
  company_pitch?: string;
  benefits: string[];
};

/** Mention à retirer, rattachée au champ concerné (« title », « missions.2 », « long »…). */
export type Issue = { field: string | null; rule?: string; match?: string | null; message: string };

export type FormPreview = {
  offer: { short: string; long: string } | null;
  questions: ScreeningQuestion[];
  issues: Issue[];
  criteria?: Criterion[];
};

export type Billing = {
  plan: "free" | "premium";
  plan_name: string;
  status: string | null;
  interval: string | null;
  period_end: string | null;
  features: string[];
  usage: { active_recruitments: number; limit: number | null };
  billing_mode: "demo" | "stripe" | "disabled";
  prices: { monthly: number; yearly: number; yearly_per_month: number; currency: string; tax: string };
  trial_days: number;
  has_customer: boolean;
  catalog: Record<string, string>;
};

export type Channel = { id: string; label: string; status: "online" | "closed" | string; at?: string; detail?: string };

export type Offer = {
  id: string;
  version: number;
  short: string;
  long: string;
  status: string;
  channels: Channel[];
  created_by: string;
  created_at: string;
};

export type GridQuestion = {
  id: string;
  text: string;
  kind: string;
  criterion_id?: string | null;
  anchors: Record<"1" | "2" | "3", string>;
};

export type Proposal = {
  id: string;
  kind: string;
  step: number;
  page?: string | null;
  title: string;
  summary?: string | null;
  payload: any;
  status: string;
  created_at: string;
  decided_at?: string | null;
};

export type PageId = "offre" | "candidatures" | "entretiens" | "debrief" | "decision";

export type RecruitmentSummary = {
  id: string;
  title: string;
  state: string;
  state_label: string;
  step: number;
  page: PageId;
  created_at: string;
  published_at?: string | null;
  closed_at?: string | null;
  applications: number;
  outcome?: string | null;
  pending: { id: string; kind: string; title: string; page?: PageId | null } | null;
};

export type Counts = {
  applications: number;
  unscreened: number;
  shortlisted: number;
  interviews: number;
  to_schedule: number;
  upcoming: number;
  to_note: number;
  noted: number;
};

export type RecruitmentDetail = Omit<RecruitmentSummary, "pending"> & {
  steps: string[];
  profile: Profile;
  pending: Proposal[];
  history: Proposal[];
  offer: Offer | null;
  grid: { id: string; version: number; questions: GridQuestion[]; status: string } | null;
  groups: Record<string, number>;
  counts: Counts;
  busy: string[];
  apply_link: string | null;
  interview_location?: string | null;
  interview_minutes: number;
  free_slots: number;
  sources?: Record<string, number>;
  result?: any;
};

export type Evaluation = {
  criterion_id: string;
  label: string;
  required: boolean;
  status: "met" | "partial" | "not_met" | "unknown";
  justification: string;
  excerpts: string[];
  declared?: string | null;
  evidence?: "confirmed" | "declared" | "inconsistent" | "cv" | null;
};

export type ApplicationItem = {
  id: string;
  name: string;
  source: string;
  status: string;
  group: string | null;
  shortlisted: boolean;
  rescued: boolean;
  created_at: string;
  screened: boolean;
  has_cv: boolean;
  pool_consent: boolean;
  anonymized: boolean;
  evaluations: Evaluation[];
  interview: { id: string; status: string; start: string | null; end: string | null; location?: string | null } | null;
  debrief_status: string | null;
  has_answers?: boolean;
};

export type DebriefNote = { score: number | null; notes: string; quote?: string | null };

export type SentMessage = { id: string; kind: string; label: string; subject?: string | null; body: string; status: string; created_at: string };

export type ApplicationDetail = ApplicationItem & {
  email?: string | null;
  phone?: string | null;
  message?: string | null;
  facts: { type: string; value: string; excerpt: string }[];
  cv_filename?: string | null;
  cv_text?: string | null;
  cv_link?: string | null;
  answers?: { question: string; answer: string }[];
  debrief: { notes: Record<string, DebriefNote>; overall?: string | null; status: string } | null;
  messages?: SentMessage[];
};

export type InterviewItem = {
  id: string;
  application_id: string;
  name: string;
  recruitment_id: string;
  recruitment_title: string;
  status: string;
  start: string | null;
  end: string | null;
  location?: string | null;
  invited_at: string;
  booked_at?: string | null;
  debrief_status?: string | null;
  /** Le candidat choisit lui-même son créneau en ligne (Premium). */
  self_booking?: boolean;
};

export type Agenda = { upcoming: InterviewItem[]; to_schedule: InterviewItem[]; to_note: InterviewItem[] };

export type Slot = { id: string; start: string; end: string };

export type Comparison = {
  questions: { id: string; text: string }[];
  candidates: {
    application_id: string;
    name: string;
    debrief_status: string | null;
    scores: Record<string, number | null>;
    notes: Record<string, string | null>;
    total: number | null;
    answered: number;
    overall?: string | null;
  }[];
  max_total?: number;
};

export type AuditItem = {
  id: number;
  at: string;
  actor_type: string;
  action: string;
  label: string;
  entity?: string | null;
  subject?: string | null;
  details: Record<string, any>;
  hash: string;
};

export type Me = {
  id: string;
  email: string;
  name?: string | null;
  phone?: string | null;
  role: string;
  theme: "light" | "dark";
  company: {
    id: string;
    name: string;
    slug: string;
    address?: string | null;
    headcount?: number | null;
    siren?: string | null;
    naf_code?: string | null;
    headcount_range?: string | null;
  } | null;
  app: { name: string; demo_mode: boolean; environment: string };
  plan: { id: "free" | "premium"; name: string; features: string[]; active_recruitments_limit: number | null };
};

export type Metrics = {
  summary: Record<string, any>;
  recruitments: Record<string, any>[];
};

export type PublicOffer = {
  title: string;
  company: string;
  company_slug: string;
  long: string;
  open: boolean;
  profile: { location?: string | null; contract?: string | null; hours?: string | null; salary?: Profile["salary"];
    remote?: string | null; start_date?: string | null };
  questions: ScreeningQuestion[];
};

export type JobRef = { label: string; rome_code: string; rome_label: string; domain: string };
export type KnowledgeRef = { label: string; category: string; subcategory: string };
export type AddressRef = { label: string; city?: string; postcode?: string; citycode?: string; context?: string; type?: string };
export type CompanyRef = { siren: string; name: string; display_name: string; address?: string; naf_code?: string; headcount_range?: string | null };
export type RefLists = { languages: string[]; cefr: string[]; permis: string[]; diploma_levels: { value: number; label: string }[]; contracts: string[] };
export type MailTemplate = { id: string; label: string; subject: string; body: string };

export type PublicBooking = {
  title: string;
  company: string;
  status: string;
  first_name?: string | null;
  minutes: number;
  location?: string | null;
  start: string | null;
  closed: boolean;
  mode: "online" | "manual";
  slots: Slot[];
};

export type CandidateData = {
  company: string;
  company_slug: string;
  first_name?: string | null;
  last_name?: string | null;
  email?: string | null;
  phone?: string | null;
  pool_consent: boolean;
  deletion_due: string;
  applications: { title: string; status: string; sent_at: string; cv_filename?: string | null;
    evaluations: { label: string; status: string; justification?: string | null }[] }[];
};

export type BulkResult = { done: number; invited?: number; to_schedule?: number };
