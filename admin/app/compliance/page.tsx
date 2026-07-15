"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { apiPost, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { AuditEntry, ConsentLog, RetentionQueue } from "@/lib/types";

export default function CompliancePage() {
  const consents = useApi<ConsentLog[]>("/api/admin/consent-logs?limit=100");
  const queue = useApi<RetentionQueue>("/api/admin/retention-queue");
  const audit = useApi<AuditEntry[]>("/api/admin/audit-log?limit=100");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function runRetention() {
    if (!window.confirm("Run PDPP retention scrub now? This anonymizes eligible riders."))
      return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const res = await apiPost<{ scrubbed: number }>("/api/admin/retention/run-now");
      setMsg(`Scrubbed ${res.scrubbed} rider(s).`);
      queue.reload(); audit.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  async function runAllJobs() {
    if (!window.confirm("Run all daily maintenance jobs now?")) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await apiPost<{ riders_scrubbed: number; bookings_flagged: number; memberships_expired: number }>(
        "/api/admin/scheduled-jobs/run-now");
      setMsg(`Done — scrubbed ${r.riders_scrubbed} rider(s), flagged ${r.bookings_flagged} booking(s), expired ${r.memberships_expired} membership(s).`);
      queue.reload(); audit.reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Compliance">
      {err && <div className="error">{err}</div>}
      {msg && <div className="muted">{msg}</div>}

      <h2>Daily maintenance jobs</h2>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Runs automatically every 24h (retention scrub, stale-unconfirmed sweep,
          membership expiry). Trigger a run on demand:
        </p>
        <button className="btn" disabled={busy} onClick={runAllJobs}>
          Run all jobs now
        </button>
      </div>

      <h2 style={{ marginTop: "1.75rem" }}>PDPP retention</h2>
      <div className="card">
        <p className="muted" style={{ marginTop: 0 }}>
          Riders eligible for anonymization (activity older than the retention window,
          no open dispute):
        </p>
        <div className="btn-row" style={{ alignItems: "center" }}>
          <strong style={{ fontSize: "1.4rem", color: "var(--navy)" }}>
            {queue.data?.count ?? "…"}
          </strong>
          <span className="muted">
            cutoff {queue.data ? fmtDate(queue.data.cutoff) : "…"}
          </span>
          <button className="btn danger sm" disabled={busy} onClick={runRetention}>
            Run retention now
          </button>
        </div>
      </div>

      <h2 style={{ marginTop: "1.75rem" }}>Consent log</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Rider</th><th>Booking</th><th>Type</th><th>IP</th><th>When</th></tr></thead>
          <tbody>
            {(consents.data || []).map((c) => (
              <tr key={c.id}>
                <td>#{c.id}</td><td>#{c.rider_id}</td><td>#{c.booking_id}</td>
                <td>{c.consent_type}</td><td>{c.ip_address || "—"}</td>
                <td>{fmtDate(c.consented_at)}</td>
              </tr>
            ))}
            {(consents.data || []).length === 0 && <tr><td colSpan={6} className="muted">No consent logs.</td></tr>}
          </tbody>
        </table>
      </div>

      <h2 style={{ marginTop: "1.75rem" }}>Audit log</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Admin</th><th>Action</th><th>Target</th><th>When</th></tr></thead>
          <tbody>
            {(audit.data || []).map((a) => (
              <tr key={a.id}>
                <td>#{a.id}</td>
                <td>{a.admin_id ? `#${a.admin_id}` : "system"}</td>
                <td>{a.action}</td>
                <td>{a.target_type ? `${a.target_type}${a.target_id ? " #" + a.target_id : ""}` : "—"}</td>
                <td>{fmtDate(a.created_at)}</td>
              </tr>
            ))}
            {(audit.data || []).length === 0 && <tr><td colSpan={5} className="muted">No audit entries.</td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
