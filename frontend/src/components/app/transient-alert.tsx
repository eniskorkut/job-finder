"use client";

import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/alert";

/**
 * A confirmation that leaves softly: the exit is shorter than the enter and
 * uses a small fixed offset so it doesn't steal attention while the user
 * moves on.
 */
export function TransientAlert({
  tone,
  title,
  children,
  duration = 3200,
}: {
  tone: "info" | "success" | "warning" | "danger";
  title: string;
  children?: React.ReactNode;
  duration?: number;
}) {
  const [phase, setPhase] = useState<"visible" | "exiting" | "gone">("visible");

  useEffect(() => {
    const timer = setTimeout(() => setPhase("exiting"), duration);
    return () => clearTimeout(timer);
  }, [duration]);

  useEffect(() => {
    if (phase !== "exiting") return;
    const timer = setTimeout(() => setPhase("gone"), 160);
    return () => clearTimeout(timer);
  }, [phase]);

  if (phase === "gone") return null;

  return (
    <div
      className={phase === "exiting" ? "exiting" : undefined}
      style={{ transitionTimingFunction: "var(--ease-out)" }}
    >
      <Alert tone={tone} title={title}>
        {children}
      </Alert>
    </div>
  );
}
