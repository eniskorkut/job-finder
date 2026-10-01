"use client";

import { useState } from "react";
import { Globe3D } from "./globe-3d";
import type { CityHub, Dossier } from "./types";

interface TabGlobeProps {
  cities: Record<string, CityHub>;
  activeCityKey: string;
  onSelectCity: (cityKey: string) => void;
  activeDossierIdx: number;
  onSelectDossier: (idx: number) => void;
  onOpenModal: (dossier: Dossier) => void;
  onSelectSkill: (skill: string) => void;
}

export function TabGlobe({
  cities,
  activeCityKey,
  onSelectCity,
  activeDossierIdx,
  onSelectDossier,
  onOpenModal,
  onSelectSkill,
}: TabGlobeProps) {
  const [textureMode, setTextureMode] = useState<
    "topo" | "blue-marble" | "carbon-matrix"
  >("topo");
  const [isAutoRotating, setIsAutoRotating] = useState(true);

  const activeCity = cities[activeCityKey] || cities.london;
  const dossiers = activeCity?.dossiers || [];
  const safeIdx = Math.min(Math.max(0, activeDossierIdx), Math.max(0, dossiers.length - 1));
  const activeDossier = dossiers[safeIdx] || dossiers[0];

  const handlePrevDossier = () => {
    if (dossiers.length === 0) return;
    const nextIdx = (safeIdx - 1 + dossiers.length) % dossiers.length;
    onSelectDossier(nextIdx);
  };

  const handleNextDossier = () => {
    if (dossiers.length === 0) return;
    const nextIdx = (safeIdx + 1) % dossiers.length;
    onSelectDossier(nextIdx);
  };

  return (
    <div id="tab-globe" className="tab-pane space-y-4 sm:space-y-6">
      {/* 3D Globe Radar Card */}
      <div className="carbon-card rounded-2xl sm:rounded-3xl p-3.5 sm:p-5 md:p-7 space-y-3 sm:space-y-4 relative overflow-hidden">
        {/* Radar Map Header & City Direct Controls */}
        <div className="flex flex-col lg:flex-row lg:items-center justify-between pb-3 sm:pb-4 border-b border-white/10 gap-2.5 sm:gap-3 font-mono">
          <div className="flex items-center gap-2 sm:gap-3">
            <span className="w-2 h-2 sm:w-2.5 sm:h-2.5 rounded-full bg-white shadow-[0_0_10px_#ffffff] flex-shrink-0" />
            <span className="text-[11px] sm:text-xs uppercase tracking-wider text-white">
              KÜRESEL İLAN MENŞEİ:{" "}
              <span className="text-white font-bold border-b border-white pb-0.5">
                {activeCity.name}
              </span>
            </span>
          </div>

          {/* Direct City Quick Switches (Equal height pills) */}
          <div className="flex items-center gap-1.5 text-xs overflow-x-auto no-scrollbar flex-nowrap py-1 w-full lg:w-auto touch-pan-x">
            {Object.entries(cities).map(([key, city]) => {
              const isActive = key === activeCityKey;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => onSelectCity(key)}
                  className={`lux-press h-8 px-3 rounded-xl font-mono text-xs whitespace-nowrap flex-shrink-0 inline-flex items-center justify-center cursor-pointer transition-all ${
                    isActive
                      ? "bg-white text-black font-bold border border-white shadow-[0_0_15px_rgba(255,255,255,0.4)]"
                      : "bg-white/[0.04] text-white/70 hover:text-white border border-white/10"
                  }`}
                >
                  <span>{city.name.split(",")[0]}</span>
                  <span
                    className={`ml-1.5 px-1 py-0.2 rounded text-[10px] ${
                      isActive ? "bg-black/15 text-black" : "bg-white/10 text-white/60"
                    }`}
                  >
                    {city.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* 3D WebGL Globe Viewport */}
        <div className="relative w-full h-[360px] sm:h-[480px] md:h-[600px] rounded-2xl bg-[#010102] border border-white/10 overflow-hidden shadow-2xl flex items-center justify-center">
          {/* Subtle Radar Grid & Concentric Scope Target Behind Globe */}
          <div className="absolute inset-0 radar-grid-bg opacity-30 pointer-events-none" />
          <svg
            className="absolute inset-0 w-full h-full opacity-15 pointer-events-none"
            xmlns="http://www.w3.org/2000/svg"
          >
            <circle
              cx="50%"
              cy="50%"
              r="130"
              fill="none"
              stroke="#ffffff"
              strokeWidth="0.8"
              strokeDasharray="4 6"
            />
            <circle
              cx="50%"
              cy="50%"
              r="240"
              fill="none"
              stroke="#ffffff"
              strokeWidth="0.8"
              strokeDasharray="4 6"
            />
            <circle
              cx="50%"
              cy="50%"
              r="350"
              fill="none"
              stroke="#ffffff"
              strokeWidth="0.8"
              strokeDasharray="4 6"
            />
            <line
              x1="50%"
              y1="0"
              x2="50%"
              y2="100%"
              stroke="#ffffff"
              strokeWidth="0.5"
              strokeDasharray="2 4"
            />
            <line
              x1="0"
              y1="50%"
              x2="100%"
              y2="50%"
              stroke="#ffffff"
              strokeWidth="0.5"
              strokeDasharray="2 4"
            />
          </svg>

          {/* 3D Globe */}
          <Globe3D
            activeCityKey={activeCityKey}
            onSelectCity={onSelectCity}
            textureMode={textureMode}
            isAutoRotating={isAutoRotating}
            cities={cities}
          />

          {/* Top Left HUD: Active Coordinate Telemetry */}
          <div className="absolute top-2.5 sm:top-4 left-2.5 sm:left-4 z-20 p-2 sm:p-3.5 rounded-xl sm:rounded-2xl bg-black/85 backdrop-blur-xl border border-white/20 text-[10px] sm:text-xs font-mono space-y-0.5 sm:space-y-1 shadow-2xl pointer-events-none max-w-[170px] sm:max-w-none">
            <div className="text-[9px] sm:text-[10px] uppercase tracking-wider text-white font-bold flex items-center gap-1.5">
              <span className="w-1.5 h-1.5 rounded-full bg-white shadow-[0_0_8px_#ffffff] animate-ping flex-shrink-0" />
              <span className="truncate">CANLI VERİ AKIŞI</span>
            </div>
            <div className="text-white/90 truncate">
              Odak: <span className="text-white font-bold">{activeCity.name.split(",")[0]}</span>
            </div>
            <div className="text-white/50 text-[9px] sm:text-[10px] hidden sm:block">
              Merkez Üs: <span className="text-white">İSTANBUL</span> // Çift Yönlü Güvenli Kanal
            </div>
          </div>

          {/* Top Right HUD: 3D Control Switches */}
          <div className="absolute top-2.5 sm:top-4 right-2.5 sm:right-4 z-20 flex flex-wrap items-center justify-end gap-1.5 sm:gap-2">
            <button
              type="button"
              onClick={() => setIsAutoRotating(!isAutoRotating)}
              className="lux-press px-2 sm:px-3 py-1 sm:py-1.5 rounded-lg sm:rounded-xl bg-black/80 hover:bg-black backdrop-blur-xl border border-white/20 text-[10px] sm:text-xs font-mono text-white flex items-center gap-1.5 cursor-pointer"
            >
              <span
                className={`w-1.5 h-1.5 sm:w-2 sm:h-2 rounded-full flex-shrink-0 ${
                  isAutoRotating ? "bg-emerald-400 animate-ping" : "bg-white/40"
                }`}
              />
              <span className="hidden sm:inline">
                {isAutoRotating ? "OTOMATİK DÖNÜŞ: AKTİF" : "OTOMATİK DÖNÜŞ: DURDURULDU"}
              </span>
              <span className="sm:hidden text-[9px]">DÖNÜŞ</span>
            </button>

            {/* Texture Presets */}
            <div className="flex items-center gap-0.5 sm:gap-1 p-0.5 sm:p-1 rounded-lg sm:rounded-xl bg-black/80 backdrop-blur-xl border border-white/20 text-[10px] sm:text-[11px] font-mono">
              <button
                type="button"
                onClick={() => setTextureMode("topo")}
                className={`texture-btn lux-press px-2 sm:px-2.5 py-1 rounded-md sm:rounded-lg cursor-pointer ${
                  textureMode === "topo"
                    ? "bg-white text-black font-bold"
                    : "text-white/70 hover:text-white"
                }`}
              >
                TOPO
              </button>
              <button
                type="button"
                onClick={() => setTextureMode("blue-marble")}
                className={`texture-btn lux-press px-2 sm:px-2.5 py-1 rounded-md sm:rounded-lg cursor-pointer ${
                  textureMode === "blue-marble"
                    ? "bg-white text-black font-bold"
                    : "text-white/70 hover:text-white"
                }`}
              >
                NASA
              </button>
              <button
                type="button"
                onClick={() => setTextureMode("carbon-matrix")}
                className={`texture-btn lux-press px-2 sm:px-2.5 py-1 rounded-md sm:rounded-lg cursor-pointer hidden sm:block ${
                  textureMode === "carbon-matrix"
                    ? "bg-white text-black font-bold"
                    : "text-white/70 hover:text-white"
                }`}
              >
                MATRİS
              </button>
            </div>
          </div>

          {/* Bottom Right HUD: Center on Istanbul Base */}
          <div className="absolute bottom-2.5 sm:bottom-4 right-2.5 sm:right-4 z-20 flex items-center gap-2">
            <button
              type="button"
              onClick={() => onSelectCity("istanbul")}
              className="lux-press px-2.5 sm:px-3.5 py-1.5 sm:py-2 rounded-xl bg-black/85 hover:bg-white hover:text-black backdrop-blur-xl border border-white/20 text-[11px] sm:text-xs font-mono text-white flex items-center gap-1.5 transition-all shadow-xl cursor-pointer"
            >
              <svg
                className="w-3.5 h-3.5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
              >
                <circle cx="12" cy="12" r="3" />
                <path d="M12 2v3M12 19v3M2 12h3M19 12h3" />
              </svg>
              <span>İSTANBUL MERKEZ</span>
            </button>
          </div>

          {/* Bottom Left HUD: Telemetry */}
          <div className="absolute bottom-4 left-4 z-20 hidden md:flex items-center gap-3 px-3.5 py-1.5 rounded-xl bg-black/80 backdrop-blur-xl border border-white/15 text-[11px] font-mono text-white/60 pointer-events-none">
            <span>
              ALTİTÜD: <span className="text-white font-bold">1.45x</span>
            </span>
            <span className="text-white/20">|</span>
            <span>
              HIZ: <span className="text-emerald-400 font-bold">60 FPS</span>
            </span>
            <span className="text-white/20">|</span>
            <span>
              IŞIMA: <span className="text-white">FRESNEL SIVI GÜMÜŞ</span>
            </span>
          </div>
        </div>
      </div>

      {/* Horizontal Dossier Carousel Stage */}
      <div className="carbon-card rounded-2xl sm:rounded-3xl p-3.5 sm:p-6 md:p-10 space-y-4 sm:space-y-6 overflow-hidden w-full max-w-full">
        {/* Stage Navigation Header */}
        <div className="space-y-3 pb-4 sm:pb-5 border-b border-white/15">
          <div className="flex flex-col md:flex-row md:items-center justify-between gap-3">
            <div>
              <div className="flex items-center gap-2 mb-1">
                <span className="w-2 h-2 rounded-full bg-white shadow-[0_0_8px_#ffffff] flex-shrink-0" />
                <span className="text-[10px] sm:text-[11px] font-mono font-bold text-white/50 uppercase tracking-widest leading-normal">
                  ÖNCELİKLİ İLAN VİTRİNİ &amp; DETAYLI EŞLEŞME ANALİZİ
                </span>
              </div>
              <h3 className="text-base sm:text-xl md:text-2xl font-mono font-bold text-white tracking-tight">
                {activeCity.name.split(",")[0].toUpperCase()} ODAKLI ÖNCELİKLİ İLANLAR
              </h3>
            </div>

            {/* Controls: City Selector & Pagination */}
            <div className="flex flex-wrap sm:flex-nowrap items-center justify-between sm:justify-end gap-2 w-full md:w-auto">
              <div className="flex items-center gap-1.5 sm:gap-2 bg-[#040405] border border-white/20 hover:border-white/40 rounded-xl px-2.5 sm:px-3 py-1.5 transition-all text-xs font-mono flex-1 min-w-[130px] sm:flex-initial">
                <span className="text-white/40 text-[9px] sm:text-[10px] uppercase tracking-wider font-semibold whitespace-nowrap">
                  MERKEZ:
                </span>
                <select
                  value={activeCityKey}
                  onChange={(e) => onSelectCity(e.target.value)}
                  className="bg-transparent text-white font-bold text-xs font-mono focus:outline-none cursor-pointer truncate w-full sm:w-auto"
                >
                  {Object.entries(cities).map(([key, city]) => (
                    <option key={key} value={key} className="bg-[#020203] text-white">
                      {city.name} ({city.count})
                    </option>
                  ))}
                </select>
              </div>

              <div className="flex items-center justify-between sm:justify-start gap-1.5 sm:gap-2 bg-[#040405] border border-white/20 rounded-xl px-2.5 sm:px-3 py-1 text-xs font-mono flex-shrink-0">
                <span className="text-white/40 text-[11px] sm:text-xs whitespace-nowrap">
                  İLAN <span className="text-white font-bold">{safeIdx + 1}</span> /{" "}
                  <span className="text-white">{dossiers.length}</span>
                </span>
                <div className="flex items-center gap-1 ml-1 border-l border-white/15 pl-1.5 sm:pl-2">
                  <button
                    type="button"
                    onClick={handlePrevDossier}
                    title="Önceki İlan"
                    className="lux-press w-7 h-7 rounded-lg bg-white/10 hover:bg-white/20 text-white flex items-center justify-center font-bold text-xs cursor-pointer"
                  >
                    ←
                  </button>
                  <button
                    type="button"
                    onClick={handleNextDossier}
                    title="Sonraki İlan"
                    className="lux-press w-7 h-7 rounded-lg bg-white/10 hover:bg-white/20 text-white flex items-center justify-center font-bold text-xs cursor-pointer"
                  >
                    →
                  </button>
                </div>
              </div>
            </div>
          </div>

          {/* Quick City Switcher Pills */}
          <div className="flex items-center gap-1.5 sm:gap-2 pt-1 text-xs font-mono overflow-x-auto no-scrollbar flex-nowrap w-full touch-pan-x">
            {Object.entries(cities).map(([key, city]) => {
              const isActive = key === activeCityKey;
              return (
                <button
                  key={key}
                  type="button"
                  onClick={() => onSelectCity(key)}
                  className={`lux-press h-8 px-3 rounded-xl font-mono text-xs whitespace-nowrap flex-shrink-0 inline-flex items-center justify-center cursor-pointer transition-all ${
                    isActive
                      ? "bg-white text-black font-bold border border-white shadow-[0_0_15px_rgba(255,255,255,0.4)]"
                      : "bg-white/[0.04] text-white/70 hover:text-white border border-white/10"
                  }`}
                >
                  <span>{city.name.split(",")[0]}</span>
                  <span
                    className={`ml-1.5 px-1 py-0.2 rounded text-[10px] ${
                      isActive ? "bg-black/15 text-black" : "bg-white/10 text-white/60"
                    }`}
                  >
                    {city.count}
                  </span>
                </button>
              );
            })}
          </div>
        </div>

        {/* Active Dossier Presentation Body */}
        {activeDossier && (
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 sm:gap-8 items-start">
            {/* Left: Position & Deep Match Analysis */}
            <div className="lg:col-span-8 space-y-3.5 sm:space-y-4">
              <div className="flex flex-wrap items-center gap-2 sm:gap-3">
                <span className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-white text-black uppercase tracking-wider shadow-[0_0_15px_rgba(255,255,255,0.4)]">
                  {activeDossier.score} CV FIT
                </span>
                <span className="text-[11px] sm:text-xs font-mono text-white/40 uppercase">
                  KOD: {activeDossier.ref}
                </span>
                <span className="text-[11px] sm:text-xs font-mono text-emerald-400">
                  {activeDossier.freshness}
                </span>
              </div>

              <div>
                <h2 className="text-xl sm:text-2xl md:text-3xl lg:text-4xl font-mono font-bold text-white tracking-tight leading-snug">
                  {activeDossier.title}
                </h2>
                <div className="text-xs sm:text-sm font-mono text-white/80 mt-1">
                  {activeDossier.company} • {activeDossier.location} • {activeDossier.salary}
                </div>
              </div>

              {/* Deep AI Insights Box */}
              <div className="p-3.5 sm:p-5 rounded-2xl bg-[#040405] border border-white/15 space-y-2.5">
                <div className="text-xs font-mono text-white font-bold uppercase tracking-wider flex items-center justify-between">
                  <span className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399]" />
                    <span>AI Değerlendirmesi</span>
                  </span>
                  <span className="text-emerald-400/90 text-[10px] font-mono tracking-wider">
                    AKTİF EŞLEŞME RAPORU
                  </span>
                </div>
                <p className="text-xs sm:text-sm text-white/90 leading-relaxed font-sans">
                  {activeDossier.analysis}
                </p>
              </div>

              {/* Skill Badges */}
              <div className="space-y-2 pt-1">
                <div className="text-[10px] font-mono uppercase tracking-wider text-white/50 flex items-center justify-between">
                  <span>EŞLEŞEN VE TALEP EDİLEN YETENEKLER:</span>
                  <span className="text-[10px] text-white/30 hidden sm:inline">
                    İLGİLİ İLANLARI FİLTRELEMEK İÇİN TIKLAYIN
                  </span>
                </div>
                <div className="flex flex-wrap gap-1.5 sm:gap-2 text-xs font-mono text-white/80">
                  {activeDossier.skills.map((skill, sIdx) => (
                    <button
                      key={sIdx}
                      type="button"
                      onClick={() => onSelectSkill(skill)}
                      className="lux-press px-2.5 py-1 rounded-lg bg-white/10 hover:bg-white text-white hover:text-black border border-white/15 transition-all text-xs cursor-pointer"
                    >
                      {skill}
                    </button>
                  ))}
                </div>
              </div>
            </div>

            {/* Right: Executive Action & Telegram Dispatch */}
            <div className="lg:col-span-4 p-4 sm:p-6 rounded-2xl bg-black/60 border border-white/15 flex flex-col justify-between space-y-5 sm:space-y-6">
              <div className="space-y-3 font-mono text-xs">
                <div className="text-[10px] uppercase text-white/40 tracking-widest">
                  Tarama Doğrulaması
                </div>
                <div className="text-emerald-400 font-semibold flex items-center gap-1.5 text-xs">
                  <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                  {activeDossier.source}
                </div>

                <div className="text-[10px] uppercase text-white/40 tracking-widest pt-1.5">
                  Telegram VIP Bildirimi
                </div>
                <div className="text-white/70 text-xs">{activeDossier.telegram}</div>
              </div>

              <div className="space-y-2 pt-3 border-t border-white/10">
                <button
                  type="button"
                  onClick={() => onOpenModal(activeDossier)}
                  className="silver-btn lux-press w-full py-3 sm:py-3.5 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center justify-center gap-2 cursor-pointer"
                >
                  <span>Başvuruyu Başlat &amp; AI Ön Yazı</span>
                  <svg
                    className="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M5 12h14M12 5l7 7-7 7" />
                  </svg>
                </button>
                <a
                  href={activeDossier.application_url || "#"}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="lux-press w-full py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-mono flex items-center justify-center gap-1.5 text-center cursor-pointer"
                >
                  <span>Orijinal İlanı Görüntüle</span>
                  <svg
                    className="w-3.5 h-3.5"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2"
                  >
                    <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6M15 3h6v6M10 14L21 3" />
                  </svg>
                </a>
              </div>
            </div>
          </div>
        )}

        {/* Horizontal Thumbnails Carousel / Slider */}
        <div className="pt-5 sm:pt-6 border-t border-white/10 space-y-3">
          <div className="flex items-center justify-between gap-2">
            <div className="text-[10px] sm:text-xs font-mono uppercase tracking-wider text-white/70 truncate">
              SEÇİLİ MERKEZ ÜS İLANLARI ({dossiers.length} İLAN)
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <span className="text-[11px] font-mono text-white font-bold bg-white/10 border border-white/15 px-2.5 py-1 rounded-xl">
                {safeIdx + 1} / {dossiers.length}
              </span>
              <div className="flex items-center gap-1 bg-[#040405] border border-white/20 rounded-xl p-0.5">
                <button
                  type="button"
                  onClick={handlePrevDossier}
                  aria-label="Önceki İlan"
                  className="lux-press w-8 h-8 rounded-lg bg-white/10 hover:bg-white/20 text-white flex items-center justify-center font-bold text-xs cursor-pointer touch-manipulation"
                >
                  <svg
                    className="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <path d="M15 18l-6-6 6-6" />
                  </svg>
                </button>
                <button
                  type="button"
                  onClick={handleNextDossier}
                  aria-label="Sonraki İlan"
                  className="lux-press w-8 h-8 rounded-lg bg-white/10 hover:bg-white/20 text-white flex items-center justify-center font-bold text-xs cursor-pointer touch-manipulation"
                >
                  <svg
                    className="w-4 h-4"
                    viewBox="0 0 24 24"
                    fill="none"
                    stroke="currentColor"
                    strokeWidth="2.5"
                  >
                    <path d="M9 18l6-6-6-6" />
                  </svg>
                </button>
              </div>
            </div>
          </div>

          {/* Unobstructed Horizontal Scroll Track */}
          <div className="relative w-full">
            <div className="overflow-x-auto scroll-smooth snap-x snap-mandatory flex gap-3 sm:gap-4 py-2 px-0.5 no-scrollbar touch-pan-x">
              {dossiers.map((d, dIdx) => {
                const isSelected = dIdx === safeIdx;
                return (
                  <div
                    key={d.id || dIdx}
                    onClick={() => onSelectDossier(dIdx)}
                    className={`snap-start flex-shrink-0 w-[84vw] max-w-[320px] sm:w-[320px] md:w-[340px] p-4 sm:p-5 rounded-2xl cursor-pointer transition-all duration-200 flex flex-col justify-between space-y-3 ${
                      isSelected
                        ? "bg-white/[0.08] border-2 border-white shadow-[0_0_25px_rgba(255,255,255,0.2)] transform scale-[1.01]"
                        : "bg-[#040405] border border-white/15 hover:border-white/40 opacity-80 hover:opacity-100"
                    }`}
                  >
                    <div className="flex items-center justify-between font-mono text-[10px]">
                      <span className="text-white/40 uppercase">NO. 0{dIdx + 1}</span>
                      <span
                        className={`px-2 py-0.5 rounded-full font-bold ${
                          isSelected
                            ? "bg-white text-black"
                            : "bg-white/10 text-emerald-400"
                        }`}
                      >
                        {d.score}
                      </span>
                    </div>

                    <div>
                      <div className="text-sm font-mono font-bold text-white line-clamp-1">
                        {d.title}
                      </div>
                      <div className="text-xs text-white/70 line-clamp-1 mt-0.5">
                        {d.company} • {d.location.split("/")[0]}
                      </div>
                      <div className="text-[11px] text-white/50 font-mono mt-1">
                        {d.salary}
                      </div>
                    </div>

                    {/* AI Değerlendirmesi inside slider card */}
                    <div className="p-2.5 rounded-xl bg-black/40 border border-white/10 space-y-1">
                      <div className="text-[10px] font-mono text-emerald-400 flex items-center gap-1.5 font-semibold">
                        <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                        AI Değerlendirmesi
                      </div>
                      <p className="text-[11px] text-white/80 line-clamp-2 leading-relaxed">
                        {d.analysis}
                      </p>
                    </div>

                    <div className="flex flex-wrap gap-1">
                      {d.skills.slice(0, 3).map((s, idx) => (
                        <span
                          key={idx}
                          className="px-1.5 py-0.5 rounded bg-white/5 border border-white/10 text-[10px] font-mono text-white/60"
                        >
                          {s}
                        </span>
                      ))}
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
