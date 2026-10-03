export type Role = "owner" | "member";

export interface SessionUser {
  id: string;
  username: string;
  email: string;
  full_name: string | null;
  role: Role;
  is_active: boolean;
  created_at: string;
  last_login_at: string | null;
}

export interface SessionResponse {
  user: SessionUser;
  csrf_token: string;
}

export interface Page<T> {
  items: T[];
  total: number;
  page: number;
  page_size: number;
  pages: number;
}

export type AnalysisStatus = "pending" | "running" | "completed" | "failed" | "skipped";
export type DimensionStatus = "match" | "partial" | "mismatch" | "unknown";

export interface DimensionMatch {
  status: DimensionStatus;
  reason: string;
}

export interface JobMatch {
  id: string;
  score: number | null;
  confidence: number | null;
  rationale: string | null;
  matched_skills: string[];
  missing_skills: string[];
  model: string | null;
  status: "new" | "viewed" | "saved" | "dismissed" | "notified";
  is_mock: boolean;
  notified_at: string | null;
  updated_at: string;
  analysis_status: AnalysisStatus;
  analysis_error: string | null;
  analysis_attempts: number;
  analyzed_at: string | null;
  cv_checksum: string | null;
  prompt_version: string | null;
  insufficient_information: boolean;
  experience_match: DimensionStatus;
  location_match: DimensionStatus;
  work_mode_match: DimensionStatus;
  title_match: DimensionStatus;
  match_details: Record<string, DimensionMatch>;
}

export type FreshnessStatus = "fresh" | "aging" | "stale" | "expired" | "unknown";
export type AvailabilityStatus = "active" | "closed" | "possibly_closed" | "removed" | "unknown";
export type EnrichmentStatus =
  | "pending"
  | "enriched"
  | "skipped"
  | "not_found"
  | "search_unavailable"
  | "search_disabled"
  | "fetch_failed"
  | "insufficient"
  | "failed";

export interface JobWebSource {
  id: string;
  url: string;
  normalized_url: string;
  host: string;
  source_type: string;
  trust_level: number;
  match_confidence: string;
  title?: string | null;
  snippet?: string | null;
  http_status?: number | null;
  selected_as_canonical: boolean;
  discovered_at: string;
  last_checked_at?: string | null;
}

export interface Job {
  id: string;
  title: string;
  company: string;
  location: string | null;
  work_mode: "remote" | "hybrid" | "onsite" | "unknown";
  employment_type: string | null;
  seniority: string | null;
  salary_text: string | null;
  url: string | null;
  source: string;
  is_mock: boolean;
  posted_at: string | null;
  discovered_at: string;
  description_status: "ok" | "insufficient_description";
  match: JobMatch | null;

  // Phase 4 fields
  linkedin_url?: string | null;
  company_job_url?: string | null;
  canonical_url?: string | null;
  application_url?: string | null;
  source_url?: string | null;
  email_received_at?: string | null;
  valid_through?: string | null;
  last_verified_at?: string | null;
  last_enriched_at?: string | null;
  posted_at_source?: string | null;
  posted_at_confidence?: string | null;
  freshness_status?: FreshnessStatus;
  availability_status?: AvailabilityStatus;
  enrichment_status?: EnrichmentStatus;
  description?: string | null;
}

export interface JobSource {
  provider: string;
  provider_message_id: string;
  subject: string | null;
  sender: string | null;
  received_at: string | null;
  discovered_at: string;
  account_email: string | null;
}

export interface JobDetail extends Job {
  description: string | null;
  mail_account_email: string | null;
  sources: JobSource[];
  web_sources?: JobWebSource[];
  analysis_cv: {
    checksum: string | null;
    filename: string | null;
    model: string | null;
    prompt_version: string | null;
    analyzed_at: string | null;
  } | null;
}

export interface ReanalyzeResponse {
  job_id: string;
  total: number;
  status: string;
  message: string;
}

export interface RefreshJobResponse {
  job_id: string;
  status: string;
  sync_job_id: string;
  message: string;
}

export interface JobStats {
  total_jobs: number;
  new_jobs: number;
  high_match_jobs: number;
  saved_jobs: number;
  dismissed_jobs: number;
  mock_jobs: number;
  high_match_threshold: number;
  average_score: number | null;
  jobs_by_source: Record<string, number>;
  top_companies: { company: string; count: number }[];
  real_jobs: number;
  discovered_today: number;
  analyzed_jobs: number;
  pending_analysis: number;
  failed_analysis: number;
  notified_jobs: number;
  average_confidence: number | null;
  // phase 4
  enriched_jobs?: number;
  pending_enrichment?: number;
  problematic_enrichment?: number;
  fresh_jobs?: number;
  aging_jobs?: number;
  stale_jobs?: number;
  expired_jobs?: number;
}

export interface JobFilterOptions {
  sources: string[];
  locations: string[];
  companies: string[];
  work_modes: string[];
  analysis_statuses: string[];
  freshness_statuses?: string[];
  enrichment_statuses?: string[];
}

export interface Preferences {
  desired_titles: string[];
  locations: string[];
  work_modes: string[];
  keywords_include: string[];
  keywords_exclude: string[];
  min_match_score: number;
  daily_scan_enabled: boolean;
  scan_interval_hours: number;
  politeness_delay_seconds: number;
  notify_telegram: boolean;
}

export interface CV {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  checksum: string | null;
  summary: string | null;
  has_extracted_text: boolean;
  extraction_status: "ok" | "ocr_required" | "unsupported" | "empty" | "failed" | "pending";
  extraction_warning: string | null;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface MailAccount {
  id: string;
  provider: string;
  email_address: string;
  display_name: string | null;
  status: string;
  filters: { senders?: string[]; subjects?: string[] };
  initial_sync_completed: boolean;
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
}

export interface GuideStep {
  step_number: number;
  title: string;
  description: string;
  action_url?: string | null;
  action_label?: string | null;
  copyable_text?: string | null;
  warning?: string | null;
}

export interface GuideFAQ {
  question: string;
  answer: string;
}

export interface GuideTroubleshooting {
  error_code: string;
  title: string;
  cause: string;
  solution: string;
}

export interface OfficialLink {
  label: string;
  url: string;
}

export interface OAuthClientConfig {
  provider: string;
  configured: boolean;
  client_id: string | null;
  client_secret_hint: string | null;
  tenant: string | null;
  redirect_uri: string;
  scopes: string[];
  title: string;
  steps: string[];
  notes: string[];
  estimated_minutes?: number;
  prerequisites?: string[];
  structured_steps?: GuideStep[];
  faq?: GuideFAQ[];
  troubleshooting?: GuideTroubleshooting[];
  official_links?: OfficialLink[];
  updated_at: string | null;
}

export interface Integration {
  provider: "gmail" | "outlook" | "telegram";
  label: string;
  description: string;
  category: string;
  status: string;
  available: boolean;
  unavailable_reason: string | null;
  phase: string;
  accounts: MailAccount[];
  detail: string | null;
  last_synced_at: string | null;
  oauth_client: OAuthClientConfig | null;
  capabilities: Record<string, unknown>;
}

export interface IntegrationsResponse {
  integrations: Integration[];
  deepseek: {
    provider: string;
    label?: string;
    configured: boolean;
    shared: boolean;
    enabled: boolean;
    model: string | null;
    endpoint_host: string | null;
    endpoint_path: string | null;
    prompt_version?: string;
    json_mode?: boolean;
    max_concurrency?: number;
    note: string;
  };
  web_search?: {
    provider: string;
    label?: string;
    configured: boolean;
    status: string;
    url: string | null;
    mode: string;
    description: string;
    max_concurrency?: number;
    note?: string;
  };
}

export interface ConnectResponse {
  provider: string;
  authorization_url: string;
  redirect_uri: string;
  expires_at: string;
  account_id: string | null;
}

export interface AccountTestResponse {
  ok: boolean;
  status: string;
  message: string;
}

export type SyncJobStatus =
  | "queued"
  | "running"
  | "completed"
  | "partial_failed"
  | "failed"
  | "cancelled";

export interface SyncJob {
  id: string;
  kind: "mail_scan" | "scoring" | "notify" | string;
  status: SyncJobStatus;
  trigger: string;
  accounts_total: number;
  accounts_processed: number;
  messages_scanned: number;
  jobs_found: number;
  jobs_new: number;
  jobs_duplicate: number;
  messages_skipped: number;
  errors_count: number;
  attempt: number;
  cancel_requested: boolean;
  payload: Record<string, unknown>;
  progress: Record<string, number>;
  error_message: string | null;
  requested_at: string;
  started_at: string | null;
  finished_at: string | null;
}

export interface ScoringItemProgress {
  id: string;
  job_id: string;
  job_title: string | null;
  company: string | null;
  status: string;
  attempt: number;
  error_class: string | null;
  error_message: string | null;
  match_id: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface SyncAccountProgress {
  id: string;
  mail_account_id: string;
  email_address: string | null;
  provider: string | null;
  status: "queued" | "running" | "succeeded" | "failed" | "skipped";
  messages_scanned: number;
  jobs_found: number;
  jobs_new: number;
  jobs_duplicate: number;
  messages_skipped: number;
  error_class: string;
  error_message: string | null;
  started_at: string | null;
  finished_at: string | null;
}

export interface SyncJobProgress {
  job: SyncJob;
  accounts: SyncAccountProgress[];
  items: ScoringItemProgress[];
}

export interface SyncRunResponse {
  job_id: string;
  status: SyncJobStatus;
  kind: string;
  accounts_total: number;
  total: number;
  requested_at: string;
  message: string;
}

export interface CVPreview {
  id: string;
  filename: string;
  content_type: string | null;
  size_bytes: number;
  is_active: boolean;
  extraction_status: "ok" | "ocr_required" | "unsupported" | "empty" | "failed" | "pending";
  extraction_warning: string | null;
  has_extracted_text: boolean;
  character_count: number;
  line_count: number;
  text: string;
  truncated: boolean;
}

export interface SyncHistoryEntry {
  id: string;
  source: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  jobs_found: number;
  jobs_new: number;
  matches_created: number;
  error_message: string | null;
  is_mock: boolean;
  account_email: string | null;
}

export interface SyncStatus {
  available: boolean;
  phase: string;
  running: boolean;
  message: string;
  last_sync_at: string | null;
  next_scan_at: string | null;
  last_auto_scan_at: string | null;
  next_auto_scan_at: string | null;
  active_cv: string | null;
  connected_accounts: number;
  active_job_id: string | null;
  active_job_kind: string | null;
  worker_hint: string | null;
  scheduler_enabled: boolean;
  llm_configured: boolean;
}

export interface NotificationEntry {
  id: string;
  channel: string;
  status: string;
  message: string | null;
  error_message: string | null;
  error_class: string | null;
  attempts: number;
  provider_message_id: string | null;
  job_id: string | null;
  job_match_id: string | null;
  job_title: string | null;
  company: string | null;
  score: number | null;
  sent_at: string | null;
  created_at: string;
  is_mock: boolean;
}

export interface TelegramStatus {
  provider: string;
  status: string;
  connected: boolean;
  bot_username: string | null;
  chat_id: string | null;
  token_hint: string | null;
  has_token: boolean;
  last_error: string | null;
  last_error_class: string | null;
  last_checked_at: string | null;
  last_notification_at: string | null;
  linked_at: string | null;
  available: boolean;
  phase: string;
  message: string;
  hint: string;
}

export interface TelegramChatCandidate {
  chat_id: string;
  type: string | null;
  title: string | null;
  username: string | null;
  last_message_at: number | null;
}

export interface TelegramDetectResponse {
  bot_username: string | null;
  candidates: TelegramChatCandidate[];
  suggested_chat_id: string | null;
  requires_manual_choice: boolean;
  message: string;
}

export interface TelegramTestResponse {
  ok: boolean;
  message: string;
  status: string;
  message_id: number | null;
}

export interface NotificationSummary {
  sent: number;
  failed: number;
  skipped: number;
  pending: number;
  threshold: number;
  enabled: boolean;
  telegram_ready: boolean;
  last_sent_at: string | null;
}

export interface NotificationDispatchResponse {
  queued: boolean;
  job_id: string | null;
  total: number;
  message: string;
}

export interface OverviewIntegration {
  provider: string;
  label: string;
  status: string;
  available: boolean;
  account_count: number;
  detail: string | null;
  last_synced_at: string | null;
}

export interface Overview {
  total_jobs: number;
  new_jobs: number;
  high_match_jobs: number;
  saved_jobs: number;
  high_match_threshold: number;
  last_sync_at: string | null;
  last_sync_status: string | null;
  next_scan_at: string | null;
  integrations: OverviewIntegration[];
  has_mock_data: boolean;
  has_active_cv: boolean;
  sync_available: boolean;
  connected_accounts: number;
  active_job_id: string | null;
  active_job_kind: string | null;
  worker_hint: string | null;
  real_jobs: number;
  discovered_today: number;
  analyzed_jobs: number;
  pending_analysis: number;
  failed_analysis: number;
  notified_jobs: number;
  average_score: number | null;
  last_manual_scan_at: string | null;
  last_auto_scan_at: string | null;
  next_auto_scan_at: string | null;
  auto_scan_enabled: boolean;
  scan_interval_hours: number;
  llm: {
    provider?: string;
    configured?: boolean;
    shared?: boolean;
    model?: string | null;
    endpoint_host?: string | null;
    endpoint_path?: string | null;
    prompt_version?: string;
    max_concurrency?: number;
    enabled?: boolean;
    label?: string;
    note?: string;
  };
  notifications: NotificationSummary;
}

export interface Invitation {
  id: string;
  email: string;
  created_at: string;
  expires_at: string;
  used_at: string | null;
  status: "pending" | "used" | "expired";
  invite_url: string | null;
}

export interface InvitationPublic {
  email: string;
  expires_at: string;
  is_valid: boolean;
  invited_by: string | null;
  message: string | null;
}

export interface SiteVerificationItem {
  site: string;
  status: "ok" | "error" | string;
  status_code: number | null;
  jobs_found: number;
  message: string | null;
}

export interface VerifySitesResponse {
  success: boolean;
  total_checked: number;
  active_sites: number;
  results: SiteVerificationItem[];
  message: string;
}

