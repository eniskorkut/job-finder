"use client";

import React, { useState, useEffect, useRef } from "react";

interface TabSyncProps {
  onShowToast: (msg: string) => void;
  triggerScanToken?: number;
}

interface LogEntry {
  time: string;
  text: string;
  isVip?: boolean;
}

const INITIAL_LOGS: LogEntry[] = [
  { time: "18:24:00", text: "Sistem başlatıldı. Çekirdek motorlar bağlı." },
  { time: "18:24:02", text: "Özel kariyer siteleri ve ATS tarama servisi yanıt verdi: 200 OK." },
  { time: "18:24:05", text: "LinkedIn e-posta besleme kuyruğu tarandı (18 ilan yakalandı)." },
  { time: "18:24:08", text: "Merkezi yapay zekâ eşleştirme skoru hesaplaması tamamlandı." },
  {
    time: "18:24:10",
    text: "VIP Telegram kanalına (@eniskorkut_vip) 3 yeni öncelikli iş fırsatı iletildi.",
    isVip: true,
  },
];

const SCAN_SEQUENCE = [
  "Web & ATS Crawler başlatılıyor (Önbellek temizlendi)...",
  "Greenhouse ATS: London AI Hub sorgulanıyor (14 pozisyon)...",
  "Lever.co: San Francisco & Paris kuruluşları yoklanıyor...",
  "Ashby: Anthropic ve Linear ekosistem partnerleri doğrulandı...",
  "LinkedIn InMail gelen kutusu ayrıştırılıyor...",
  "Merkezi yapay zekâ motoru ile 103 ilan için kıdem ve yetenek matrisi hesaplandı.",
  'Sonuç: %98.4 uyumlu "Lead AI Systems Architect" en üst sıraya yerleşti.',
  "VIP Telegram kanalına bildirim gönderildi. Tarama başarıyla sonlandı.",
];

export function TabSync({ onShowToast, triggerScanToken }: TabSyncProps) {
  const [isScanning, setIsScanning] = useState(false);
  const [scanStatus, setScanStatus] = useState("BEKLEMEDE // HAZIR");
  const [lastSyncTime, setLastSyncTime] = useState("18:24:10");
  const [logs, setLogs] = useState<LogEntry[]>(INITIAL_LOGS);
  const terminalRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (triggerScanToken && triggerScanToken > 0) {
      handleStartScan();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerScanToken]);

  useEffect(() => {
    if (terminalRef.current) {
      terminalRef.current.scrollTop = terminalRef.current.scrollHeight;
    }
  }, [logs]);

  const handleStartScan = () => {
    if (isScanning) return;
    setIsScanning(true);
    setScanStatus("TARANIYOR...");
    onShowToast("Canlı küresel radar taraması başlatıldı...");

    let idx = 0;
    const interval = setInterval(() => {
      if (idx < SCAN_SEQUENCE.length) {
        const line = SCAN_SEQUENCE[idx];
        const nowTime = new Date().toLocaleTimeString();
        setLogs((prev) => [...prev, { time: nowTime, text: line }]);
        idx++;
      } else {
        clearInterval(interval);
        setIsScanning(false);
        setScanStatus("SENKRONİZE // TAMAMLANDI");
        const finishedTime = new Date().toLocaleTimeString();
        setLastSyncTime(finishedTime);
        onShowToast("Küresel tarama tamamlandı! 14 yeni liderlik fırsatı güncellendi.");
      }
    }, 700);
  };

  return (
    <div id="tab-sync" className="tab-pane space-y-6">
      {/* Sync Controls & Metrics */}
      <div className="carbon-card rounded-3xl p-6 md:p-8 space-y-6">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-6 border-b border-white/15">
          <div>
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-emerald-400 animate-ping" />
              <h2 className="text-xl font-bold font-mono text-white tracking-wide">
                CANLI SENKRONİZASYON &amp; RADAR LOGLARI
              </h2>
            </div>
            <p className="text-xs text-white/50 font-mono mt-1">
              LinkedIn E-posta, Özel Web Kaynakları, Greenhouse ve Lever ağları anlık olarak taranır.
            </p>
          </div>

          <button
            type="button"
            onClick={handleStartScan}
            disabled={isScanning}
            className="silver-btn lux-press px-6 py-3 rounded-xl text-xs font-mono uppercase tracking-wider flex items-center gap-2 disabled:opacity-50"
          >
            <svg className="w-4 h-4" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2">
              <polygon points="5 3 19 12 5 21 5 3" />
            </svg>
            <span>{isScanning ? "TARAMA SÜRÜYOR..." : "MANUEL TARAMAYI ŞİMDİ BAŞLAT"}</span>
          </button>
        </div>

        {/* Telemetry Stats Cards */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 font-mono text-xs">
          <div className="p-4 rounded-2xl bg-[#040405] border border-white/10">
            <div className="text-white/40 uppercase text-[10px]">Taranan Kaynak</div>
            <div className="text-2xl font-bold text-white mt-1">8 Ağ</div>
            <div className="text-[10px] text-emerald-400 mt-0.5">Tüm Kanallar Açık</div>
          </div>
          <div className="p-4 rounded-2xl bg-[#040405] border border-white/10">
            <div className="text-white/40 uppercase text-[10px]">Bugün İncelenen</div>
            <div className="text-2xl font-bold text-white mt-1">1,420 İlan</div>
            <div className="text-[10px] text-white/60 mt-0.5">Global Veri Akışı</div>
          </div>
          <div className="p-4 rounded-2xl bg-[#040405] border border-white/10">
            <div className="text-white/40 uppercase text-[10px]">Kusursuz Uyum (&gt;%90)</div>
            <div className="text-2xl font-bold text-white mt-1">24 Pozisyon</div>
            <div className="text-[10px] text-emerald-400 mt-0.5">VIP Listeye Alındı</div>
          </div>
          <div className="p-4 rounded-2xl bg-[#040405] border border-white/10">
            <div className="text-white/40 uppercase text-[10px]">Son Senkronizasyon</div>
            <div className="text-2xl font-bold text-white mt-1">{lastSyncTime}</div>
            <div className="text-[10px] text-white/40 mt-0.5">Otomatik Döngüde</div>
          </div>
        </div>

        {/* Live Terminal Stream */}
        <div className="rounded-2xl bg-[#020203] border border-white/15 p-4 md:p-6 font-mono text-xs space-y-2">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 text-[11px] text-white/40">
            <span>TELEMETRİ TERMİNALİ // RADAR STREAM STDOUT</span>
            <span
              className={`font-bold ${
                isScanning
                  ? "text-amber-400 animate-pulse"
                  : scanStatus.includes("TAMAMLANDI")
                  ? "text-emerald-400"
                  : "text-emerald-400"
              }`}
            >
              {scanStatus}
            </span>
          </div>

          <div
            ref={terminalRef}
            className="h-64 overflow-y-auto space-y-1.5 text-white/70 text-[11px] leading-relaxed pt-2"
          >
            {logs.map((entry, i) => (
              <div key={i} className="animate-fade-in text-white/90">
                <span className="text-white/30">[{entry.time}]</span>{" "}
                {entry.isVip ? (
                  <span>
                    VIP Telegram kanalına (<span className="text-emerald-400">@eniskorkut_vip</span>) 3 yeni öncelikli
                    iş fırsatı iletildi.
                  </span>
                ) : (
                  <span>{entry.text}</span>
                )}
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
