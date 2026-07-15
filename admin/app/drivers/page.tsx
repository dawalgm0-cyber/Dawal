"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { API_BASE, api, apiPatch, apiPost, useApi } from "@/lib/api";
import { Badge, fmtDate, gmd } from "@/lib/format";
import type { Driver, LedgerEntry, Membership } from "@/lib/types";

const VSTATUS = ["", "pending", "verified", "rejected", "suspended"];

export default function DriversPage() {
  const [vs, setVs] = useState("");
  const [selected, setSelected] = useState<Driver | null>(null);
  const qs = vs ? `?verification_status=${vs}` : "";
  const { data, loading, error, reload } = useApi<Driver[]>(
    `/api/admin/drivers${qs}`, [vs]
  );

  return (
    <Shell title="Drivers">
      <div className="filters">
        <div className="field">
          <label>Verification</label>
          <select value={vs} onChange={(e) => setVs(e.target.value)}>
            {VSTATUS.map((s) => (
              <option key={s} value={s}>{s || "All"}</option>
            ))}
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
              <tr>
                <th>ID</th><th>Name</th><th>Phone</th><th>Verification</th>
                <th>Standing</th><th>Credits</th><th>Joined</th>
              </tr>
            </thead>
            <tbody>
              {data.map((d) => (
                <tr key={d.id} className="clickable" onClick={() => setSelected(d)}>
                  <td>#{d.id}</td>
                  <td>{d.name}</td>
                  <td>{d.phone}</td>
                  <td><Badge value={d.verification_status} /></td>
                  <td><Badge value={d.standing_tier} /></td>
                  <td>{d.credit_balance}</td>
                  <td>{fmtDate(d.created_at)}</td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={7} className="muted">No drivers.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <DriverDrawer
          driverId={selected.id}
          onClose={() => setSelected(null)}
          onChanged={reload}
        />
      )}
    </Shell>
  );
}

function DriverDrawer({
  driverId, onClose, onChanged,
}: {
  driverId: number;
  onClose: () => void;
  onChanged: () => void;
}) {
  const { data: d, reload } = useApi<Driver>(`/api/admin/drivers/${driverId}`);
  const { data: memberships, reload: reloadM } =
    useApi<Membership[]>(`/api/admin/memberships?driver_id=${driverId}`);
  const { data: ledger } =
    useApi<LedgerEntry[]>(`/api/admin/drivers/${driverId}/credit-history`);
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function run(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null);
    try {
      await fn();
      reload(); reloadM(); onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  if (!d) return null;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2>{d.name} <Badge value={d.verification_status} /></h2>
        {err && <div className="error">{err}</div>}
        <dl className="kv">
          <dt>Phone</dt><dd>{d.phone}</dd>
          <dt>Vehicle</dt><dd>{d.vehicle_type || "—"} · {d.plate_number || "—"}</dd>
          <dt>License</dt>
          <dd>
            {d.license_number || "—"}{" "}
            {d.license_doc_url && (
              <a href={`${API_BASE}${d.license_doc_url}`} target="_blank" rel="noreferrer">
                view doc
              </a>
            )}
          </dd>
          <dt>Standing</dt><dd><Badge value={d.standing_tier} /></dd>
          <dt>Credits</dt><dd>{d.credit_balance}</dd>
          <dt>Verified</dt><dd>{fmtDate(d.verified_at)}</dd>
        </dl>

        <h3>Verification</h3>
        <div className="btn-row">
          <button className="btn sm" disabled={busy}
            onClick={() => run(() => apiPost(`/api/admin/drivers/${d.id}/verify`))}>Verify</button>
          <button className="btn ghost sm" disabled={busy}
            onClick={() => run(() => apiPost(`/api/admin/drivers/${d.id}/reject`, { reason: "admin" }))}>Reject</button>
          <button className="btn danger sm" disabled={busy}
            onClick={() => run(() => apiPost(`/api/admin/drivers/${d.id}/suspend`, { reason: "admin" }))}>Suspend</button>
          <button className="btn ghost sm" disabled={busy}
            onClick={() => run(() => apiPost(`/api/admin/drivers/${d.id}/reinstate`))}>Reinstate</button>
        </div>

        <h3>Standing override</h3>
        <div className="btn-row">
          {["new", "standard", "gold"].map((t) => (
            <button key={t} className="btn ghost sm" disabled={busy}
              onClick={() => run(() => apiPatch(`/api/admin/drivers/${d.id}/standing`, { standing_tier: t }))}>
              {t}
            </button>
          ))}
        </div>

        <h3>Membership</h3>
        <div className="btn-row">
          <button className="btn sm" disabled={busy}
            onClick={() => run(() => apiPost(`/api/admin/memberships/${d.id}/activate`, { months: 1, amount_paid: "200.00" }))}>
            Activate 1mo
          </button>
          <button className="btn ghost sm" disabled={busy}
            onClick={() => run(() => apiPost(`/api/admin/memberships/${d.id}/extend?months=1`))}>
            Extend 1mo
          </button>
        </div>
        <table style={{ marginTop: "0.5rem" }}>
          <thead><tr><th>Status</th><th>Start</th><th>End</th><th>Paid</th></tr></thead>
          <tbody>
            {(memberships || []).map((m) => (
              <tr key={m.id}>
                <td><Badge value={m.status} /></td>
                <td>{fmtDate(m.period_start)}</td>
                <td>{fmtDate(m.period_end)}</td>
                <td>{gmd(m.amount_paid)}</td>
              </tr>
            ))}
            {(memberships || []).length === 0 && <tr><td colSpan={4} className="muted">None</td></tr>}
          </tbody>
        </table>

        <h3>Credit history</h3>
        <table>
          <thead><tr><th>Type</th><th>Credits</th><th>GMD</th><th>When</th></tr></thead>
          <tbody>
            {(ledger || []).map((l) => (
              <tr key={l.id}>
                <td><Badge value={l.transaction_type} /></td>
                <td>{l.amount_credits > 0 ? `+${l.amount_credits}` : l.amount_credits}</td>
                <td>{l.amount_gmd ? gmd(l.amount_gmd) : "—"}</td>
                <td>{fmtDate(l.created_at)}</td>
              </tr>
            ))}
            {(ledger || []).length === 0 && <tr><td colSpan={4} className="muted">None</td></tr>}
          </tbody>
        </table>
      </div>
    </div>
  );
}
