export interface Dossier {
  id: string;
  title: string;
  company: string;
  location: string;
  salary: string;
  score: string;
  ref: string;
  freshness: string;
  analysis: string;
  skills: string[];
  tier: string;
  source: string;
  telegram: string;
  cityKey?: string;
  cityName?: string;
  application_url?: string;
}

export interface CityHub {
  name: string;
  lat: number;
  lng: number;
  count: number;
  dossiers: Dossier[];
}

export type TabId =
  | "tab-globe"
  | "tab-jobs"
  | "tab-integrations"
  | "tab-cv"
  | "tab-sync";

export interface ToastItem {
  id: string;
  message: string;
}
