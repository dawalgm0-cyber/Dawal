"use strict";

const API_BASE =
  (document.querySelector('meta[name="dawal-api"]') || {}).content ||
  "http://localhost:8000";
const STORE = "dawal_driver";

const $ = (s, el = document) => el.querySelector(s);
const views = {};
document.querySelectorAll(".view").forEach((v) => (views[v.dataset.view] = v));

let sess = load() || { token: null, id: null };
let payOpts = null; // cached payment-options

function load() { try { return JSON.parse(localStorage.getItem(STORE)); } catch { return null; } }
function saveSess() { localStorage.setItem(STORE, JSON.stringify(sess)); }
function clearSess() { sess = { token: null, id: null }; localStorage.removeItem(STORE); }

function show(view) {
  Object.values(views).forEach((v) => v.classList.remove("active"));
  views[view].classList.add("active");
  $("#logout-btn").hidden = ["login", "register"].includes(view);
  window.scrollTo(0, 0);
}
function toast(m) { const t = $("#toast"); t.textContent = m; t.hidden = false; clearTimeout(t._t); t._t = setTimeout(() => (t.hidden = true), 2600); }
function money(v) { return "GMD " + Number(v).toLocaleString("en-GB", { minimumFractionDigits: 2, maximumFractionDigits: 2 }); }
function fmt(iso) { return iso ? new Date(iso).toLocaleDateString("en-GB", { day: "2-digit", month: "short" }) : "—"; }

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers);
  if (sess.token) headers["Authorization"] = "Bearer " + sess.token;
  if (opts.body && !(opts.body instanceof FormData)) headers["Content-Type"] = "application/json";
  const res = await fetch(API_BASE + path, { ...opts, headers });
  if (res.status === 401) { clearSess(); show("login"); throw new Error("Session expired — please sign in."); }
  let body = null; try { body = await res.json(); } catch {}
  if (!res.ok) {
    const d = body && body.detail;
    throw new Error(typeof d === "string" ? d : "Something went wrong.");
  }
  return body;
}

// --- auth ----------------------------------------------------------------
function routeByStatus(status) { show(status === "verified" ? "dashboard" : "pending"); if (status === "verified") loadDashboard(); }

$("#to-register").addEventListener("click", (e) => { e.preventDefault(); show("register"); });
$("#to-login").addEventListener("click", (e) => { e.preventDefault(); show("login"); });
$("#logout-btn").addEventListener("click", () => { clearSess(); show("login"); });

$("#login-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#login-error"); err.hidden = true;
  const f = e.target;
  try {
    const r = await api("/api/drivers/login", { method: "POST", body: JSON.stringify({ phone: f.phone.value.trim().replace(/\s/g, ""), pin: f.pin.value.trim() }) });
    sess = { token: r.access_token, id: r.driver_id }; saveSess();
    routeByStatus(r.verification_status);
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
});

$("#register-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const err = $("#register-error"); err.hidden = true;
  const f = e.target;
  try {
    const r = await api("/api/drivers/register", { method: "POST", body: JSON.stringify({
      name: f.name.value.trim(), phone: f.phone.value.trim().replace(/\s/g, ""), pin: f.pin.value.trim(),
      vehicle_type: f.vehicle_type.value.trim() || null, plate_number: f.plate_number.value.trim() || null,
      license_number: f.license_number.value.trim() || null }) });
    sess = { token: r.access_token, id: r.driver_id }; saveSess();
    const photo = f.license_photo.files[0];
    if (photo) { const fd = new FormData(); fd.append("file", photo); await api(`/api/drivers/${sess.id}/upload-license`, { method: "POST", body: fd }); }
    routeByStatus(r.verification_status); // new drivers -> pending
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
});

// --- dashboard -----------------------------------------------------------
async function loadDashboard() {
  try {
    const [p, m, s, b] = await Promise.all([
      api(`/api/drivers/${sess.id}/profile`),
      api(`/api/drivers/${sess.id}/membership`),
      api(`/api/drivers/${sess.id}/standing`),
      api(`/api/drivers/${sess.id}/bookings`),
    ]);
    $("#dash-hello").textContent = "Hi, " + p.name.split(" ")[0];
    $("#d-credits").textContent = p.credit_balance;
    $("#d-standing").textContent = p.standing_tier;
    const badge = $("#d-membership");
    const st = m.status || "none";
    badge.textContent = st.replace("_", " ");
    badge.className = "badge " + ({ active: "green", free_trial: "blue", expired: "red" }[st] || "gray");
    $("#d-membership-until").textContent = m.period_end ? "Valid until " + fmt(m.period_end) : "No active membership";
    const tb = $("#d-bookings"); tb.innerHTML = "";
    (b || []).slice(0, 8).forEach((x) => {
      tb.insertAdjacentHTML("beforeend", `<tr><td>#${x.id}</td><td>${x.ride_type}</td><td>${x.status.replace(/_/g, " ")}</td><td>${fmt(x.created_at)}</td></tr>`);
    });
    if (!b || !b.length) tb.innerHTML = `<tr><td colspan="4" class="muted">No jobs yet.</td></tr>`;
  } catch (ex) { toast(ex.message); }
}
$("#buy-credits-btn").addEventListener("click", () => openTopup());
$("#renew-btn").addEventListener("click", () => openRenewal());
document.querySelectorAll("[data-back]").forEach((b) => b.addEventListener("click", () => { show("dashboard"); loadDashboard(); }));

// --- payment options -----------------------------------------------------
async function getPayOpts() { if (!payOpts) payOpts = await api(`/api/drivers/${sess.id}/payment-options`); return payOpts; }
function methodOptions() { return ["wave", "afrimoney", "qmoney", "cash"].map((m) => `<option value="${m}">${m}</option>`).join(""); }
function renderNumbers(el, numbers) {
  el.innerHTML = Object.entries(numbers).filter(([, v]) => v)
    .map(([k, v]) => `<li><span>${k}</span><span>${v}</span></li>`).join("") ||
    `<li class="muted">Ask admin for payment numbers.</li>`;
}

// --- topup ---------------------------------------------------------------
let topupSel = null;
async function openTopup() {
  show("topup"); topupSel = null; $("#topup-pay").hidden = true;
  const o = await getPayOpts();
  const wrap = $("#topup-blocks"); wrap.innerHTML = "";
  o.credit_blocks.forEach((blk) => {
    const div = document.createElement("div"); div.className = "block";
    div.innerHTML = `<span class="credits">${blk.credits} credits</span><span class="price">${money(blk.amount_gmd)}</span>`;
    div.addEventListener("click", () => {
      document.querySelectorAll("#topup-blocks .block").forEach((x) => x.classList.remove("sel"));
      div.classList.add("sel"); topupSel = blk;
      $("#topup-amount").textContent = money(blk.amount_gmd);
      renderNumbers($("#topup-numbers"), o.payment_numbers);
      $("#topup-method").innerHTML = methodOptions();
      $("#topup-pay").hidden = false;
    });
    wrap.appendChild(div);
  });
  loadTopupList();
}
async function loadTopupList() {
  const list = await api(`/api/drivers/${sess.id}/topup-requests`);
  const tb = $("#topup-list"); tb.innerHTML = list.map((r) =>
    `<tr><td>${r.amount_credits}</td><td>${money(r.amount_gmd)}</td><td>${r.payment_method}</td><td>${statusBadge(r.status)}</td></tr>`).join("")
    || `<tr><td colspan="4" class="muted">No requests yet.</td></tr>`;
}
$("#topup-submit").addEventListener("click", async () => {
  const err = $("#topup-error"); err.hidden = true;
  if (!topupSel) return;
  try {
    const proof = await uploadProof($("#topup-proof").files[0]);
    await api(`/api/drivers/${sess.id}/credit-topup-request`, { method: "POST", body: JSON.stringify({
      amount_credits: topupSel.credits, amount_gmd: topupSel.amount_gmd,
      payment_method: $("#topup-method").value, reference_number: $("#topup-ref").value.trim() || null, proof_url: proof }) });
    toast("Submitted — awaiting admin approval.");
    $("#topup-pay").hidden = true; $("#topup-ref").value = ""; loadTopupList();
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
});

// --- renewal -------------------------------------------------------------
async function openRenewal() {
  show("renewal");
  const o = await getPayOpts();
  const sel = $("#renew-months"); sel.innerHTML = "";
  for (let i = 1; i <= 12; i++) sel.insertAdjacentHTML("beforeend", `<option value="${i}">${i} month${i > 1 ? "s" : ""}</option>`);
  const upd = () => { $("#renew-amount").textContent = money(Number(o.membership_fee_gmd) * Number(sel.value)); };
  sel.onchange = upd; upd();
  renderNumbers($("#renew-numbers"), o.payment_numbers);
  $("#renew-method").innerHTML = methodOptions();
  loadRenewList();
}
async function loadRenewList() {
  const list = await api(`/api/drivers/${sess.id}/membership-requests`);
  const tb = $("#renew-list"); tb.innerHTML = list.map((r) =>
    `<tr><td>${r.months}</td><td>${money(r.amount_gmd)}</td><td>${statusBadge(r.status)}</td></tr>`).join("")
    || `<tr><td colspan="3" class="muted">No requests yet.</td></tr>`;
}
$("#renew-submit").addEventListener("click", async () => {
  const err = $("#renew-error"); err.hidden = true;
  try {
    const proof = await uploadProof($("#renew-proof").files[0]);
    await api(`/api/drivers/${sess.id}/membership-request`, { method: "POST", body: JSON.stringify({
      months: Number($("#renew-months").value), payment_method: $("#renew-method").value,
      reference_number: $("#renew-ref").value.trim() || null, proof_url: proof }) });
    toast("Submitted — awaiting admin approval.");
    $("#renew-ref").value = ""; loadRenewList();
  } catch (ex) { err.textContent = ex.message; err.hidden = false; }
});

// --- shared --------------------------------------------------------------
async function uploadProof(file) {
  if (!file) return null;
  const fd = new FormData(); fd.append("file", file);
  const r = await api(`/api/drivers/${sess.id}/upload-proof`, { method: "POST", body: fd });
  return r.proof_url;
}
function statusBadge(s) {
  const cls = { pending: "orange", approved: "green", rejected: "red" }[s] || "gray";
  return `<span class="badge ${cls}">${s}</span>`;
}

// --- boot ----------------------------------------------------------------
(async function boot() {
  if (sess.token && sess.id) {
    try { const p = await api(`/api/drivers/${sess.id}/profile`); routeByStatus(p.verification_status); return; }
    catch { clearSess(); }
  }
  show("login");
})();
