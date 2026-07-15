"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { API_BASE, apiPost, getToken, useApi } from "@/lib/api";
import { Badge, fmtDate } from "@/lib/format";
import type { Rider } from "@/lib/types";

export default function RidersPage() {
  const { data, loading, error, reload } = useApi<Rider[]>("/api/admin/riders");
  const [selected, setSelected] = useState<Rider | null>(null);

  return (
    <Shell title="Riders">
      <button className="btn ghost" onClick={reload} style={{ marginBottom: "1rem" }}>
        Refresh
      </button>
      {loading && <div className="spinner">Loading…</div>}
      {error && <div className="error">{error}</div>}
      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Name</th><th>Phone</th><th>Blacklisted</th>
                <th>Fake reports</th><th>Joined</th></tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id} className="clickable" onClick={() => setSelected(r)}>
                  <td>#{r.id}</td>
                  <td>{r.name}</td>
                  <td>{r.phone}</td>
                  <td>{r.blacklisted ? <Badge value="blacklisted" /> : "—"}</td>
                  <td>{r.fake_report_count}</td>
                  <td>{fmtDate(r.created_at)}</td>
                </tr>
              ))}
              {data.length === 0 && <tr><td colSpan={6} className="muted">No riders.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
      {selected && (
        <RiderDrawer riderId={selected.id} onClose={() => setSelected(null)} onChanged={reload} />
      )}
    </Shell>
  );
}

function RiderDrawer({ riderId, onClose, onChanged }: {
  riderId: number; onClose: () => void; onChanged: () => void;
}) {
  const { data: r, reload } = useApi<Rider>(`/api/admin/riders/${riderId}`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [msg, setMsg] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>, done?: string) {
    setBusy(true); setErr(null); setMsg(null);
    try {
      await fn();
      if (done) setMsg(done);
      reload(); onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  function exportData() {
    // open the export as a download via a fetch (needs auth header)
    fetch(`${API_BASE}/api/admin/riders/${riderId}/data-export`, {
      headers: { Authorization: `Bearer ${getToken()}` },
    })
      .then((res) => res.json())
      .then((json) => {
        const blob = new Blob([JSON.stringify(json, null, 2)], { type: "application/json" });
        const url = URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `rider-${riderId}-export.json`;
        a.click();
        URL.revokeObjectURL(url);
      })
      .catch((e) => setErr(String(e)));
  }

  if (!r) return null;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2>{r.name} {r.blacklisted && <Badge value="blacklisted" />}</h2>
        {err && <div className="error">{err}</div>}
        {msg && <div className="muted">{msg}</div>}
        <dl className="kv">
          <dt>Phone</dt><dd>{r.phone}</dd>
          <dt>Bookings</dt><dd>{r.booking_count ?? "—"}</dd>
          <dt>Fake reports</dt><dd>{r.fake_report_count}</dd>
          <dt>Consent given</dt><dd>{fmtDate(r.consent_given_at)}</dd>
          <dt>Blacklist reason</dt><dd>{r.blacklist_reason || "—"}</dd>
        </dl>

        <h3>Actions</h3>
        <div className="btn-row">
          {!r.blacklisted && (
            <button className="btn danger sm" disabled={busy}
              onClick={() => run(() => apiPost(`/api/admin/riders/${r.id}/blacklist`,
                { reason: window.prompt("Reason:") || "admin" }))}>
              Blacklist
            </button>
          )}
          <button className="btn ghost sm" onClick={exportData}>PDPP export</button>
          <button className="btn danger sm" disabled={busy}
            onClick={() => {
              if (window.confirm("Erase this rider's PII? This cannot be undone."))
                run(() => fetch(`${API_BASE}/api/admin/riders/${r.id}/data`, {
                  method: "DELETE",
                  headers: { Authorization: `Bearer ${getToken()}` },
                }).then((res) => { if (!res.ok) throw new Error("Erase failed (open dispute?)"); }),
                  "Rider PII erased.");
            }}>
            PDPP erase
          </button>
        </div>
      </div>
    </div>
  );
}
