import { api } from "@/lib/api";
import WeeklyTrendChart from "@/components/WeeklyTrendChart";
import MarketingScoreBar from "@/components/MarketingScoreBar";
import { notFound } from "next/navigation";

export const revalidate = 1800;

interface Props {
  params: { id: string };
}

const sentimentLabel = (v: number) => {
  if (v >= 0.6) return { text: "매우 긍정적", color: "text-green-600" };
  if (v >= 0.4) return { text: "긍정적", color: "text-green-500" };
  if (v >= 0.2) return { text: "보통", color: "text-yellow-500" };
  return { text: "혼재", color: "text-red-500" };
};

export default async function CelebrityPage({ params }: Props) {
  const id = parseInt(params.id, 10);
  if (isNaN(id)) notFound();

  let celeb;
  try {
    celeb = await api.getCelebrity(id);
  } catch {
    notFound();
  }

  const sl = sentimentLabel(celeb.sentiment_avg);
  const topIndustries = [...celeb.industry_fit].sort((a, b) => b.fit_score - a.fit_score).slice(0, 3);

  return (
    <div className="max-w-3xl mx-auto">
      {/* 상단: 이름 + 기본 정보 */}
      <div className="bg-white rounded-xl border border-gray-200 p-6 mb-5">
        <div className="flex items-start justify-between mb-4">
          <div>
            <div className="flex items-center gap-3 mb-1">
              {celeb.current_rank && (
                <span className="bg-blue-600 text-white text-lg font-bold rounded-full w-10 h-10 flex items-center justify-center">
                  {celeb.current_rank}
                </span>
              )}
              <h1 className="text-2xl font-bold text-gray-900">{celeb.name}</h1>
              {celeb.name_en && <span className="text-gray-400 text-sm">{celeb.name_en}</span>}
            </div>
            {celeb.category && (
              <span className="text-sm bg-gray-100 text-gray-500 px-3 py-1 rounded-full">
                {celeb.category}
              </span>
            )}
          </div>
          {celeb.instagram_handle && (
            <a
              href={`https://instagram.com/${celeb.instagram_handle}`}
              target="_blank"
              rel="noopener noreferrer"
              className="text-sm text-pink-500 hover:text-pink-700 border border-pink-200 px-3 py-1 rounded-full"
            >
              @{celeb.instagram_handle}
            </a>
          )}
        </div>

        {/* 이미지 태그 */}
        {celeb.image_tags.length > 0 && (
          <div className="flex flex-wrap gap-2 mb-4">
            {celeb.image_tags.map((tag) => (
              <span key={tag} className="bg-blue-50 text-blue-600 border border-blue-100 px-3 py-1 rounded-full text-sm font-medium">
                {tag}
              </span>
            ))}
          </div>
        )}

        {celeb.personality_summary && (
          <p className="text-gray-600 text-sm mb-4 leading-relaxed">{celeb.personality_summary}</p>
        )}

        {/* 핵심 지표 */}
        <div className="grid grid-cols-3 gap-4 py-4 border-t border-gray-100">
          <div className="text-center">
            <div className="text-2xl font-bold text-blue-600">{celeb.marketing_score.toFixed(1)}</div>
            <div className="text-xs text-gray-400 mt-1">마케팅 점수</div>
          </div>
          <div className="text-center">
            <div className="text-2xl font-bold text-gray-700">{celeb.mention_total.toLocaleString()}</div>
            <div className="text-xs text-gray-400 mt-1">주간 언급</div>
          </div>
          <div className="text-center">
            <div className={`text-2xl font-bold ${sl.color}`}>{sl.text}</div>
            <div className="text-xs text-gray-400 mt-1">SNS 감성</div>
          </div>
        </div>

        <div className="pt-3 border-t border-gray-100">
          <div className="flex items-center justify-between text-sm text-gray-500 mb-1">
            <span>마케팅 종합 점수</span>
          </div>
          <MarketingScoreBar score={celeb.marketing_score} />
        </div>
      </div>

      {/* 주간 추이 차트 */}
      {celeb.weekly_history.length > 0 && (
        <div className="mb-5">
          <WeeklyTrendChart history={celeb.weekly_history} />
        </div>
      )}

      {/* B2C 산업군 매칭 */}
      {celeb.industry_fit.length > 0 && (
        <div className="bg-white rounded-xl border border-gray-200 p-5 mb-5">
          <h3 className="font-semibold text-gray-800 mb-4">B2C 산업군 적합도</h3>
          <div className="space-y-3">
            {[...celeb.industry_fit]
              .sort((a, b) => b.fit_score - a.fit_score)
              .map((item) => (
                <div key={item.industry}>
                  <div className="flex justify-between text-sm mb-1">
                    <span className="text-gray-700 font-medium">{item.label}</span>
                    <span className="text-gray-400">#{item.rank} · {item.fit_score.toFixed(0)}점</span>
                  </div>
                  <MarketingScoreBar score={item.fit_score} />
                </div>
              ))}
          </div>
        </div>
      )}

      {/* Claude 브랜드 분석 */}
      {celeb.brand_fit_description && (
        <div className="bg-gradient-to-br from-blue-50 to-indigo-50 rounded-xl border border-blue-100 p-5 mb-5">
          <div className="flex items-center gap-2 mb-3">
            <span className="text-blue-500 font-semibold text-sm">AI 마케팅 인사이트</span>
          </div>
          <p className="text-gray-700 text-sm leading-relaxed">{celeb.brand_fit_description}</p>
          <div className="mt-3">
            <span className="text-xs text-gray-500">추천 산업군: </span>
            {topIndustries.map((ind) => (
              <span key={ind.industry} className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full ml-1">
                {ind.label}
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="text-center">
        <a href="/" className="text-sm text-blue-600 hover:underline">← 전체 랭킹으로 돌아가기</a>
      </div>
    </div>
  );
}
