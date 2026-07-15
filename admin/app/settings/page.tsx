"use client";

import { useEffect, useState } from "react";
import Shell from "@/components/Shell";
import { apiPatch, apiPost, useApi } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { AdminUser, MessageTemplate, PricingConfig } from "@/lib/types";

export default function SettingsPage() {
  return (
    <Shell title="Settings">
      <PricingSection />
      <TemplatesSection />
      <AdminUsersSection />
    </Shell>
  );
}

function PricingSection() {
  const { data, reload } = useApi<PricingConfig[]>("/api/admin/pricing-config");
  const [edits, setEdits] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function save() {
    if (Object.keys(edits).length === 0) return;
    setBusy(true); setErr(null); setMsg(null);
    try {
      await apiPatch("/api/admin/pricing-config", { updates: edits });
      setMsg("Saved."); setEdits({}); reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section>
      <h2>Pricing &amp; config</h2>
      {err && <div className="error">{err}</div>}
      {msg && <div className="muted">{msg}</div>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>Key</th><th>Value</th><th>Type</th><th>Updated</th></tr></thead>
          <tbody>
            {(data || []).map((c) => (
              <tr key={c.key}>
                <td>{c.key}</td>
                <td>
                  <input
                    defaultValue={c.value}
                    onChange={(e) => setEdits((p) => ({ ...p, [c.key]: e.target.value }))}
                    style={{ width: 120 }}
                  />
                </td>
                <td>{c.value_type}</td>
                <td>{fmtDate(c.updated_at)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <button className="btn orange" disabled={busy || Object.keys(edits).length === 0}
        onClick={save} style={{ marginTop: "0.75rem" }}>
        Save changes
      </button>
    </section>
  );
}

function TemplatesSection() {
  const { data, reload } = useApi<MessageTemplate[]>("/api/admin/message-templates");
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  useEffect(() => {
    if (data) setDrafts(Object.fromEntries(data.map((t) => [t.key, t.template_text])));
  }, [data]);

  async function save(key: string) {
    setBusy(true); setErr(null);
    try {
      await apiPatch(`/api/admin/message-templates/${key}`, { template_text: drafts[key] });
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2>Message templates</h2>
      {err && <div className="error">{err}</div>}
      {(data || []).map((t) => (
        <div className="card" key={t.key} style={{ marginBottom: "1rem" }}>
          <div className="field">
            <label>{t.key}</label>
            <textarea
              rows={4}
              value={drafts[t.key] ?? t.template_text}
              onChange={(e) => setDrafts((p) => ({ ...p, [t.key]: e.target.value }))}
              style={{ font: "inherit", padding: "0.5rem", border: "1px solid var(--line)", borderRadius: 8 }}
            />
          </div>
          <button className="btn sm" disabled={busy} onClick={() => save(t.key)}
            style={{ marginTop: "0.5rem" }}>
            Save
          </button>
        </div>
      ))}
    </section>
  );
}

function AdminUsersSection() {
  const { data, reload } = useApi<AdminUser[]>("/api/admin/users");
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "dispatcher" });
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  async function create(e: React.FormEvent) {
    e.preventDefault();
    setBusy(true); setErr(null);
    try {
      await apiPost("/api/admin/users", form);
      setForm({ name: "", email: "", password: "", role: "dispatcher" });
      reload();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section style={{ marginTop: "2rem" }}>
      <h2>Admin users</h2>
      {err && <div className="error">{err}</div>}
      <div className="table-wrap">
        <table>
          <thead><tr><th>ID</th><th>Name</th><th>Email</th><th>Role</th></tr></thead>
          <tbody>
            {(data || []).map((u) => (
              <tr key={u.id}>
                <td>#{u.id}</td><td>{u.name}</td><td>{u.email}</td><td>{u.role}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <form className="card" onSubmit={create} style={{ marginTop: "1rem" }}>
        <div className="filters" style={{ marginBottom: 0 }}>
          <div className="field"><label>Name</label>
            <input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} required /></div>
          <div className="field"><label>Email</label>
            <input type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} required /></div>
          <div className="field"><label>Password</label>
            <input type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} required /></div>
          <div className="field"><label>Role</label>
            <select value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
              <option value="dispatcher">dispatcher</option>
              <option value="captain_viewer">captain_viewer</option>
              <option value="super_admin">super_admin</option>
            </select></div>
          <button className="btn orange" disabled={busy}>Add admin</button>
        </div>
        <p className="muted" style={{ marginBottom: 0 }}>Requires super_admin.</p>
      </form>
    </section>
  );
}
