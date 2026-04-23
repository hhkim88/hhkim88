import Link from "next/link";
import MarketingScoreBar from "./MarketingScoreBar";

interface Props {
  rank: number;
  celebrity_id: number;
  name: string;
  category: string | null;
  marketing_score: number;
  mention_total: number;
  sentiment_avg: number;
  image_tags: string[];
  personality_summary?: string | null;
}

const rankColor: Record<number, string> = {
  1: "bg-yellow-400 text-yellow-900",
  2: "bg-gray-300 text-gray-700",
  3: "bg-orange-400 text-orange-900",
};

export default function CelebrityCard(props: Props) {
  const {
    rank, celebrity_id, name, category,
    marketing_score, mention_total, sentiment_avg,
    image_tags, personality_summary,
  } = props;

  const badgeClass = rankColor[rank] || "bg-blue-100 text-blue-700";

  return (
    <Link href={`/celebrities/${celebrity_id}`}>
      <div className="bg-white rounded-xl border border-gray-200 p-5 hover:shadow-md hover:border-blue-300 transition-all cursor-pointer">
        <div className="flex items-start gap-4">
          {/* 순위 배지 */}
          <span className={`text-lg font-bold rounded-full w-10 h-10 flex items-center justify-center flex-shrink-0 ${badgeClass}`}>
            {rank}
          </span>

          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <h3 className="font-bold text-lg text-gray-900">{name}</h3>
              {category && (
                <span className="text-xs bg-gray-100 text-gray-500 px-2 py-0.5 rounded-full">
                  {category}
                </span>
              )}
            </div>

            {/* 이미지 태그 */}
            {image_tags.length > 0 && (
              <div className="flex flex-wrap gap-1 mb-2">
                {image_tags.slice(0, 5).map((tag) => (
                  <span key={tag} className="text-xs bg-blue-50 text-blue-600 border border-blue-100 px-2 py-0.5 rounded-full">
                    {tag}
                  </span>
                ))}
              </div>
            )}

            {personality_summary && (
              <p className="text-sm text-gray-500 mb-3 line-clamp-1">{personality_summary}</p>
            )}

            {/* 마케팅 점수 바 */}
            <MarketingScoreBar score={marketing_score} />

            {/* 통계 */}
            <div className="flex gap-4 mt-2 text-xs text-gray-400">
              <span>언급 {mention_total.toLocaleString()}건</span>
              <span>감성 {(sentiment_avg * 100).toFixed(0)}%</span>
            </div>
          </div>
        </div>
      </div>
    </Link>
  );
}
