"use client";

interface Props {
  score: number;
  max?: number;
}

export default function MarketingScoreBar({ score, max = 100 }: Props) {
  const pct = Math.min(100, (score / max) * 100);
  const color =
    pct >= 70 ? "bg-green-500" : pct >= 40 ? "bg-blue-500" : "bg-gray-400";

  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 bg-gray-100 rounded-full h-2 overflow-hidden">
        <div
          className={`h-2 rounded-full transition-all ${color}`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-sm font-semibold text-gray-700 w-10 text-right">
        {score.toFixed(1)}
      </span>
    </div>
  );
}
