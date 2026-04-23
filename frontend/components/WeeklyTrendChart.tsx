"use client";

import {
  LineChart, Line, XAxis, YAxis, CartesianGrid,
  Tooltip, ResponsiveContainer, ReferenceLine,
} from "recharts";

interface WeeklyHistory {
  week_start: string;
  rank: number | null;
  marketing_score: number;
}

interface Props {
  history: WeeklyHistory[];
}

export default function WeeklyTrendChart({ history }: Props) {
  const data = history.map((h) => ({
    week: h.week_start.slice(5),   // "MM-DD" 형식
    score: Number(h.marketing_score.toFixed(1)),
    rank: h.rank,
  }));

  return (
    <div className="bg-white rounded-xl border border-gray-200 p-5">
      <h3 className="font-semibold text-gray-800 mb-4">주간 마케팅 점수 추이</h3>
      <ResponsiveContainer width="100%" height={200}>
        <LineChart data={data} margin={{ top: 5, right: 10, left: -20, bottom: 5 }}>
          <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
          <XAxis dataKey="week" tick={{ fontSize: 11, fill: "#9ca3af" }} />
          <YAxis domain={[0, 100]} tick={{ fontSize: 11, fill: "#9ca3af" }} />
          <Tooltip
            contentStyle={{ fontSize: 12, borderRadius: 8 }}
            formatter={(v: number) => [`${v}점`, "마케팅 점수"]}
            labelFormatter={(l) => `${l} 주`}
          />
          <Line
            type="monotone"
            dataKey="score"
            stroke="#3b82f6"
            strokeWidth={2.5}
            dot={{ fill: "#3b82f6", r: 4 }}
            activeDot={{ r: 6 }}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}
