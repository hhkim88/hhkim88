const API_BASE = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export interface RankingItem {
  rank: number;
  celebrity_id: number;
  name: string;
  category: string | null;
  profile_image_url: string | null;
  marketing_score: number;
  mention_total: number;
  engagement_rate: number;
  sentiment_avg: number;
  image_tags: string[];
  personality_summary: string | null;
}

export interface RankingResponse {
  week_start: string;
  rankings: RankingItem[];
}

export interface IndustryFitItem {
  industry: string;
  label: string;
  fit_score: number;
  rank: number;
}

export interface WeeklyHistory {
  week_start: string;
  rank: number | null;
  marketing_score: number;
}

export interface CelebrityDetail {
  id: number;
  name: string;
  name_en: string | null;
  category: string | null;
  profile_image_url: string | null;
  instagram_handle: string | null;
  current_rank: number | null;
  marketing_score: number;
  mention_total: number;
  engagement_rate: number;
  sentiment_avg: number;
  image_tags: string[];
  personality_summary: string | null;
  brand_fit_description: string | null;
  industry_fit: IndustryFitItem[];
  weekly_history: WeeklyHistory[];
}

export interface IndustryInfo {
  code: string;
  label: string;
}

export interface IndustryCelebrityItem {
  rank: number;
  celebrity_id: number;
  name: string;
  category: string | null;
  profile_image_url: string | null;
  fit_score: number;
  image_tags: string[];
}

export interface IndustryRankingResponse {
  industry: string;
  label: string;
  week_start: string;
  celebrities: IndustryCelebrityItem[];
}

async function fetcher<T>(path: string): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    next: { revalidate: 3600 },
  });
  if (!res.ok) {
    throw new Error(`API error ${res.status}: ${path}`);
  }
  return res.json();
}

export const api = {
  getCurrentRankings: () => fetcher<RankingResponse>("/api/v1/rankings/current"),
  getRankingsByWeek: (weekStart: string) =>
    fetcher<RankingResponse>(`/api/v1/rankings/${weekStart}`),
  getCelebrity: (id: number) => fetcher<CelebrityDetail>(`/api/v1/celebrities/${id}`),
  getIndustries: () => fetcher<IndustryInfo[]>("/api/v1/industries"),
  getIndustryRankings: (industry: string, weekStart?: string) => {
    const qs = weekStart ? `?week_start=${weekStart}` : "";
    return fetcher<IndustryRankingResponse>(`/api/v1/industries/${industry}/rankings${qs}`);
  },
};
