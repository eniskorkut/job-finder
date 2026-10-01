"use client";

import React, { useState, useRef } from "react";

interface TabCvProps {
  onShowToast: (msg: string) => void;
}

export function TabCv({ onShowToast }: TabCvProps) {
  const [cvFilename, setCvFilename] = useState("Enis_Korkut_Executive_CV_2026.pdf");
  const [targetTitles, setTargetTitles] = useState<string[]>([
    "Lead AI Architect",
    "Staff Engineer",
    "Principal Systems Lead",
  ]);
  const [newTitle, setNewTitle] = useState("");

  const [skills, setSkills] = useState<string[]>([
    "Next.js 16",
    "Python FastAPI",
    "Autonomous Agents",
    "Distributed Systems",
    "PyTorch",
  ]);
  const [newSkill, setNewSkill] = useState("");

  const [salary, setSalary] = useState("£120,000 / $180,000");
  const [workMode, setWorkMode] = useState("remote");
  const fileInputRef = useRef<HTMLInputElement>(null);

  const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setCvFilename(file.name);
      onShowToast(`${file.name} başarıyla yüklendi ve ayrıştırıldı.`);
    }
  };

  const handleAddTitle = () => {
    const val = newTitle.trim();
    if (!val) return;
    if (!targetTitles.includes(val)) {
      setTargetTitles([...targetTitles, val]);
    }
    setNewTitle("");
  };

  const handleRemoveTitle = (titleToRemove: string) => {
    setTargetTitles(targetTitles.filter((t) => t !== titleToRemove));
  };

  const handleAddSkill = () => {
    const val = newSkill.trim();
    if (!val) return;
    if (!skills.includes(val)) {
      setSkills([...skills, val]);
    }
    setNewSkill("");
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setSkills(skills.filter((s) => s !== skillToRemove));
  };

  const handleReanalyze = () => {
    onShowToast("CV derinlemesine analiz ediliyor...");
    setTimeout(() => {
      onShowToast("Analiz tamamlandı: CV Uyum Skoru %98.4 olarak teyit edildi.");
    }, 1000);
  };

  const handleSave = () => {
    onShowToast("Kariyer hedefleri ve asgari maaş baremleri güncellendi.");
  };

  return (
    <div id="tab-cv" className="tab-pane space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Upload & Parsed Summary (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-white/10 font-mono">
              <span className="text-sm font-bold text-white uppercase">AKTİF YÖNETİCİ CV&apos;Sİ</span>
              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                DERİNLEMESİNE AYRIŞTIRILDI
              </span>
            </div>

            {/* Upload Dropzone */}
            <div
              onClick={() => fileInputRef.current?.click()}
              className="border-2 border-dashed border-white/20 hover:border-white/50 rounded-2xl p-6 text-center cursor-pointer transition-all bg-white/[0.01]"
            >
              <svg
                className="w-8 h-8 text-white/60 mx-auto mb-2"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
              >
                <path d="M4 14.899A7 7 0 1 1 15.71 8h1.79a4.5 4.5 0 0 1 2.5 8.242" />
                <path d="M12 12v9" />
                <path d="m16 16-4-4-4 4" />
              </svg>
              <div className="text-xs font-mono font-bold text-white">YENİ CV YÜKLE VEYA BURAYA BIRAK</div>
              <div className="text-[10px] font-mono text-white/40 mt-1">PDF, DOCX, Markdown (Maks. 10MB)</div>
              <input
                type="file"
                ref={fileInputRef}
                className="hidden"
                accept=".pdf,.docx,.txt,.md"
                onChange={handleFileUpload}
              />
            </div>

            {/* Current File Pill */}
            <div className="p-3.5 rounded-xl bg-[#040405] border border-white/15 flex items-center justify-between font-mono text-xs">
              <div className="flex items-center gap-2.5 truncate">
                <svg
                  className="w-4 h-4 text-white flex-shrink-0"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M14.5 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7.5L14.5 2z" />
                  <polyline points="14 2 14 8 20 8" />
                </svg>
                <span className="truncate text-white font-medium">{cvFilename}</span>
              </div>
              <span className="text-white/40 text-[10px]">1.4 MB</span>
            </div>

            {/* Parsed Summary Extract */}
            <div className="space-y-3 font-mono text-xs">
              <div className="text-[10px] text-white/40 uppercase tracking-wider">CV Eşleşme Oranı</div>
              <div className="text-base font-bold text-emerald-400 font-mono">%98.4 Yüksek Uyum Skoru</div>

              <div className="text-[10px] text-white/40 uppercase tracking-wider pt-2">Toplam Tecrübe Baremi</div>
              <div className="text-white/80">9+ Yıl Üst Düzey Dağıtık Sistemler &amp; AI Ajanları</div>
            </div>

            <button
              onClick={handleReanalyze}
              className="lux-press w-full py-2.5 rounded-xl bg-white/10 hover:bg-white/15 text-white text-xs font-mono font-bold flex items-center justify-center gap-2"
            >
              <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M21.5 2v6h-6M21.34 15.57a10 10 0 1 1-.57-8.38l5.67-5.67" />
              </svg>
              <span>AI ile CV&apos;yi Yeniden Analiz Et</span>
            </button>
          </div>
        </div>

        {/* Right: Matching Preferences & Parameters (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-white/10 font-mono">
              <span className="text-sm font-bold text-white uppercase">HEDEF POZİSYON VE EŞLEŞTİRME PARAMETRELERİ</span>
              <span className="text-white/40 text-xs">Gerçek Zamanlı Filtre</span>
            </div>

            <div className="space-y-4 font-mono text-xs">
              {/* Target Titles */}
              <div>
                <label className="block text-white/60 mb-1.5 uppercase text-[11px]">Hedef Pozisyon Başlıkları</label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {targetTitles.map((title) => (
                    <span
                      key={title}
                      className="px-2.5 py-1 rounded-lg bg-white/10 text-white flex items-center gap-1.5"
                    >
                      {title}
                      <button
                        type="button"
                        onClick={() => handleRemoveTitle(title)}
                        className="text-white/40 hover:text-white"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newTitle}
                    onChange={(e) => setNewTitle(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAddTitle();
                      }
                    }}
                    placeholder="Yeni unvan ekle..."
                    className="flex-1 bg-[#040405] border border-white/15 rounded-xl px-3.5 py-2 text-white font-mono text-xs focus:border-white focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleAddTitle}
                    className="px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Core Skills */}
              <div>
                <label className="block text-white/60 mb-1.5 uppercase text-[11px]">
                  Çekirdek Yetenekler (Öncelikli Puanlandırılır)
                </label>
                <div className="flex flex-wrap gap-1.5 mb-2">
                  {skills.map((skill) => (
                    <span
                      key={skill}
                      className="px-2.5 py-1 rounded-lg bg-white/10 text-white flex items-center gap-1.5"
                    >
                      {skill}
                      <button
                        type="button"
                        onClick={() => handleRemoveSkill(skill)}
                        className="text-white/40 hover:text-white"
                      >
                        ×
                      </button>
                    </span>
                  ))}
                </div>
                <div className="flex gap-2">
                  <input
                    type="text"
                    value={newSkill}
                    onChange={(e) => setNewSkill(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") {
                        e.preventDefault();
                        handleAddSkill();
                      }
                    }}
                    placeholder="Yeni yetenek ekle..."
                    className="flex-1 bg-[#040405] border border-white/15 rounded-xl px-3.5 py-2 text-white font-mono text-xs focus:border-white focus:outline-none"
                  />
                  <button
                    type="button"
                    onClick={handleAddSkill}
                    className="px-3.5 py-2 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold"
                  >
                    +
                  </button>
                </div>
              </div>

              {/* Salary & Work Mode */}
              <div className="grid grid-cols-1 md:grid-cols-2 gap-4 pt-2">
                <div>
                  <label className="block text-white/60 mb-1.5 uppercase text-[11px]">Asgari Maaş Beklentisi</label>
                  <input
                    type="text"
                    value={salary}
                    onChange={(e) => setSalary(e.target.value)}
                    className="w-full bg-[#040405] border border-white/15 rounded-xl px-3.5 py-2.5 text-white font-mono focus:border-white focus:outline-none"
                  />
                </div>
                <div>
                  <label className="block text-white/60 mb-1.5 uppercase text-[11px]">Çalışma Formatı</label>
                  <select
                    value={workMode}
                    onChange={(e) => setWorkMode(e.target.value)}
                    className="w-full bg-[#040405] border border-white/15 rounded-xl px-3.5 py-2.5 text-white font-mono focus:border-white focus:outline-none cursor-pointer"
                  >
                    <option value="remote">Tamamen Uzaktan (Remote First)</option>
                    <option value="hybrid">Hibrit veya Uzaktan</option>
                    <option value="any">Fark Etmez / Relocation Dahil</option>
                  </select>
                </div>
              </div>

              <div className="pt-4 border-t border-white/10">
                <button
                  type="button"
                  onClick={handleSave}
                  className="silver-btn lux-press w-full py-3 rounded-xl text-xs font-mono uppercase tracking-wider"
                >
                  TERCİHLERİ VE EŞLEŞTİRME FİLTRELERİNİ KAYDET
                </button>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
