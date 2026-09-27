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

export interface JobMatch {
  id: string;
  score: number | null;
  rationale: string | null;
  matched_skills: string[];
  missing_skills: string[];
  model: string | null;
  status: "new" | "viewed" | "saved" | "dismissed" | "notified";
  is_mock: boolean;
  notified_at: string | null;
  updated_at: string;
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
  match: JobMatch | null;
}

export interface JobDetail extends Job {
  description: string | null;
  mail_account_email: string | null;
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
}

export interface JobFilterOptions {
  sources: string[];
  locations: string[];
  companies: string[];
  work_modes: string[];
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
  last_synced_at: string | null;
  last_error: string | null;
  created_at: string;
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
}

export interface IntegrationsResponse {
  integrations: Integration[];
  deepseek: {
    provider: string;
    label: string;
    model: string;
    base_url: string;
    shared: boolean;
    enabled: boolean;
    configured: boolean;
    phase: string;
    note: string;
  };
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
  active_cv: string | null;
  connected_accounts: number;
}

export interface NotificationEntry {
  id: string;
  channel: string;
  status: string;
  message: string | null;
  error_message: string | null;
  job_id: string | null;
  job_match_id: string | null;
  job_title: string | null;
  company: string | null;
  sent_at: string | null;
  created_at: string;
  is_mock: boolean;
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
