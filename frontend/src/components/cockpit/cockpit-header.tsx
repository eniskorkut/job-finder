"use client";

import type { TabId } from "./types";

interface CockpitHeaderProps {
  activeTab: TabId;
  onSelectTab: (tab: TabId) => void;
  onQuickSync: () => void;
  totalJobCount: number;
}

export function CockpitHeader({
  activeTab,
  onSelectTab,
  onQuickSync,
  totalJobCount,
}: CockpitHeaderProps) {
  const tabs: { id: TabId; label: string }[] = [
    { id: "tab-globe", label: "KÜRESEL RADAR" },
    { id: "tab-jobs", label: `İLAN HAVUZU & DOSYALAR (${totalJobCount})` },
    { id: "tab-integrations", label: "ENTEGRASYONLAR & BOT" },
    { id: "tab-cv", label: "CV & PROFİL" },
    { id: "tab-sync", label: "TARAMA LOGLARI" },
  ];

  return (
    <header className="sticky top-0 z-50 bg-[#020203]/95 backdrop-blur-2xl border-b border-white/15">
      {/* Row 1: Brand & Actions */}
      <div className="max-w-7xl mx-auto px-3.5 sm:px-6 md:px-8 py-2.5 md:py-3 flex items-center justify-between gap-3 border-b border-white/10">
        <div className="flex items-center gap-2.5 sm:gap-3.5">
          <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl sm:rounded-2xl bg-white text-black flex items-center justify-center font-mono font-bold text-xs sm:text-sm shadow-[0_0_20px_rgba(255,255,255,0.4)] flex-shrink-0">
            05
          </div>
          <div>
            <div className="flex items-center gap-1.5 sm:gap-2">
              <span className="text-sm sm:text-base font-bold text-white tracking-wider font-mono">
                JOB HUNTER
              </span>
              <span className="px-1.5 sm:px-2 py-0.5 rounded text-[9px] sm:text-[10px] font-mono bg-white/10 text-white border border-white/20 whitespace-nowrap">
                YÖNETİCİ KONSOLU
              </span>
            </div>
            <p className="text-[10px] sm:text-xs text-white/50 font-mono hidden sm:block">
              Kariyer İstihbarat Platformu
            </p>
          </div>
        </div>

        {/* Live Actions & Clearance */}
        <div className="flex items-center gap-2 sm:gap-3 font-mono">
          <button
            type="button"
            onClick={onQuickSync}
            className="silver-btn lux-press px-2.5 sm:px-3.5 py-1.5 rounded-xl text-[11px] sm:text-xs font-mono uppercase tracking-wider flex items-center gap-1.5 sm:gap-2 flex-shrink-0 cursor-pointer"
          >
            <svg
              className="w-3.5 h-3.5"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2.2"
            >
              <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
            </svg>
            <span>ŞİMDİ TARA</span>
          </button>

          <div className="flex items-center gap-2 pl-2 border-l border-white/10">
            <div className="text-right hidden sm:block">
              <div className="text-xs font-bold text-white">ENIS KORKUT</div>
              <div className="text-[10px] text-emerald-400 font-mono">
                AKTİF PROFİL
              </div>
            </div>
            <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-white/10 border border-white/20 flex items-center justify-center font-bold text-xs text-white flex-shrink-0">
              EK
            </div>
          </div>
        </div>
      </div>

      {/* Row 2: Dedicated Navigation Row with Smooth Horizontal Swipe on Mobile */}
      <div className="max-w-7xl mx-auto px-2.5 sm:px-6 md:px-8 py-1.5 sm:py-2">
        <nav className="flex items-center gap-1.5 p-1 rounded-2xl bg-white/[0.04] border border-white/10 text-xs font-mono overflow-x-auto no-scrollbar flex-nowrap w-full sm:w-auto touch-pan-x">
          {tabs.map((tab) => {
            const isActive = activeTab === tab.id;
            return (
              <button
                key={tab.id}
                type="button"
                onClick={() => onSelectTab(tab.id)}
                className={`nav-tab-btn lux-press px-3.5 sm:px-4 py-1.5 sm:py-2 rounded-xl whitespace-nowrap flex-shrink-0 cursor-pointer transition-all ${
                  isActive
                    ? "bg-white text-black font-bold border border-white shadow-[0_0_15px_rgba(255,255,255,0.3)]"
                    : "text-white/70 hover:text-white"
                }`}
              >
                {tab.label}
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
