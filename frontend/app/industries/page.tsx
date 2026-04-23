import { api } from "@/lib/api";
import Link from "next/link";
import MarketingScoreBar from "@/components/MarketingScoreBar";

export const revalidate = 3600;

const industryEmoji: Record<string, string> = {
  beauty: "💄", food: "🍱", fashion: "👗", electronics: "💻",
  sports: "⚽", travel: "✈️", finance: "💰", health: "💪",
  entertainment: "🎬", home: "🏠",
};

const rankBadge = (i: number) => {
  if (i === 0) return "bg-yellow-400 text-yellow-900";
  if (i === 1) return "bg-gray-300 text-gray-700";
  if (i === 2) return "bg-orange-300 text-orange-900";
  return "bg-blue-50 text-blue-600";
};

export default async function IndustriesPage() {
  const industries = await api.getIndustries();

  const industryData = await Promise.allSettled(
    industries.map((ind) => api.getIndustryRankings(ind.code).catch(() => null))
  );

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">B2C 산업군별 셀럽 마케팅 분석</h1>
        <p className="text-gray-500 text-sm">
          10개 B2C 산업군별 마케팅 적합도 TOP 5 셀럽 — 매주 업데이트
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
        {industries.map((ind, idx) => {
          const result = industryData[idx];
          const rankingData = result.status === "fulfilled" && result.value ? result.value : null;

          return (
            <div key={ind.code} className="bg-white rounded-xl border border-gray-200 overflow-hidden">
              {/* 산업군 헤더 */}
              <div className="flex items-center justify-between px-5 py-4 bg-gray-50 border-b border-gray-100">
                <div className="flex items-center gap-3">
                  <span className="text-2xl">{industryEmoji[ind.code] || "🏷️"}</span>
                  <h2 className="text-base font-bold text-gray-800">{ind.label}</h2>
                </div>
                <Link
                  href={`/industries/${ind.code}`}
                  className="text-xs text-blue-500 hover:text-blue-700 hover:underline"
                >
                  전체보기 →
                </Link>
              </div>

              {rankingData ? (
                <div className="divide-y divide-gray-50">
                  {rankingData.celebrities.slice(0, 5).map((celeb, i) => (
                    <Link
                      key={celeb.celebrity_id}
                      href={`/celebrities/${celeb.celebrity_id}`}
                      className="flex items-center gap-3 px-5 py-3 hover:bg-blue-50 transition-colors"
                    >
                      {/* 순위 배지 */}
                      <span className={`text-xs font-bold rounded-full w-6 h-6 flex items-center justify-center flex-shrink-0 ${rankBadge(i)}`}>
                        {i + 1}
                      </span>

                      {/* 이름 + 태그 */}
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-1.5 mb-1">
                          <span className="font-semibold text-sm text-gray-900 truncate">{celeb.name}</span>
                          {celeb.category && (
                            <span className="text-xs text-gray-400 flex-shrink-0">{celeb.category}</span>
                          )}
                        </div>
                        {celeb.image_tags.length > 0 && (
                          <div className="flex gap-1 flex-wrap">
                            {celeb.image_tags.slice(0, 3).map((tag) => (
                              <span key={tag} className="text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">
                                {tag}
                              </span>
                            ))}
                          </div>
                        )}
                      </div>

                      {/* 점수 바 */}
                      <div className="w-24 flex-shrink-0">
                        <MarketingScoreBar score={celeb.fit_score} />
                      </div>
                    </Link>
                  ))}
                </div>
              ) : (
                <div className="px-5 py-8 text-center text-sm text-gray-400">
                  데이터 준비 중 — 관리자 업데이트 후 표시됩니다
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
