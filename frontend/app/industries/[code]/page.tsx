import { api } from "@/lib/api";
import Link from "next/link";
import MarketingScoreBar from "@/components/MarketingScoreBar";
import { notFound } from "next/navigation";

export const revalidate = 3600;

interface Props {
  params: { code: string };
}

const industryEmoji: Record<string, string> = {
  beauty: "💄", food: "🍱", fashion: "👗", electronics: "💻",
  sports: "⚽", travel: "✈️", finance: "💰", health: "💪",
  entertainment: "🎬", home: "🏠",
};

const rankBadge = (i: number) => {
  const styles = [
    "bg-yellow-400 text-yellow-900 text-base",
    "bg-gray-300 text-gray-700",
    "bg-orange-300 text-orange-900",
    "bg-blue-100 text-blue-700",
    "bg-blue-50 text-blue-500",
  ];
  return styles[i] ?? "bg-gray-100 text-gray-500";
};

export default async function IndustryDetailPage({ params }: Props) {
  let data;
  try {
    data = await api.getIndustryRankings(params.code);
  } catch {
    notFound();
  }

  const emoji = industryEmoji[params.code] || "🏷️";

  return (
    <div className="max-w-2xl mx-auto">
      {/* 헤더 */}
      <div className="mb-6">
        <div className="flex items-center gap-3 mb-2">
          <span className="text-4xl">{emoji}</span>
          <div>
            <h1 className="text-2xl font-bold text-gray-900">{data.label}</h1>
            <p className="text-sm text-gray-500">{data.week_start} 주간 기준 · 마케팅 적합도 순위</p>
          </div>
        </div>
      </div>

      {/* TOP 5 상세 카드 */}
      <div className="space-y-3 mb-8">
        {data.celebrities.slice(0, 5).map((celeb, i) => (
          <Link
            key={celeb.celebrity_id}
            href={`/celebrities/${celeb.celebrity_id}`}
            className="block bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md hover:border-blue-200 transition-all"
          >
            <div className="flex items-start gap-4">
              <span className={`text-lg font-bold rounded-full w-10 h-10 flex items-center justify-center flex-shrink-0 ${rankBadge(i)}`}>
                {i + 1}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2 mb-2">
                  <span className="font-bold text-lg text-gray-900">{celeb.name}</span>
                  {celeb.category && (
                    <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                      {celeb.category}
                    </span>
                  )}
                </div>
                {celeb.image_tags.length > 0 && (
                  <div className="flex flex-wrap gap-1 mb-3">
                    {celeb.image_tags.map((tag) => (
                      <span key={tag} className="text-xs bg-blue-50 text-blue-600 border border-blue-100 px-2 py-0.5 rounded-full">
                        {tag}
                      </span>
                    ))}
                  </div>
                )}
                <div className="flex items-center gap-3">
                  <span className="text-sm text-gray-500 w-24">산업 적합도</span>
                  <div className="flex-1">
                    <MarketingScoreBar score={celeb.fit_score} />
                  </div>
                </div>
              </div>
            </div>
          </Link>
        ))}
      </div>

      {/* 나머지 6-10위 */}
      {data.celebrities.length > 5 && (
        <div className="bg-white rounded-xl border border-gray-200 overflow-hidden mb-6">
          <div className="px-5 py-3 bg-gray-50 border-b border-gray-100">
            <span className="text-sm font-semibold text-gray-600">6위 ~ {Math.min(data.celebrities.length, 10)}위</span>
          </div>
          <div className="divide-y divide-gray-50">
            {data.celebrities.slice(5, 10).map((celeb, i) => (
              <Link
                key={celeb.celebrity_id}
                href={`/celebrities/${celeb.celebrity_id}`}
                className="flex items-center gap-3 px-5 py-3 hover:bg-gray-50 transition-colors"
              >
                <span className="text-sm font-bold text-gray-400 w-5 text-center">{i + 6}</span>
                <div className="flex-1">
                  <span className="font-semibold text-sm text-gray-800">{celeb.name}</span>
                  {celeb.category && <span className="ml-2 text-xs text-gray-400">{celeb.category}</span>}
                </div>
                <span className="text-sm text-blue-600 font-semibold">{celeb.fit_score.toFixed(0)}점</span>
              </Link>
            ))}
          </div>
        </div>
      )}

      <div className="text-center">
        <a href="/industries" className="text-sm text-blue-600 hover:underline">← 전체 산업군 보기</a>
      </div>
    </div>
  );
}
