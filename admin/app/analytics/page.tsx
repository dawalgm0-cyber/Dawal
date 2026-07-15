"use client";

import Shell from "@/components/Shell";
import { useApi } from "@/lib/api";
import { gmd } from "@/lib/format";
import type { Arpd, AreaHeat, Repurchase, TrendPoint } from "@/lib/types";

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card stat">
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default function AnalyticsPage() {
  const trend = useApi<TrendPoint[]>("/api/admin/analytics/bookings-trend?days=30");
  const arpd = useApi<Arpd>("/api/admin/analytics/arpd");
  const repurchase = useApi<Repurchase>("/api/admin/analytics/repurchase-rate");
  const heat = useApi<AreaHeat[]>("/api/admin/analytics/area-heatmap");

  const maxTrend = Math.max(1, ...(trend.data || []).map((p) => p.count));

  return (
    <Shell title="Analytics">
      <div className="grid cols-3">
        <Stat label="Revenue (all-time)" value={gmd(arpd.data?.revenue_gmd ?? null)} />
        <Stat label="Avg revenue / driver" value={gmd(arpd.data?.arpd_gmd ?? null)} />
        <Stat label="Repurchase rate"
          value={repurchase.data ? `${(repurchase.data.repurchase_rate * 100).toFixed(1)}%` : "—"} />
      </div>

      <h2 style={{ marginTop: "1.75rem" }}>Bookings — last 30 days</h2>
      <div className="card">
        {trend.loading && <div className="spinner">Loading…</div>}
        {trend.data && trend.data.length === 0 && <div className="muted">No bookings yet.</div>}
        <div style={{ display: "flex", alignItems: "flex-end", gap: 4, height: 160 }}>
          {(trend.data || []).map((p) => (
            <div key={p.day} title={`${p.day}: ${p.count}`}
              style={{
                flex: 1, minWidth: 6,
                height: `${(p.count / maxTrend) * 100}%`,
                background: "var(--orange)", borderRadius: "3px 3px 0 0",
              }} />
          ))}
        </div>
      </div>

      <h2 style={{ marginTop: "1.75rem" }}>Bookings by area</h2>
      <div className="table-wrap">
        <table>
          <thead><tr><th>Area</th><th>Bookings</th></tr></thead>
          <tbody>
            {(heat.data || []).map((h) => (
              <tr key={String(h.area_id)}>
                <td>{h.area_name || (h.area_id ? `#${h.area_id}` : "unassigned")}</td>
                <td>{h.bookings}</td>
              </tr>
            ))}
            {(heat.data || []).length === 0 && <tr><td colSpan={2} className="muted">No data.</td></tr>}
          </tbody>
        </table>
      </div>
    </Shell>
  );
}
