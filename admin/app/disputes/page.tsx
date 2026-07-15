"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { apiPost, useApi } from "@/lib/api";
import { Badge, fmtDate } from "@/lib/format";
import type { Dispute } from "@/lib/types";

const STATUSES = ["", "open", "investigating", "resolved"];

export default function DisputesPage() {
  const [status, setStatus] = useState("open");
  const qs = status ? `?dispute_status=${status}` : "";
  const { data, loading, error, reload } = useApi<Dispute[]>(
    `/api/admin/disputes${qs}`, [status]
  );
  const [selected, setSelected] = useState<Dispute | null>(null);

  return (
    <Shell title="Disputes">
      <div className="filters">
        <div className="field">
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => <option key={s} value={s}>{s || "All"}</option>)}
          </select>
        </div>
        <button className="btn ghost" onClick={reload}>Refresh</button>
      </div>

      {loading && <div className="spinner">Loading…</div>}
      {error && <div className="error">{error}</div>}
      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Booking</th><th>Raised by</th><th>Type</th>
                <th>Status</th><th>Created</th></tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id} className="clickable" onClick={() => setSelected(d)}>
                  <td>#{d.id}</td>
                  <td>#{d.booking_id}</td>
                  <td>{d.raised_by}</td>
                  <td>{d.type.replace(/_/g, " ")}</td>
                  <td><Badge value={d.status} /></td>
                  <td>{fmtDate(d.created_at)}</td>
                </tr>
              ))}
              {data.length === 0 && <tr><td colSpan={6} className="muted">No disputes.</td></tr>}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <ResolveDrawer dispute={selected} onClose={() => setSelected(null)}
          onDoneAction={() => { reload(); setSelected(null); }} />
      )}
    </Shell>
  );
}

function ResolveDrawer({ dispute, onClose, onDoneAction }: {
  dispute: Dispute; onClose: () => void; onDoneAction: () => void;
}) {
  const [resolution, setResolution] = useState(dispute.resolution || "");
  const [status, setStatus] = useState(
    dispute.status === "open" ? "resolved" : dispute.status
  );
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit() {
    setBusy(true); setErr(null);
    try {
      await apiPost(`/api/admin/disputes/${dispute.id}/resolve`, { resolution, status });
      onDoneAction();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2>Dispute #{dispute.id} <Badge value={dispute.status} /></h2>
        {err && <div className="error">{err}</div>}
        <dl className="kv">
          <dt>Booking</dt><dd>#{dispute.booking_id}</dd>
          <dt>Raised by</dt><dd>{dispute.raised_by}</dd>
          <dt>Type</dt><dd>{dispute.type.replace(/_/g, " ")}</dd>
          <dt>Description</dt><dd>{dispute.description || "—"}</dd>
        </dl>
        <h3>Resolve</h3>
        <div className="field" style={{ marginBottom: "0.75rem" }}>
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            <option value="investigating">investigating</option>
            <option value="resolved">resolved</option>
          </select>
        </div>
        <div className="field" style={{ marginBottom: "0.75rem" }}>
          <label>Resolution note</label>
          <input value={resolution} onChange={(e) => setResolution(e.target.value)} />
        </div>
        <button className="btn orange" disabled={busy || !resolution} onClick={submit}>
          {busy ? "Saving…" : "Save resolution"}
        </button>
      </div>
    </div>
  );
}
