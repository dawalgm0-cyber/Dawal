"use client";

import { useState } from "react";
import Shell from "@/components/Shell";
import { apiPost, useApi } from "@/lib/api";
import { Badge, fmtDate, gmd } from "@/lib/format";
import type { LedgerEntry, MembershipRequest, Topup } from "@/lib/types";

export default function CreditsPage() {
  const { data: topups, loading, error, reload } =
    useApi<Topup[]>("/api/admin/credit-topups?topup_status=pending");
  const { data: ledger, reload: reloadLedger } =
    useApi<LedgerEntry[]>("/api/admin/credit-ledger?limit=50");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true); setErr(null);
    try {
      await fn();
      reload(); reloadLedger();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <Shell title="Credits">
      {err && <div className="error">{err}</div>}

      <h2>Pending top-up requests</h2>
      {loading && <div className="spinner">Loading…</div>}
      {error && <div className="error">{error}</div>}
      {topups && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>ID</th><th>Driver</th><th>Credits</th><th>Amount</th>
                <th>Method</th><th>Reference</th><th>Requested</th><th></th>
              </tr>
            </thead>
            <tbody>
              {topups.map((t) => (
                <tr key={t.id}>
                  <td>#{t.id}</td>
                  <td>#{t.driver_id}</td>
                  <td>{t.amount_credits}</td>
                  <td>{gmd(t.amount_gmd)}</td>
                  <td>{t.payment_method}</td>
                  <td>{t.reference_number || "—"}</td>
                  <td>{fmtDate(t.created_at)}</td>
                  <td>
                    <div className="btn-row">
                      <button className="btn sm" disabled={busy}
                        onClick={() => act(() => apiPost(`/api/admin/credit-topups/${t.id}/approve`))}>
                        Approve
                      </button>
                      <button className="btn ghost sm" disabled={busy}
                        onClick={() => act(() => apiPost(`/api/admin/credit-topups/${t.id}/reject`))}>
                        Reject
                      </button>
                    </div>
                  </td>
                </tr>
              ))}
              {topups.length === 0 && (
                <tr><td colSpan={8} className="muted">No pending requests.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      <h2 style={{ marginTop: "1.75rem" }}>Pending membership requests</h2>
      <MembershipRequests onDoneAction={() => reloadLedger()} />

      <h2 style={{ marginTop: "1.75rem" }}>Adjust credits</h2>
      <AdjustForm onDone={() => { reloadLedger(); }} />

      <h2 style={{ marginTop: "1.75rem" }}>Recent ledger</h2>
      {ledger && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Driver</th><th>Type</th><th>Credits</th><th>GMD</th><th>Booking</th><th>When</th></tr>
            </thead>
            <tbody>
              {ledger.map((l) => (
                <tr key={l.id}>
                  <td>#{l.id}</td>
                  <td>#{l.driver_id}</td>
                  <td><Badge value={l.transaction_type} /></td>
                  <td>{l.amount_credits > 0 ? `+${l.amount_credits}` : l.amount_credits}</td>
                  <td>{l.amount_gmd ? gmd(l.amount_gmd) : "—"}</td>
                  <td>{l.booking_id ? `#${l.booking_id}` : "—"}</td>
                  <td>{fmtDate(l.created_at)}</td>
                </tr>
              ))}
              {ledger.length === 0 && <tr><td colSpan={7} className="muted">Empty.</td></tr>}
            </tbody>
          </table>
        </div>
      )}
    </Shell>
  );
}

function MembershipRequests({ onDoneAction }: { onDoneAction: () => void }) {
  const { data, loading, reload } =
    useApi<MembershipRequest[]>("/api/admin/membership-requests?request_status=pending");
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function act(id: number, action: "approve" | "reject") {
    setBusy(true); setErr(null);
    try {
      await apiPost(`/api/admin/membership-requests/${id}/${action}`);
      reload(); onDoneAction();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      {err && <div className="error">{err}</div>}
      {loading && <div className="spinner">Loading…</div>}
      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr><th>ID</th><th>Driver</th><th>Months</th><th>Amount</th>
                <th>Method</th><th>Reference</th><th></th></tr>
            </thead>
            <tbody>
              {data.map((r) => (
                <tr key={r.id}>
                  <td>#{r.id}</td>
                  <td>#{r.driver_id}</td>
                  <td>{r.months}</td>
                  <td>{gmd(r.amount_gmd)}</td>
                  <td>{r.payment_method}</td>
                  <td>{r.reference_number || "—"}</td>
                  <td>
                    <div className="btn-row">
                      <button className="btn sm" disabled={busy} onClick={() => act(r.id, "approve")}>Approve</button>
                      <button className="btn ghost sm" disabled={busy} onClick={() => act(r.id, "reject")}>Reject</button>
                    </div>
                  </td>
                </tr>
              ))}
              {data.length === 0 && (
                <tr><td colSpan={7} className="muted">No pending membership requests.</td></tr>
              )}
            </tbody>
          </table>
        </div>
      )}
    </>
  );
}

function AdjustForm({ onDone }: { onDone: () => void }) {
  const [driverId, setDriverId] = useState("");
  const [amount, setAmount] = useState("");
  const [kind, setKind] = useState<"bonus" | "refund">("bonus");
  const [reason, setReason] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null); setMsg(null);
    try {
      await apiPost(`/api/admin/credits/${Number(driverId)}/${kind}`, {
        amount_credits: Number(amount),
        reason,
      });
      setMsg(`${kind === "bonus" ? "Bonus" : "Refund"} of ${amount} credits applied to driver #${driverId}.`);
      setAmount(""); setReason("");
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
      {msg && <div className="muted">{msg}</div>}
      <div className="filters" style={{ marginBottom: 0 }}>
        <div className="field">
          <label>Driver ID</label>
          <input value={driverId} onChange={(e) => setDriverId(e.target.value)} required />
        </div>
        <div className="field">
          <label>Type</label>
          <select value={kind} onChange={(e) => setKind(e.target.value as "bonus" | "refund")}>
            <option value="bonus">Bonus</option>
            <option value="refund">Refund</option>
          </select>
        </div>
        <div className="field">
          <label>Credits</label>
          <input type="number" min={1} value={amount} onChange={(e) => setAmount(e.target.value)} required />
        </div>
        <div className="field">
          <label>Reason</label>
          <input value={reason} onChange={(e) => setReason(e.target.value)} />
        </div>
        <button className="btn orange" disabled={busy}>Apply</button>
      </div>
    </form>
  );
}
