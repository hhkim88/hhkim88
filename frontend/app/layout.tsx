import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "셀럽 마케팅 인사이트",
  description: "한국 SNS 셀럽 마케팅 효과 분석 서비스 — 매주 업데이트",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ko">
      <body className="min-h-screen">
        <header className="bg-white border-b border-gray-200 sticky top-0 z-10 shadow-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 py-4 flex items-center justify-between">
            <a href="/" className="flex items-center gap-2">
              <span className="text-2xl font-bold text-blue-600">CelebRank</span>
              <span className="text-xs bg-blue-100 text-blue-700 px-2 py-0.5 rounded-full font-medium">
                마케팅 인사이트
              </span>
            </a>
            <nav className="flex gap-6 text-sm font-medium text-gray-600">
              <a href="/" className="hover:text-blue-600 transition-colors">주간 랭킹</a>
              <a href="/industries" className="hover:text-blue-600 transition-colors">산업별 분석</a>
            </nav>
          </div>
        </header>
        <main className="max-w-7xl mx-auto px-4 sm:px-6 py-8">{children}</main>
        <footer className="mt-16 border-t border-gray-200 bg-white py-6 text-center text-sm text-gray-400">
          © 2025 CelebRank · 매주 월요일 업데이트 · 마케팅팀 전용
        </footer>
      </body>
    </html>
  );
}
