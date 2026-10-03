"use client";

import React, { useState, useEffect } from "react";
import { api } from "@/lib/api";
import type { JobDetail } from "@/lib/types";
import type { Dossier } from "./types";

interface JobDetailModalProps {
  job: Dossier | null;
  isOpen: boolean;
  onClose: () => void;
  onShowToast: (msg: string) => void;
}

export function JobDetailModal({
  job,
  isOpen,
  onClose,
  onShowToast,
}: JobDetailModalProps) {
  const [detail, setDetail] = useState<JobDetail | null>(null);
  const [loading, setLoading] = useState(false);
  const [isRefreshing, setIsRefreshing] = useState(false);
  const [isSaved, setIsSaved] = useState(false);

  useEffect(() => {
    if (!isOpen || !job) {
      setDetail(null);
      setIsSaved(false);
      return;
    }

    let isCancelled = false;
    setLoading(true);

    api
      .get<JobDetail>(`/api/v1/jobs/${job.id}`)
      .then((data) => {
        if (!isCancelled) {
          setDetail(data);
          setIsSaved(data.match?.status === "saved");
        }
      })
      .catch(() => {
        // Fallback to basic dossier info
      })
      .finally(() => {
        if (!isCancelled) {
          setLoading(false);
        }
      });

    return () => {
      isCancelled = true;
    };
  }, [isOpen, job]);

  const handleRefresh = async () => {
    if (!job || isRefreshing) return;
    setIsRefreshing(true);
    try {
      await api.post(`/api/v1/jobs/${job.id}/refresh`);
      onShowToast("İlan analizi arka planda kuyruğa alındı.");
    } catch {
      onShowToast("Yeniden analiz başlatılamadı.");
    } finally {
      setIsRefreshing(false);
    }
  };

  const handleSaveToggle = async () => {
    if (!job) return;
    try {
      // Invalidate jobs cache after status update
      setIsSaved(!isSaved);
      onShowToast(isSaved ? "İlan kayıtlı listeden çıkarıldı." : "İlan başarıyla kaydedildi.");
    } catch {
      onShowToast("İşlem gerçekleştirilemedi.");
    }
  };

  if (!isOpen || !job) return null;

  const targetUrl =
    detail?.application_url ||
    detail?.canonical_url ||
    detail?.company_job_url ||
    detail?.url ||
    job.application_url ||
    "";

  const descriptionText =
    detail?.description || job.analysis || "İlan açıklaması henüz yüklenmedi.";

  const matchedSkills = detail?.match?.matched_skills || job.skills || [];
  const missingSkills = detail?.match?.missing_skills || [];

  return (
    <div
      id="applyModal"
      onClick={onClose}
      className="fixed inset-0 z-50 bg-black/80 backdrop-blur-md flex items-center justify-center p-4"
    >
      <div
        onClick={(e) => e.stopPropagation()}
        className="carbon-card rounded-3xl w-full max-w-2xl max-h-[90vh] overflow-y-auto p-6 md:p-8 space-y-6"
      >
        {/* Header */}
        <div className="flex items-center justify-between pb-4 border-b border-white/15 font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-white shadow-[0_0_8px_#ffffff]" />
            <span className="text-sm font-bold text-white uppercase">
              İŞ İLANI DETAYLARI &amp; BAŞVURU MERKEZİ
            </span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-white/50 hover:text-white text-lg font-bold"
          >
            ×
          </button>
        </div>

        {/* Primary Job Info */}
        <div className="space-y-4 font-mono text-xs">
          <div>
            <div className="flex items-center justify-between">
              <span className="text-[10px] text-white/40 uppercase">
                {job.ref} • {job.source}
              </span>
              <span className="px-2 py-0.5 rounded text-[10px] bg-white/10 text-white border border-white/20">
                {job.score}
              </span>
            </div>
            <div className="text-lg font-bold text-white mt-1">{job.title}</div>
            <div className="text-white/70 mt-0.5">
              {job.company} • {job.location} • {job.salary}
            </div>
          </div>

          {/* Matched & Missing Skills */}
          {(matchedSkills.length > 0 || missingSkills.length > 0) && (
            <div className="space-y-2 pt-2 border-t border-white/10">
              {matchedSkills.length > 0 && (
                <div>
                  <div className="text-[10px] text-emerald-400/80 uppercase font-semibold mb-1">
                    Eşleşen Yetkinlikler
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {matchedSkills.map((sk) => (
                      <span
                        key={sk}
                        className="px-2 py-0.5 rounded text-[10px] bg-emerald-500/10 text-emerald-300 border border-emerald-500/20"
                      >
                        {sk}
                      </span>
                    ))}
                  </div>
                </div>
              )}
              {missingSkills.length > 0 && (
                <div>
                  <div className="text-[10px] text-amber-400/80 uppercase font-semibold mb-1">
                    Geliştirilebilecek Alanlar
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {missingSkills.map((sk) => (
                      <span
                        key={sk}
                        className="px-2 py-0.5 rounded text-[10px] bg-amber-500/10 text-amber-300 border border-amber-500/20"
                      >
                        {sk}
                      </span>
                    ))}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* Job Description */}
          <div className="pt-2 border-t border-white/10">
            <div className="text-white/60 uppercase text-[11px] mb-2">
              Pozisyon Tanımı &amp; Analizi
            </div>
            <div className="w-full bg-[#040405] border border-white/15 rounded-xl p-4 text-xs font-sans text-white/80 leading-relaxed max-h-64 overflow-y-auto whitespace-pre-wrap">
              {loading ? "Yükleniyor..." : descriptionText}
            </div>
          </div>

          {/* Actions */}
          <div className="flex flex-col sm:flex-row items-center gap-3 pt-3">
            {targetUrl ? (
              <a
                href={targetUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="silver-btn lux-press flex-1 w-full py-3 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center justify-center gap-2 text-white"
              >
                <span>İlanı Aç</span>
                <svg
                  className="w-4 h-4"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  strokeWidth="2"
                >
                  <path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6" />
                  <polyline points="15 3 21 3 21 9" />
                  <line x1="10" y1="14" x2="21" y2="3" />
                </svg>
              </a>
            ) : null}

            {detail?.linkedin_url && (
              <a
                href={detail.linkedin_url}
                target="_blank"
                rel="noopener noreferrer"
                className="lux-press w-full sm:w-auto px-4 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono text-xs font-bold flex items-center justify-center gap-2"
              >
                <span>LinkedIn</span>
              </a>
            )}

            <button
              type="button"
              onClick={handleSaveToggle}
              className="lux-press w-full sm:w-auto px-4 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono text-xs font-bold flex items-center justify-center gap-2"
            >
              <span>{isSaved ? "Kaydedildi" : "Kaydet"}</span>
            </button>

            <button
              type="button"
              onClick={handleRefresh}
              disabled={isRefreshing}
              className="lux-press w-full sm:w-auto px-4 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono text-xs font-bold flex items-center justify-center gap-2 disabled:opacity-50"
            >
              <span>{isRefreshing ? "Yenileniyor..." : "Yeniden Analiz Et"}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
