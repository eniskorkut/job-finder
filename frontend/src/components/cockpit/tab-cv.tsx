"use client";

import React, { useState, useEffect, useRef } from "react";
import { api } from "@/lib/api";
import type { CV, Preferences } from "@/lib/types";

interface TabCvProps {
  onShowToast: (msg: string) => void;
}

export function TabCv({ onShowToast }: TabCvProps) {
  const [cvList, setCvList] = useState<CV[]>([]);
  const [activeCv, setActiveCv] = useState<CV | null>(null);
  const [isUploading, setIsUploading] = useState(false);
  const [isReanalyzing, setIsReanalyzing] = useState(false);
  const [isSavingPrefs, setIsSavingPrefs] = useState(false);

  // Career Preferences
  const [targetTitles, setTargetTitles] = useState<string[]>([]);
  const [newTitle, setNewTitle] = useState("");
  const [targetSkills, setTargetSkills] = useState<string[]>([]);
  const [newSkill, setNewSkill] = useState("");
  const [minScore, setMinScore] = useState(70);

  const fileInputRef = useRef<HTMLInputElement>(null);

  const loadCvs = () => {
    api
      .get<CV[]>("/api/v1/cvs")
      .then((data) => {
        if (Array.isArray(data)) {
          setCvList(data);
          const active = data.find((c) => c.is_active) || data[0] || null;
          setActiveCv(active);
        }
      })
      .catch(() => {});
  };

  const loadPreferences = () => {
    api
      .get<Preferences>("/api/v1/preferences")
      .then((data) => {
        if (data) {
          setTargetTitles(data.desired_titles || []);
          setTargetSkills(data.keywords_include || []);
          setMinScore(data.min_match_score || 70);
        }
      })
      .catch(() => {});
  };

  useEffect(() => {
    loadCvs();
    loadPreferences();
  }, []);

  const handleFileUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    if (e.target.files && e.target.files[0]) {
      const file = e.target.files[0];
      setIsUploading(true);
      onShowToast(`${file.name} yükleniyor ve metin ayrıştırılıyor...`);

      const formData = new FormData();
      formData.append("file", file);

      try {
        await api.upload<CV>("/api/v1/cvs", formData);
        onShowToast(`${file.name} başarıyla yüklendi.`);
        loadCvs();
      } catch {
        onShowToast("CV yükleme işlemi başarısız oldu.");
      } finally {
        setIsUploading(false);
        if (fileInputRef.current) fileInputRef.current.value = "";
      }
    }
  };

  const handleActivateCv = async (cvId: string) => {
    try {
      await api.post(`/api/v1/cvs/${cvId}/activate`);
      onShowToast("Aktif CV güncellendi.");
      loadCvs();
    } catch {
      onShowToast("Aktif CV seçilemedi.");
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
    if (!targetSkills.includes(val)) {
      setTargetSkills([...targetSkills, val]);
    }
    setNewSkill("");
  };

  const handleRemoveSkill = (skillToRemove: string) => {
    setTargetSkills(targetSkills.filter((s) => s !== skillToRemove));
  };

  const handleSavePreferences = async () => {
    setIsSavingPrefs(true);
    try {
      await api.put("/api/v1/preferences", {
        desired_titles: targetTitles,
        keywords_include: targetSkills,
        min_match_score: minScore,
      });
      onShowToast("Kariyer hedefleri ve yetenek tercihleri güncellendi.");
    } catch {
      onShowToast("Tercihler kaydedilemedi.");
    } finally {
      setIsSavingPrefs(false);
    }
  };

  const handleReanalyze = async () => {
    setIsReanalyzing(true);
    onShowToast("CV uyum analiz motoru başlatılıyor (Son 30 gün)...");
    try {
      await api.post("/api/v1/analysis/reanalyze", { days: 30 });
      onShowToast("Yeniden analiz başarıyla başlatıldı. Sonuçlar listeye yansıtılacak.");
    } catch {
      onShowToast("Analiz başlatılamadı.");
    } finally {
      setIsReanalyzing(false);
    }
  };

  return (
    <div id="tab-cv" className="tab-pane space-y-6">
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        {/* Left: Upload & Active CV (5 cols) */}
        <div className="lg:col-span-5 space-y-6">
          <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-5">
            <div className="flex items-center justify-between pb-3 border-b border-white/10 font-mono">
              <span className="text-sm font-bold text-white uppercase">AKTİF YÖNETİCİ CV&apos;Sİ</span>
              <span className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
                {activeCv ? "YÜKLENDİ" : "CV BEKLENİYOR"}
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
                <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4" />
                <polyline points="17 8 12 3 7 8" />
                <line x1="12" y1="3" x2="12" y2="15" />
              </svg>
              <p className="text-xs font-mono text-white/80 font-bold">
                {isUploading ? "Yükleniyor..." : "Yeni CV Dosyası Yükle"}
              </p>
              <p className="text-[10px] text-white/40 mt-1 font-mono">
                PDF veya DOCX formatında (Azami 10MB)
              </p>
              <input
                ref={fileInputRef}
                type="file"
                accept=".pdf,.docx,.doc"
                onChange={handleFileUpload}
                className="hidden"
              />
            </div>

            {/* Active CV Info */}
            <div className="p-4 rounded-xl bg-white/[0.03] border border-white/10 font-mono text-xs space-y-2">
              <div className="text-[10px] text-white/40 uppercase">Aktif Profil</div>
              <div className="text-sm font-bold text-white truncate">
                {activeCv?.filename || "Henüz aktif bir CV yüklenmedi"}
              </div>
              {activeCv?.created_at && (
                <div className="text-[10px] text-white/50">
                  Yükleme Tarihi: {new Date(activeCv.created_at).toLocaleDateString("tr-TR")}
                </div>
              )}
            </div>

            {/* Previous CVs List */}
            {cvList.length > 1 && (
              <div className="space-y-2 font-mono text-xs">
                <div className="text-[10px] text-white/40 uppercase">Tüm Yüklenen CV&apos;ler</div>
                <div className="space-y-1.5 max-h-40 overflow-y-auto">
                  {cvList.map((cv) => (
                    <div
                      key={cv.id}
                      className="flex items-center justify-between p-2 rounded-lg bg-white/[0.02] border border-white/5"
                    >
                      <span className="truncate pr-2 text-white/80">{cv.filename}</span>
                      {cv.is_active ? (
                        <span className="text-[9px] text-emerald-400 font-bold uppercase">Aktif</span>
                      ) : (
                        <button
                          type="button"
                          onClick={() => handleActivateCv(cv.id)}
                          className="text-[9px] text-white/60 hover:text-white underline uppercase"
                        >
                          Seç
                        </button>
                      )}
                    </div>
                  ))}
                </div>
              </div>
            )}

            <button
              type="button"
              onClick={handleReanalyze}
              disabled={isReanalyzing || !activeCv}
              className="silver-btn lux-press w-full py-3 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center justify-center gap-2 text-white disabled:opacity-50"
            >
              <span>{isReanalyzing ? "Analiz Ediliyor..." : "Tüm İlanları Yeniden Analiz Et"}</span>
            </button>
          </div>
        </div>

        {/* Right: Preferences, Target Titles & Skills (7 cols) */}
        <div className="lg:col-span-7 space-y-6">
          <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-6">
            <div className="flex items-center justify-between pb-3 border-b border-white/10 font-mono">
              <span className="text-sm font-bold text-white uppercase">HEDEF ROLLER &amp; YETENEKLER</span>
              <span className="text-[10px] text-white/50">Eşleştirme Filtreleri</span>
            </div>

            {/* Target Titles */}
            <div className="space-y-3 font-mono text-xs">
              <label className="block text-[10px] text-white/60 uppercase">
                Hedef Pozisyon Başlıkları
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newTitle}
                  onChange={(e) => setNewTitle(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddTitle()}
                  placeholder="Örn: Staff Engineer, AI Architect"
                  className="flex-1 bg-[#040405] border border-white/20 rounded-xl px-4 py-2.5 text-xs text-white focus:border-white focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleAddTitle}
                  className="lux-press px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold"
                >
                  Ekle
                </button>
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                {targetTitles.map((t) => (
                  <span
                    key={t}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-white/10 text-white border border-white/20 text-xs"
                  >
                    <span>{t}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveTitle(t)}
                      className="text-white/40 hover:text-white font-bold ml-1"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* Target Skills */}
            <div className="space-y-3 font-mono text-xs pt-4 border-t border-white/10">
              <label className="block text-[10px] text-white/60 uppercase">
                Öncelikli Teknik Yetkinlikler
              </label>
              <div className="flex gap-2">
                <input
                  type="text"
                  value={newSkill}
                  onChange={(e) => setNewSkill(e.target.value)}
                  onKeyDown={(e) => e.key === "Enter" && handleAddSkill()}
                  placeholder="Örn: Next.js, FastAPI, PyTorch"
                  className="flex-1 bg-[#040405] border border-white/20 rounded-xl px-4 py-2.5 text-xs text-white focus:border-white focus:outline-none"
                />
                <button
                  type="button"
                  onClick={handleAddSkill}
                  className="lux-press px-4 py-2.5 rounded-xl bg-white/10 hover:bg-white/20 text-white font-bold"
                >
                  Ekle
                </button>
              </div>

              <div className="flex flex-wrap gap-2 pt-1">
                {targetSkills.map((sk) => (
                  <span
                    key={sk}
                    className="flex items-center gap-1.5 px-3 py-1 rounded-full bg-emerald-500/10 text-emerald-300 border border-emerald-500/20 text-xs"
                  >
                    <span>{sk}</span>
                    <button
                      type="button"
                      onClick={() => handleRemoveSkill(sk)}
                      className="text-emerald-400/40 hover:text-emerald-300 font-bold ml-1"
                    >
                      ×
                    </button>
                  </span>
                ))}
              </div>
            </div>

            {/* Minimum Match Score */}
            <div className="space-y-3 font-mono text-xs pt-4 border-t border-white/10">
              <div className="flex items-center justify-between">
                <label className="text-[10px] text-white/60 uppercase">
                  Asgari Uyum Skoru Filtresi
                </label>
                <span className="text-white font-bold">%{minScore}</span>
              </div>
              <input
                type="range"
                min={0}
                max={100}
                step={5}
                value={minScore}
                onChange={(e) => setMinScore(Number(e.target.value))}
                className="w-full accent-white"
              />
            </div>

            <div className="pt-2">
              <button
                type="button"
                onClick={handleSavePreferences}
                disabled={isSavingPrefs}
                className="silver-btn lux-press px-6 py-2.5 rounded-xl text-xs font-mono uppercase tracking-wider text-white disabled:opacity-50"
              >
                <span>{isSavingPrefs ? "Kaydediliyor..." : "Tercihleri Kaydet"}</span>
              </button>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
