"use client";

import { clsx } from "clsx";

const STATUS_MAP: Record<string, string> = {
  settled: "badge-settled",
  failed: "badge-failed",
  collecting: "badge-collecting",
  scoring: "badge-scoring",
  escalating: "badge-escalating",
  routing: "badge-routing",
  created: "badge-created",
};

export function StatusBadge({ status }: { status: string }) {
  const cls = STATUS_MAP[status.toLowerCase()] ?? "bg-gray-800 text-gray-400 border border-gray-700";
  return (
    <span className={clsx("px-2 py-0.5 rounded text-xs font-mono uppercase tracking-wider", cls)}>
      {status}
    </span>
  );
}
