"use client";

interface IndustryInfo {
  code: string;
  label: string;
}

interface Props {
  industries: IndustryInfo[];
  selected: string | null;
  onSelect: (code: string | null) => void;
}

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

export default function IndustryFilter({ industries, selected, onSelect }: Props) {
  return (
    <div className="flex flex-wrap gap-2">
      <button
        onClick={() => onSelect(null)}
        className={`px-4 py-2 rounded-full text-sm font-medium transition-colors ${
          selected === null
            ? "bg-blue-600 text-white"
            : "bg-white text-gray-600 border border-gray-200 hover:border-blue-300"
        }`}
      >
        전체
      </button>
      {industries.map((ind) => (
        <button
          key={ind.code}
          onClick={() => onSelect(selected === ind.code ? null : ind.code)}
          className={`px-4 py-2 rounded-full text-sm font-medium transition-colors flex items-center gap-1 ${
            selected === ind.code
              ? "bg-blue-600 text-white"
              : "bg-white text-gray-600 border border-gray-200 hover:border-blue-300"
          }`}
        >
          <span>{industryEmoji[ind.code] || "🏷️"}</span>
          {ind.label}
        </button>
      ))}
    </div>
  );
}
