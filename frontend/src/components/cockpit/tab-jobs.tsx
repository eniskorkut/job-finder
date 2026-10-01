"use client";

import { useMemo, useState } from "react";
import type { CityHub, Dossier } from "./types";

interface TabJobsProps {
  cities: Record<string, CityHub>;
  allDossiers: Dossier[];
  selectedSkill: string;
  onSelectSkill: (skill: string) => void;
  onOpenModal: (dossier: Dossier) => void;
}

export function TabJobs({
  cities,
  allDossiers,
  selectedSkill,
  onSelectSkill,
  onOpenModal,
}: TabJobsProps) {
  const [searchQuery, setSearchQuery] = useState("");
  const [selectedCityFilter, setSelectedCityFilter] = useState("all");
  const [sortBy, setSortBy] = useState<"score" | "recent">("score");

  // Calculate top skills across all dossiers
  const skillCounts = useMemo(() => {
    const map = new Map<string, number>();
    allDossiers.forEach((d) => {
      d.skills.forEach((s) => {
        map.set(s, (map.get(s) || 0) + 1);
      });
    });
    return Array.from(map.entries())
      .sort((a, b) => b[1] - a[1])
      .slice(0, 16);
  }, [allDossiers]);

  // Filtered and sorted dossiers
  const filteredJobs = useMemo(() => {
    let result = [...allDossiers];

    // City Filter
    if (selectedCityFilter !== "all") {
      result = result.filter((j) => j.cityKey === selectedCityFilter);
    }

    // Skill Filter
    if (selectedSkill && selectedSkill !== "all") {
      const target = selectedSkill.toLowerCase();
      result = result.filter((j) =>
        j.skills.some((s) => s.toLowerCase() === target)
      );
    }

    // Search Query
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      result = result.filter(
        (j) =>
          j.title.toLowerCase().includes(q) ||
          j.company.toLowerCase().includes(q) ||
          (j.cityName && j.cityName.toLowerCase().includes(q)) ||
          j.skills.some((s) => s.toLowerCase().includes(q))
      );
    }

    // Sort
    if (sortBy === "score") {
      result.sort((a, b) => parseFloat(b.score) - parseFloat(a.score));
    }

    return result;
  }, [allDossiers, selectedCityFilter, selectedSkill, searchQuery, sortBy]);

  return (
    <div id="tab-jobs" className="tab-pane space-y-4 sm:space-y-6">
      <div className="carbon-card rounded-2xl sm:rounded-3xl p-4 sm:p-6 md:p-8 space-y-5 sm:space-y-6">
        {/* Header & Search Toolbar */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-3 sm:gap-4 pb-4 sm:pb-6 border-b border-white/15">
          <div>
            <h2 className="text-lg sm:text-xl font-bold font-mono text-white tracking-wide">
              KÜRESEL İLAN HAVUZU &amp; ADAY DOSYALARI
            </h2>
            <p className="text-xs text-white/50 font-mono mt-0.5">
              Taranan tüm uluslararası açık pozisyonlar, yetenek haritaları ve AI değerlendirmeleri
            </p>
          </div>

          {/* Search Input */}
          <div className="relative w-full md:w-80">
            <svg
              className="absolute left-3.5 top-1/2 -translate-y-1/2 w-4 h-4 text-white/40"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <circle cx="11" cy="11" r="8" />
              <path d="m21 21-4.35-4.35" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Şirket, unvan veya yetenek ara..."
              className="w-full bg-[#040405] border border-white/20 rounded-xl pl-10 pr-4 py-2.5 text-xs font-mono text-white placeholder-white/40 focus:outline-none focus:border-white transition-all"
            />
          </div>
        </div>

        {/* Skills Radar Swipeable Filter Bar */}
        <div className="p-3 sm:p-4 rounded-2xl bg-[#040405] border border-white/15 space-y-2.5">
          <div className="flex items-center justify-between font-mono text-xs text-white">
            <div className="flex items-center gap-2">
              <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
              <span className="font-bold text-[11px] sm:text-xs">
                YETENEK RADARI // İLANLARI FİLTRELE:
              </span>
            </div>
            {selectedSkill && selectedSkill !== "all" && (
              <button
                type="button"
                onClick={() => onSelectSkill("all")}
                className="text-[10px] text-white/60 hover:text-white underline cursor-pointer"
              >
                Filtreyi Temizle
              </button>
            )}
          </div>

          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar py-1 touch-pan-x">
            <button
              type="button"
              onClick={() => onSelectSkill("all")}
              className={`lux-press px-3 py-1.5 rounded-xl font-mono text-xs whitespace-nowrap flex-shrink-0 cursor-pointer transition-all ${
                !selectedSkill || selectedSkill === "all"
                  ? "bg-white text-black font-bold border border-white"
                  : "bg-white/[0.04] text-white/70 hover:text-white border border-white/10"
              }`}
            >
              TÜMÜ ({allDossiers.length})
            </button>
            {skillCounts.map(([skill, count]) => {
              const isActive = selectedSkill.toLowerCase() === skill.toLowerCase();
              return (
                <button
                  key={skill}
                  type="button"
                  onClick={() => onSelectSkill(skill)}
                  className={`lux-press px-3 py-1.5 rounded-xl font-mono text-xs whitespace-nowrap flex-shrink-0 cursor-pointer transition-all ${
                    isActive
                      ? "bg-white text-black font-bold border border-white"
                      : "bg-white/[0.04] text-white/70 hover:text-white border border-white/10"
                  }`}
                >
                  <span>{skill}</span>
                  <span
                    className={`ml-1.5 px-1 py-0.2 rounded text-[10px] ${
                      isActive ? "bg-black/15 text-black" : "bg-white/10 text-white/60"
                    }`}
                  >
                    {count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* City Filter Pills & Sort Select */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 text-xs font-mono">
          <div className="flex items-center gap-1.5 overflow-x-auto no-scrollbar flex-nowrap py-1 touch-pan-x">
            <button
              type="button"
              onClick={() => setSelectedCityFilter("all")}
              className={`lux-press px-3 py-1 rounded-xl whitespace-nowrap flex-shrink-0 cursor-pointer transition-all ${
                selectedCityFilter === "all"
                  ? "bg-white text-black font-bold border border-white"
                  : "bg-white/[0.04] text-white/70 hover:text-white border border-white/10"
              }`}
            >
              Tümü ({allDossiers.length})
            </button>
            {Object.entries(cities).map(([key, city]) => (
              <button
                key={key}
                type="button"
                onClick={() => setSelectedCityFilter(key)}
                className={`lux-press px-3 py-1 rounded-xl whitespace-nowrap flex-shrink-0 cursor-pointer transition-all ${
                  selectedCityFilter === key
                    ? "bg-white text-black font-bold border border-white"
                    : "bg-white/[0.04] text-white/70 hover:text-white border border-white/10"
                }`}
              >
                {city.name.split(",")[0]} ({city.count})
              </button>
            ))}
          </div>

          <div className="flex items-center gap-2 self-end sm:self-auto flex-shrink-0">
            <span className="text-white/40 text-[11px]">SIRALA:</span>
            <select
              value={sortBy}
              onChange={(e) => setSortBy(e.target.value as any)}
              className="bg-[#040405] border border-white/20 rounded-xl px-3 py-1.5 text-white font-mono text-xs focus:outline-none cursor-pointer"
            >
              <option value="score">Uyum Puanına Göre (Yüksek-Düşük)</option>
              <option value="recent">En Son Keşfedilenler</option>
            </select>
          </div>
        </div>

        {/* Job Cards Grid */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {filteredJobs.length === 0 ? (
            <div className="col-span-1 md:col-span-2 text-center py-12 text-white/40 font-mono text-xs">
              Arama ve yetenek kriterlerine uygun açık pozisyon bulunamadı.
            </div>
          ) : (
            filteredJobs.map((job) => (
              <div
                key={job.id}
                className="p-5 rounded-2xl bg-[#040405] border border-white/15 hover:border-white/40 transition-all flex flex-col justify-between space-y-4"
              >
                <div className="space-y-2">
                  <div className="flex items-center justify-between font-mono text-xs">
                    <span className="px-2 py-0.5 rounded text-[10px] bg-white/10 text-white border border-white/20">
                      {job.cityName ? job.cityName.split(",")[0] : "KÜRESEL"}
                    </span>
                    <span className="font-bold text-emerald-400">{job.score} FIT</span>
                  </div>

                  <h3 className="text-base font-bold font-mono text-white leading-snug">
                    {job.title}
                  </h3>

                  <div className="text-xs font-mono text-white/70">
                    {job.company} • {job.location}
                  </div>
                  <div className="text-xs font-mono text-white/50">{job.salary}</div>

                  {/* AI Değerlendirmesi */}
                  <div className="p-3 rounded-xl bg-black/40 border border-white/10 space-y-1 mt-2">
                    <div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5 font-semibold">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      AI Değerlendirmesi
                    </div>
                    <p className="text-xs text-white/80 leading-relaxed font-sans line-clamp-2">
                      {job.analysis}
                    </p>
                  </div>

                  {/* Skills Chips */}
                  <div className="flex flex-wrap gap-1.5 pt-2">
                    {job.skills.map((s, idx) => (
                      <button
                        key={idx}
                        type="button"
                        onClick={() => onSelectSkill(s)}
                        className="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[10px] font-mono text-white/70 hover:bg-white hover:text-black cursor-pointer transition-colors"
                      >
                        {s}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex items-center gap-2 pt-3 border-t border-white/10 font-mono text-xs">
                  <button
                    type="button"
                    onClick={() => onOpenModal(job)}
                    className="flex-1 py-2 rounded-xl silver-btn lux-press font-bold text-[11px] uppercase cursor-pointer"
                  >
                    DOSYAYI İNCELE
                  </button>
                  <a
                    href={job.application_url || "#"}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="px-3 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white text-[11px] cursor-pointer"
                  >
                    BAĞLANTI
                  </a>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}
