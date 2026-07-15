import React from "react";

export function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("en-GB", {
    day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit",
  });
}

export function gmd(v: string | number | null): string {
  if (v === null || v === undefined) return "—";
  return `D ${Number(v).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

const BADGE: Record<string, string> = {
  pending: "gray", posted: "blue", claimed: "orange", confirmed: "blue",
  completed: "green", no_show: "red", cancelled: "gray", fake_flagged: "red",
  unassigned: "orange", pending_review: "orange",
  verified: "green", rejected: "red", suspended: "red",
  active: "green", free_trial: "blue", expired: "gray",
  approved: "green", open: "orange", investigating: "orange", resolved: "green",
  new: "gray", standard: "blue", gold: "orange",
};

export function Badge({ value }: { value: string }) {
  const color = BADGE[value] || "gray";
  return <span className={`badge ${color}`}>{value.replace(/_/g, " ")}</span>;
}
