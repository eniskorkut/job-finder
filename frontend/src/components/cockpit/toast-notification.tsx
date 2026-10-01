"use client";

import React from "react";
import { ToastItem } from "./types";

interface ToastNotificationProps {
  toasts: ToastItem[];
  onDismiss?: (id: string) => void;
}

export function ToastNotificationContainer({ toasts }: ToastNotificationProps) {
  return (
    <div
      id="toastContainer"
      className="fixed bottom-6 right-6 z-50 space-y-2 pointer-events-none"
    >
      {toasts.map((toast) => (
        <div
          key={toast.id}
          className="pointer-events-auto px-4 py-3 rounded-2xl bg-black/90 backdrop-blur-xl border border-white/20 text-white font-mono text-xs shadow-2xl flex items-center gap-2.5 transition-all transform animate-fade-in"
        >
          <span className="w-2 h-2 rounded-full bg-emerald-400 shadow-[0_0_8px_#34d399] flex-shrink-0" />
          <span>{toast.message}</span>
        </div>
      ))}
    </div>
  );
}
