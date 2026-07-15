"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { api, apiPost, useApi } from "@/lib/api";
import { fmtDate, gmd } from "@/lib/format";
import type { AreaAdmin, Captain, PayoutSummary } from "@/lib/types";

export default function AreasPage() {
  const areas = useApi<AreaAdmin[]>("/api/admin/areas");
  const captains = useApi<Captain[]>("/api/admin/captains");
  const [payout, setPayout] = useState<PayoutSummary | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function loadPayout(captainId: number) {
    setErr(null);
    try {
      setPayout(await api<PayoutSummary>(`/api/admin/captains/${captainId}/payout-summary`));
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }

  function reloadAll() { areas.reload(); captains.reload(); }

  return (
    <Shell title="Areas & Captains">
      {err && <div className="error">{err}</div>}

      <h2>Areas</h2>
      <NewAreaForm onDone={reloadAll} />
      <div className="table-wrap" style={{ marginTop: "1rem" }}>
        <table>
          <thead>
            <tr><th>ID</th><th>Name</th><th>Center</th><th>Radius (m)</th><th>Captain</th><th></th></tr>
          </thead>
          <tbody>
            {(areas.data || []).map((a) => (
              <tr key={a.id}>
                <td>#{a.id}</td>
                <td>{a.name}</td>
                <td className="muted">{a.center_lat}, {a.center_lng}</td>
                <td>{a.radius_meters}</td>
                <td>{a.captain_driver_name || <span className="muted">none</span>}</td>
                <td>
                  <button className="btn ghost sm"
                    onClick={() => {
                      const did = window.prompt("Assign captain — driver id:");
                      if (did) apiPost(`/api/admin/areas/${a.id}/assign-captain`,
                        { driver_id: Number(did) }).then(reloadAll)
                        .catch((e) => setErr(String(e)));
                    }}>
                    {a.captain_driver_id ? "Change captain" : "Assign captain"}
                  </button>
                </td>
              </tr>
            ))}
            {(areas.data || []).length === 0 && <tr><td colSpan={6} className="muted">No areas.</td></tr>}
          </tbody>
        </table>
      </div>

      <h2 style={{ marginTop: "1.75rem" }}>Captains</h2>
      <div className="table-wrap">
        <table>
          <thead>
            <tr><th>ID</th><th>Driver</th><th>Area</th><th>Share %</th><th>Since</th><th>Payout</th></tr>
          </thead>
          <tbody>
            {(captains.data || []).map((c) => (
              <tr key={c.id}>
                <td>#{c.id}</td>
                <td>{c.driver_name} (#{c.driver_id})</td>
                <td>{c.area_name}</td>
                <td>{c.revenue_share_pct}%</td>
                <td>{fmtDate(c.created_at)}</td>
                <td>
                  <button className="btn sm" onClick={() => loadPayout(c.id)}>
                    Payout report
                  </button>
                </td>
              </tr>
            ))}
            {(captains.data || []).length === 0 && <tr><td colSpan={6} className="muted">No captains.</td></tr>}
          </tbody>
        </table>
      </div>

      {payout && (
        <div className="overlay" onClick={() => setPayout(null)}>
          <div className="drawer" onClick={(e) => e.stopPropagation()}>
            <button className="close" onClick={() => setPayout(null)}>×</button>
            <h2>Payout report</h2>
            <p className="muted" style={{ marginTop: 0 }}>
              Calculation only — payout is disbursed manually.
            </p>
            <dl className="kv">
              <dt>Captain</dt><dd>{payout.driver_name} (#{payout.driver_id})</dd>
              <dt>Area</dt><dd>{payout.area_name}</dd>
              <dt>Drivers in area</dt><dd>{payout.driver_count}</dd>
              <dt>Credit revenue</dt><dd>{gmd(payout.total_purchase_gmd)}</dd>
              <dt>Share</dt><dd>{payout.revenue_share_pct}%</dd>
              <dt>Payout due</dt>
              <dd style={{ fontWeight: 800, color: "var(--orange)", fontSize: "1.2rem" }}>
                {gmd(payout.payout_gmd)}
              </dd>
            </dl>
          </div>
        </div>
      )}
    </Shell>
  );
}

function NewAreaForm({ onDone }: { onDone: () => void }) {
  const [f, setF] = useState({ name: "", center_lat: "", center_lng: "", radius_meters: "5000" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await apiPost("/api/admin/areas", {
        name: f.name, center_lat: f.center_lat, center_lng: f.center_lng,
        radius_meters: Number(f.radius_meters),
      });
      setF({ name: "", center_lat: "", center_lng: "", radius_meters: "5000" });
      onDone();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form className="card" onSubmit={submit}>
      {err && <div className="error">{err}</div>}
      <div className="filters" style={{ marginBottom: 0 }}>
        <div className="field"><label>Name</label>
          <input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} required /></div>
        <div className="field"><label>Center lat</label>
          <input value={f.center_lat} onChange={(e) => setF({ ...f, center_lat: e.target.value })} required /></div>
        <div className="field"><label>Center lng</label>
          <input value={f.center_lng} onChange={(e) => setF({ ...f, center_lng: e.target.value })} required /></div>
        <div className="field"><label>Radius (m)</label>
          <input type="number" value={f.radius_meters} onChange={(e) => setF({ ...f, radius_meters: e.target.value })} required /></div>
        <button className="btn orange" disabled={busy}>Add area</button>
      </div>
    </form>
  );
}
