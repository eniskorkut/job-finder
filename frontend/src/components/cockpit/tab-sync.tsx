"use client";

import React, { useState, useEffect, useRef, useCallback } from "react";
import { api } from "@/lib/api";
import type { SyncJobProgress } from "@/lib/types";

interface TabSyncProps {
  onShowToast: (msg: string) => void;
  triggerScanToken?: number;
}

interface LogEntry {
  time: string;
  text: string;
  isVip?: boolean;
}

export function TabSync({ onShowToast, triggerScanToken }: TabSyncProps) {
  const [isScanning, setIsScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState("BEKLEMEDE // HAZIR");
  const [lastSyncTime, setLastSyncTime] = useState("-");
  const [activeJobId, setActiveJobId] = useState<string | null>(null);
  const [logs, setLogs] = useState<LogEntry[]>([
    {
      time: new Date().toLocaleTimeString(),
      text: "Sistem hazır. Gerçek zamanlı senkronizasyon servisi bağlandı.",
    },
  ]);
  const terminalRef = useRef<HTMLDivElement>(null);
  const pollTimerRef = useRef<NodeJS.Timeout | null>(null);

  const addLog = useCallback((text: string, isVip = false) => {
    const time = new Date().toLocaleTimeString();
    setLogs((prev) => [...prev, { time, text, isVip }]);
  }, []);

  const stopPolling = useCallback(() => {
    if (pollTimerRef.current) {
      clearInterval(pollTimerRef.current);
      pollTimerRef.current = null;
    }
  }, []);

  const pollJob = useCallback(
    (jobId: string) => {
      let lastStage = "";
      pollTimerRef.current = setInterval(async () => {
        try {
          const data = await api.get<SyncJobProgress>(`/api/v1/sync/jobs/${jobId}`);
          if (!data || !data.job) return;
          const job = data.job;
          const stage = (job.payload?.stage as string) || job.status;

          if (stage && stage !== lastStage) {
            lastStage = stage;
            addLog(`Aşama: ${stage} (Durum: ${job.status})`);
          }

          if (job.status === "completed") {
            stopPolling();
            setIsScanning(false);
            setScanStatus("SENKRONİZE // TAMAMLANDI");
            const finishedTime = new Date().toLocaleTimeString();
            setLastSyncTime(finishedTime);
            addLog(
              `Tarama başarıyla tamamlandı! ${job.jobs_found ?? 0} ilan tespit edildi, ${job.jobs_new ?? 0} yeni ilan eklendi.`
            );
            onShowToast("Küresel tarama başarıyla tamamlandı!");
          } else if (job.status === "failed") {
            stopPolling();
            setIsScanning(false);
            setScanStatus("HATA");
            addLog(`Tarama hatası: ${job.error_message || "Bilinmeyen sunucu hatası"}`);
            onShowToast("Tarama işlemi başarısız oldu.");
          }
        } catch {
          // Poll error, retry next tick
        }
      }, 1500);
    },
    [addLog, onShowToast, stopPolling]
  );

  const handleStartScan = useCallback(async () => {
    if (isScanning) return;
    setIsScanning(true);
    setScanStatus("KUYRUĞA ALINIYOR...");
    addLog("Merkezi tarama görevi kuyruğa alınıyor...");
    onShowToast("Canlı tarama başlatılıyor...");

    try {
      const res = await api.post<{ id?: string; job_id?: string }>("/api/v1/sync/run");
      const id = res?.id || res?.job_id;
      if (id) {
        setActiveJobId(id);
        setScanStatus("İŞLENİYOR...");
        addLog(`Arka plan işçisi görevi devraldı (Job ID: ${id.slice(0, 8)}...)`);
        pollJob(id);
      } else {
        throw new Error("Job ID alınamadı");
      }
    } catch {
      setIsScanning(false);
      setScanStatus("BAŞLATILAMADI");
      addLog("Tarama kuyruğa alınamadı. Arka plan servislerini kontrol edin.");
      onShowToast("Tarama başlatılamadı.");
    }
  }, [addLog, isScanning, onShowToast, pollJob]);

  useEffect(() => {
    if (triggerScanToken && triggerScanToken > 0) {
      handleStartScan();
    }
  }, [triggerScanToken, handleStartScan]);

  useEffect(() => {
    return () => {
      stopPolling();
    };
  }, [stopPolling]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div id="tab-sync" className="tab-pane space-y-6">
      {/* Sync Controls & Metrics */}
      <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-white/15">
          <div>
            <div className="flex items-center gap-2.5">
              <span
                className={`w-2.5 h-2.5 rounded-full ${
                  isScanning ? "bg-emerald-400 animate-ping" : "bg-white"
                }`}
              />
              <h2 className="text-xl font-bold font-mono text-white tracking-wide">
                GERÇEK ZAMANLI SENKRONİZASYON &amp; RADAR LOGLARI
              </h2>
            </div>
            <p className="text-xs text-white/50 font-mono mt-1">
              LinkedIn E-posta, Özel Web Kaynakları, Greenhouse ve Lever ağları dayanıklı arka plan işçisiyle taranır.
            </p>
          </div>

          <button
            type="button"
            onClick={handleStartScan}
            disabled={isScanning}
            className="silver-btn lux-press px-6 py-3 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center justify-center gap-2 text-white self-start md:self-auto disabled:opacity-50"
          >
            <span>{isScanning ? "Taranıyor..." : "Taramayı Başlat"}</span>
            <svg
              className={`w-4 h-4 ${isScanning ? "animate-spin" : ""}`}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
            >
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
          </button>
        </div>

        {/* Status Metrics Bar */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 font-mono text-xs">
          <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/10">
            <span className="text-[10px] text-white/40 uppercase block mb-1">DURUM</span>
            <span
              className={`font-bold uppercase text-[11px] ${
                isScanning ? "text-emerald-400" : "text-white"
              }`}
            >
              {scanStatus}
            </span>
          </div>

          <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/10">
            <span className="text-[10px] text-white/40 uppercase block mb-1">SON SENKRON</span>
            <span className="text-white font-bold text-[11px]">{lastSyncTime}</span>
          </div>

          <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/10">
            <span className="text-[10px] text-white/40 uppercase block mb-1">AKTİF İŞ ID</span>
            <span className="text-white/80 font-bold text-[11px] truncate block">
              {activeJobId ? `${activeJobId.slice(0, 8)}...` : "Yok"}
            </span>
          </div>

          <div className="p-3.5 rounded-2xl bg-white/[0.02] border border-white/10">
            <span className="text-[10px] text-white/40 uppercase block mb-1">GÜVENLİK</span>
            <span className="text-emerald-400 font-bold text-[11px]">SSRF / WAL KORUMALI</span>
          </div>
        </div>

        {/* Live Terminal Output */}
        <div className="space-y-2">
          <div className="flex items-center justify-between text-xs font-mono text-white/50 px-1">
            <span>TERMINAL AKIŞI</span>
            <span>UTF-8 // CANLI İŞÇİ GÜNLÜĞÜ</span>
          </div>

          <div
            ref={terminalRef}
            className="w-full h-80 bg-[#020203] border border-white/15 rounded-2xl p-4 md:p-6 overflow-y-auto font-mono text-xs space-y-2 text-white/80 leading-relaxed shadow-inner"
          >
            {logs.map((log, idx) => (
              <div key={idx} className="flex items-start gap-2.5">
                <span className="text-white/30 shrink-0 select-none">[{log.time}]</span>
                <span className={log.isVip ? "text-emerald-400 font-bold" : "text-white/80"}>
                  {log.text}
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
