"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { api, apiPost, useApi } from "@/lib/api";
import { Badge, fmtDate } from "@/lib/format";
import type { BookingDetail, BookingListItem } from "@/lib/types";

const STATUSES = ["", "pending", "posted", "claimed", "completed", "no_show",
  "cancelled", "fake_flagged", "unassigned", "pending_review"];

export default function BookingsPage() {
  const [status, setStatus] = useState("");
  const [selected, setSelected] = useState<BookingDetail | null>(null);
  const qs = status ? `?booking_status=${status}` : "";
  const { data, loading, error, reload } = useApi<BookingListItem[]>(
    `/api/admin/bookings${qs}`, [status]
  );

  async function open(id: number) {
    setSelected(await api<BookingDetail>(`/api/admin/bookings/${id}`));
  }

  return (
    <Shell title="Bookings">
      <div className="filters">
        <div className="field">
          <label>Status</label>
          <select value={status} onChange={(e) => setStatus(e.target.value)}>
            {STATUSES.map((s) => (
              <option key={s} value={s}>{s ? s.replace(/_/g, " ") : "All"}</option>
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
                <th>ID</th><th>Rider</th><th>Type</th><th>Status</th>
                <th>Priority</th><th>Driver</th><th>Created</th>
              </tr>
            </thead>
            <tbody>
              {data.map((b) => (
                <tr key={b.id} className="clickable" onClick={() => open(b.id)}>
                  <td>#{b.id}</td>
                  <td>{b.rider_name || "—"}</td>
                  <td>{b.ride_type}</td>
                  <td><Badge value={b.status} /></td>
                  <td>{b.priority ? <span className="badge orange">priority</span> : "—"}</td>
                  <td>{b.assigned_driver_id ? `#${b.assigned_driver_id}` : "—"}</td>
                  <td>{fmtDate(b.created_at)}</td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={7} className="muted">No bookings.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {selected && (
        <BookingDrawer
          booking={selected}
          onClose={() => setSelected(null)}
          onChanged={() => { reload(); open(selected.id); }}
        />
      )}
    </Shell>
  );
}

function BookingDrawer({
  booking, onClose, onChanged,
}: {
  booking: BookingDetail;
  onClose: () => void;
  onChanged: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function act(path: string, body?: unknown) {
    setBusy(true); setErr(null);
    try {
      await apiPost(path, body);
      onChanged();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  const b = booking;
  return (
    <div className="overlay" onClick={onClose}>
      <div className="drawer" onClick={(e) => e.stopPropagation()}>
        <button className="close" onClick={onClose}>×</button>
        <h2>Booking #{b.id} <Badge value={b.status} /></h2>
        {err && <div className="error">{err}</div>}
        <dl className="kv">
          <dt>Rider</dt><dd>{b.rider_name} · {b.rider_phone}</dd>
          <dt>Type</dt><dd>{b.ride_type}</dd>
          <dt>Area</dt><dd>{b.area_id ?? "unassigned"}</dd>
          <dt>Pickup</dt><dd>{b.pickup_address_text || "—"}</dd>
          <dt>Destination</dt><dd>{b.destination_text || "—"}</dd>
          <dt>Driver</dt><dd>{b.driver_name ? `${b.driver_name} · ${b.driver_phone}` : "—"}</dd>
          <dt>Priority</dt><dd>{b.priority ? "yes" : "no"}</dd>
          <dt>Created</dt><dd>{fmtDate(b.created_at)}</dd>
          <dt>Claimed</dt><dd>{fmtDate(b.claimed_at)}</dd>
          <dt>Completed</dt><dd>{fmtDate(b.completed_at)}</dd>
        </dl>

        <h3>Actions</h3>
        <div className="btn-row">
          <button className="btn danger sm" disabled={busy}
            onClick={() => act(`/api/admin/bookings/${b.id}/mark-no-show`)}>
            Mark no-show
          </button>
          <button className="btn danger sm" disabled={busy}
            onClick={() => act(`/api/admin/bookings/${b.id}/flag-fake`)}>
            Flag fake
          </button>
          <button className="btn ghost sm" disabled={busy}
            onClick={() => act(`/api/admin/bookings/${b.id}/cancel`, { reason: "admin" })}>
            Cancel
          </button>
          <button className="btn ghost sm" disabled={busy}
            onClick={() => {
              const area = window.prompt("Assign to area id:");
              if (area) act(`/api/admin/bookings/${b.id}/override-assign`, { area_id: Number(area) });
            }}>
            Assign area…
          </button>
        </div>
      </div>
    </div>
  );
}
