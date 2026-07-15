"use client";

import Shell from "@/components/Shell";
import { useApi } from "@/lib/api";
import { gmd } from "@/lib/format";
import type { DashboardSummary } from "@/lib/types";

function Stat({ label, value, alert }: { label: string; value: string | number; alert?: boolean }) {
  return (
    <div className={`card stat ${alert ? "alert" : ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export default function DashboardPage() {
  const { data, error, loading } = useApi<DashboardSummary>("/api/admin/dashboard/summary");

  return (
    <Shell title="Dashboard">
      {loading && <div className="spinner">Loading…</div>}
      {error && <div className="error">{error}</div>}
      {data && (
        <>
          <div className="grid cols-4">
            <Stat label="Bookings today" value={data.bookings_today} />
            <Stat label="Active drivers" value={data.active_drivers} />
            <Stat label="Revenue today" value={gmd(data.revenue_today_gmd)} />
            <Stat label="Revenue this month" value={gmd(data.revenue_month_gmd)} />
          </div>

          <h2 style={{ marginTop: "1.75rem" }}>Needs attention</h2>
          <div className="grid cols-4">
            <Stat label="Pending verifications" value={data.alerts.pending_verifications} alert />
            <Stat label="Pending top-ups" value={data.alerts.pending_topups} alert />
            <Stat label="Open disputes" value={data.alerts.open_disputes} alert />
            <Stat label="Unassigned bookings" value={data.alerts.unassigned_bookings} alert />
          </div>

          <h2 style={{ marginTop: "1.75rem" }}>Bookings today by status</h2>
          <div className="grid cols-4">
            {Object.entries(data.bookings_by_status_today).map(([k, v]) => (
              <Stat key={k} label={k.replace(/_/g, " ")} value={v} />
            ))}
            {Object.keys(data.bookings_by_status_today).length === 0 && (
              <div className="muted">No bookings yet today.</div>
            )}
          </div>
        </>
      )}
    </Shell>
  );
}
