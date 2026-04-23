import { api } from "@/lib/api";
import Link from "next/link";

export const revalidate = 3600;

const industryEmoji: Record<string, string> = {
  beauty: "💄",
  food: "🍱",
  fashion: "👗",
  electronics: "💻",
  sports: "⚽",
  travel: "✈️",
  finance: "💰",
  health: "💪",
  entertainment: "🎬",
  home: "🏠",
};

export default async function IndustriesPage() {
  const industries = await api.getIndustries();

  const industryData = await Promise.allSettled(
    industries.map((ind) =>
      api.getIndustryRankings(ind.code).catch(() => null)
    )
  );

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-gray-900 mb-2">산업군별 셀럽 마케팅 분석</h1>
        <p className="text-gray-500 text-sm">
          B2C 10개 산업군별로 마케팅 효과가 높은 셀럽을 확인하세요
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
        {industries.map((ind, idx) => {
          const result = industryData[idx];
          const rankingData =
            result.status === "fulfilled" && result.value ? result.value : null;

          return (
            <div key={ind.code} className="bg-white rounded-xl border border-gray-200 p-5">
              {/* 산업군 헤더 */}
              <div className="flex items-center gap-3 mb-4">
                <span className="text-3xl">{industryEmoji[ind.code] || "🏷️"}</span>
                <h2 className="text-lg font-bold text-gray-800">{ind.label}</h2>
              </div>

              {rankingData ? (
                <ol className="space-y-2">
                  {rankingData.celebrities.slice(0, 5).map((celeb, i) => (
                    <li key={celeb.celebrity_id}>
                      <Link
                        href={`/celebrities/${celeb.celebrity_id}`}
                        className="flex items-center gap-3 p-2 rounded-lg hover:bg-gray-50 transition-colors"
                      >
                        <span className="text-sm font-bold text-gray-400 w-5 text-center">
                          {i + 1}
                        </span>
                        <div className="flex-1">
                          <span className="font-semibold text-gray-900">{celeb.name}</span>
                          {celeb.category && (
                            <span className="ml-2 text-xs text-gray-400">{celeb.category}</span>
                          )}
                          {celeb.image_tags.slice(0, 2).map((tag) => (
                            <span key={tag} className="ml-1 text-xs bg-blue-50 text-blue-600 px-1.5 py-0.5 rounded-full">
                              {tag}
                            </span>
                          ))}
                        </div>
                        <span className="text-sm font-semibold text-blue-600">
                          {celeb.fit_score.toFixed(0)}점
                        </span>
                      </Link>
                    </li>
                  ))}
                </ol>
              ) : (
                <p className="text-sm text-gray-400 text-center py-4">데이터 준비 중</p>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}
