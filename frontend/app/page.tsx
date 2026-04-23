import { api } from "@/lib/api";
import CelebrityCard from "@/components/CelebrityCard";

export const revalidate = 3600;

function formatWeek(dateStr: string) {
  const d = new Date(dateStr);
  return `${d.getFullYear()}년 ${d.getMonth() + 1}월 ${d.getDate()}일 주간`;
}

export default async function HomePage() {
  let data;
  try {
    data = await api.getCurrentRankings();
  } catch {
    return (
      <div className="text-center py-20 text-gray-500">
        <p className="text-xl font-semibold mb-2">랭킹 데이터 준비 중</p>
        <p className="text-sm">관리자: POST /api/v1/rankings/admin/trigger-update 실행 후 새로고침</p>
      </div>
    );
  }

  return (
    <div>
      {/* 헤더 섹션 */}
      <div className="mb-8">
        <div className="flex items-center justify-between mb-2">
          <h1 className="text-2xl font-bold text-gray-900">
            주간 셀럽 마케팅 효과 TOP 10
          </h1>
          <span className="text-sm text-gray-400 bg-white border border-gray-200 px-3 py-1 rounded-full">
            {formatWeek(data.week_start)} 기준
          </span>
        </div>
        <p className="text-gray-500 text-sm">
          한국 SNS(네이버 블로그/카페, 인스타그램, 유튜브) 언급 데이터 + Claude AI 분석 기반
        </p>
      </div>

      {/* 점수 설명 배너 */}
      <div className="bg-blue-50 border border-blue-100 rounded-xl p-4 mb-6 flex flex-wrap gap-6 text-sm text-blue-700">
        <span><strong>마케팅 점수</strong> = 언급량 30% + 참여율 35% + 긍정감성 20% + 플랫폼다양성 15%</span>
        <a href="/industries" className="text-blue-600 underline font-medium hover:text-blue-800">
          산업군별 분석 보기 →
        </a>
      </div>

      {/* TOP 10 리스트 */}
      <div className="grid gap-3">
        {data.rankings.map((item) => (
          <CelebrityCard key={item.celebrity_id} {...item} />
        ))}
      </div>
    </div>
  );
}
