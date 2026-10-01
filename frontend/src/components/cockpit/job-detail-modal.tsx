"use client";

import React, { useState, useEffect, useRef } from "react";
import { Dossier } from "./types";

interface JobDetailModalProps {
  job: Dossier | null;
  isOpen: boolean;
  onClose: () => void;
  onShowToast: (msg: string) => void;
}

function generateExecutiveCoverLetter(job: Dossier): string {
  const topSkills =
    job.skills && job.skills.length > 0
      ? job.skills.slice(0, 3).join(", ")
      : "Dağıtık Sistemler ve Yapay Zekâ";

  return `Sayın ${job.company} İşe Alım & Yönetici Komitesi,

${job.location} menşeili "${job.title}" pozisyonu için 9+ yıllık üst düzey sistem tasarımı, dağıtık mikroservisler ve yapay zekâ otonom ajanları tecrübemle başvurumu sunmaktan kıvanç duyarım.

CV'mde ayrıntılandırıldığı üzere, özellikle ${topSkills} alanındaki çekirdek mimari liderliğim, şirketin yüksek ölçekli stratejik vizyonuyla birebir örtüşmektedir.

Pozisyonun gerektirdiği sorumlulukları ve şirketinizin global vizyonuna sunabileceğim katma değeri aktarmak üzere bir araya gelmekten memnuniyet duyarım.

Saygılarımla,
Enis Korkut
Sistem & Yazılım Mimarı`;
}

export function JobDetailModal({ job, isOpen, onClose, onShowToast }: JobDetailModalProps) {
  const [coverLetter, setCoverLetter] = useState("");
  const typingTimerRef = useRef<NodeJS.Timeout | null>(null);

  useEffect(() => {
    if (isOpen && job) {
      startTypewriter(job);
    } else {
      if (typingTimerRef.current) clearInterval(typingTimerRef.current);
      setCoverLetter("");
    }
    return () => {
      if (typingTimerRef.current) clearInterval(typingTimerRef.current);
    };
  }, [isOpen, job]);

  const startTypewriter = (targetJob: Dossier) => {
    if (typingTimerRef.current) clearInterval(typingTimerRef.current);
    const fullText = generateExecutiveCoverLetter(targetJob);
    setCoverLetter("");
    let charIdx = 0;

    typingTimerRef.current = setInterval(() => {
      if (charIdx < fullText.length) {
        setCoverLetter((prev) => prev + fullText[charIdx]);
        charIdx++;
      } else {
        if (typingTimerRef.current) clearInterval(typingTimerRef.current);
      }
    }, 10);
  };

  const handleRegenerate = () => {
    if (!job) return;
    startTypewriter(job);
    onShowToast("Yapay zekâ mektubu yeniden yazıldı.");
  };

  const handleCopy = () => {
    navigator.clipboard
      .writeText(coverLetter)
      .then(() => {
        onShowToast("Kapak mektubu panoya kopyalandı.");
      })
      .catch(() => {
        onShowToast("Kopyalama yetkisi verilemedi.");
      });
  };

  const handleSubmit = () => {
    onClose();
    onShowToast(`Başvuru başarıyla kaydedildi: ${job?.title || "Öncelikli Başvuru"}`);
  };

  if (!isOpen || !job) return null;

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
        <div className="flex items-center justify-between pb-4 border-b border-white/15 font-mono">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-white shadow-[0_0_8px_#ffffff]" />
            <span className="text-sm font-bold text-white uppercase">YÖNETİCİ BAŞVURU &amp; AI ÖN YAZI KONSOLU</span>
          </div>
          <button
            type="button"
            onClick={onClose}
            className="text-white/50 hover:text-white text-lg font-bold"
          >
            ×
          </button>
        </div>

        <div className="space-y-4 font-mono text-xs">
          <div>
            <div className="text-[10px] text-white/40 uppercase">Hedef Pozisyon &amp; Şirket</div>
            <div className="text-lg font-bold text-white mt-0.5">{job.title}</div>
            <div className="text-white/70">
              {job.company} • {job.location} • {job.salary}
            </div>
          </div>

          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-white/60 uppercase text-[11px]">
                Özelleştirilmiş AI Kapak Mektubu (Executive Pitch)
              </span>
              <button
                type="button"
                onClick={handleRegenerate}
                className="text-emerald-400 hover:underline text-[10px] cursor-pointer"
              >
                Yeniden Oluştur ↺
              </button>
            </div>
            <textarea
              rows={10}
              value={coverLetter}
              onChange={(e) => setCoverLetter(e.target.value)}
              className="w-full bg-[#040405] border border-white/20 rounded-xl p-4 text-xs font-sans text-white/90 leading-relaxed focus:border-white focus:outline-none"
            />
          </div>

          <div className="flex flex-col sm:flex-row items-center gap-3 pt-2">
            <button
              type="button"
              onClick={handleCopy}
              className="lux-press w-full sm:w-auto px-5 py-3 rounded-xl bg-white/10 hover:bg-white/20 text-white font-mono text-xs font-bold flex items-center justify-center gap-2"
            >
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <rect width="14" height="14" x="8" y="8" rx="2" ry="2" />
                <path d="M4 16c-1.1 0-2-.9-2-2V4c0-1.1.9-2 2-2h10c1.1 0 2 .9 2 2" />
              </svg>
              <span>Panoya Kopyala</span>
            </button>
            <button
              type="button"
              onClick={handleSubmit}
              className="silver-btn lux-press flex-1 w-full py-3 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center justify-center gap-2"
            >
              <span>Başvuru Mandasını Kaydet &amp; Gönder</span>
              <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M5 12h14M12 5l7 7-7 7" />
              </svg>
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}
