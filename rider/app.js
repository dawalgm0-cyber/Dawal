"use strict";

// Point at the backend. For production, change this to your API origin.
const API_BASE =
  (document.querySelector('meta[name="dawal-api"]') || {}).content ||
  "http://localhost:8000";

const POLL_MS = 4000;
const STORE_KEY = "dawal_booking";

// --- tiny helpers --------------------------------------------------------
const $ = (sel, el = document) => el.querySelector(sel);
const views = {};
document.querySelectorAll(".view").forEach((v) => (views[v.dataset.view] = v));

let state = load() || { id: null, token: null, phone: null, coords: null, view: "booking" };
let pollTimer = null;

function save() { localStorage.setItem(STORE_KEY, JSON.stringify(state)); }
function load() { try { return JSON.parse(localStorage.getItem(STORE_KEY)); } catch { return null; } }
function clearBooking() { state = { id: null, token: null, phone: null, coords: null, view: "booking" }; save(); }

function show(view) {
  state.view = view; save();
  Object.values(views).forEach((v) => v.classList.remove("active"));
  views[view].classList.add("active");
  window.scrollTo(0, 0);
  if (view === "status") startPolling(); else stopPolling();
}

function toast(msg) {
  const t = $("#toast");
  t.textContent = msg; t.hidden = false;
  clearTimeout(t._t); t._t = setTimeout(() => (t.hidden = true), 2600);
}

async function api(path, opts = {}) {
  const headers = Object.assign({}, opts.headers);
  if (opts.body) headers["Content-Type"] = "application/json";
  const res = await fetch(API_BASE + path, { ...opts, headers });
  let body = null;
  try { body = await res.json(); } catch { /* no body */ }
  if (!res.ok) {
    const detail = body && body.detail
      ? (typeof body.detail === "string" ? body.detail : "Please check your details.")
      : "Something went wrong. Please try again.";
    throw new Error(detail);
  }
  return body;
}

// --- booking: OpenStreetMap (Nominatim) + validation ---------------------
const NOMINATIM = "https://nominatim.openstreetmap.org";
let pickupPlace = null;   // { lat, lon, address }
let destPlace = null;

function fieldErr(name, msg) {
  const el = document.querySelector(`[data-err="${name}"]`);
  if (el) el.textContent = msg || "";
}
const nameOk = (v) => v.trim().length >= 3;
const phoneDigits = () => $("#f-phone").value.replace(/\D/g, "");

// --- Nominatim address autocomplete (debounced, adds "Gambia") -----------
const acTimers = {};
function onLocInput(field) {
  const input = field === "pickup" ? $("#f-pickup") : $("#f-destination");
  const dd = document.querySelector(`[data-ac="${field}"]`);
  if (field === "pickup") pickupPlace = null; else destPlace = null;
  const val = input.value.trim();
  clearTimeout(acTimers[field]);
  if (val.length < 3) { dd.hidden = true; return; }
  acTimers[field] = setTimeout(() => fetchPlaces(val, field, dd), 400);
}
async function fetchPlaces(query, field, dd) {
  try {
    const res = await fetch(
      `${NOMINATIM}/search?q=${encodeURIComponent(query + " Gambia")}&format=json&limit=7&addressdetails=1`,
      { headers: { Accept: "application/json" } });
    const places = await res.json();
    if (!places.length) { dd.innerHTML = `<div class="ac-item muted">No matches — keep typing</div>`; dd.hidden = false; return; }
    dd.innerHTML = places.map((p, i) => {
      const main = p.display_name.split(",")[0];
      const sub = p.display_name.split(",").slice(1, 3).join(",").trim();
      return `<div class="ac-item" data-i="${i}"><strong>${main}</strong><span>${sub}</span></div>`;
    }).join("");
    dd.hidden = false;
    dd.querySelectorAll(".ac-item[data-i]").forEach((item) =>
      item.addEventListener("click", () => selectPlace(places[item.dataset.i], field)));
  } catch { dd.hidden = true; }
}
function selectPlace(p, field) {
  const place = { lat: parseFloat(p.lat), lon: parseFloat(p.lon), address: p.display_name };
  const input = field === "pickup" ? $("#f-pickup") : $("#f-destination");
  input.value = p.display_name.split(",").slice(0, 3).join(",");
  document.querySelector(`[data-ac="${field}"]`).hidden = true;
  if (field === "pickup") { pickupPlace = place; updateMap(place); } else { destPlace = place; }
}
function updateMap(p) {
  const d = 0.01;
  const bbox = [p.lon - d, p.lat - d, p.lon + d, p.lat + d].join(",");
  const map = $("#map");
  map.src = `https://www.openstreetmap.org/export/embed.html?bbox=${bbox}&layer=mapnik&marker=${p.lat},${p.lon}`;
  map.hidden = false;
}
$("#f-pickup").addEventListener("input", () => onLocInput("pickup"));
$("#f-destination").addEventListener("input", () => onLocInput("destination"));
document.addEventListener("click", (e) => {
  if (!e.target.closest(".field")) document.querySelectorAll(".ac").forEach((d) => (d.hidden = true));
});

// My location -> reverse geocode -> fill pickup + map
$("#myloc-btn").addEventListener("click", () => {
  if (!navigator.geolocation) return toast("Location not available");
  toast("Getting your location…");
  navigator.geolocation.getCurrentPosition(async (pos) => {
    const { latitude: lat, longitude: lon } = pos.coords;
    let name = `${lat.toFixed(5)}, ${lon.toFixed(5)}`;
    try { const r = await fetch(`${NOMINATIM}/reverse?lat=${lat}&lon=${lon}&format=json`); const p = await r.json(); if (p.display_name) name = p.display_name; } catch {}
    selectPlace({ lat, lon, display_name: name }, "pickup");
  }, () => toast("Couldn't get location — search instead"),
    { enableHighAccuracy: true, timeout: 10000 });
});

let pendingBooking = null;
$("#booking-form").addEventListener("submit", (e) => {
  e.preventDefault();
  const first = $("#f-firstname").value, last = $("#f-lastname").value;
  let ok = true;
  fieldErr("firstname", nameOk(first) ? "" : "Min. 3 characters"); if (!nameOk(first)) ok = false;
  fieldErr("lastname", nameOk(last) ? "" : "Min. 3 characters"); if (!nameOk(last)) ok = false;
  const digits = phoneDigits();
  fieldErr("phone", digits.length >= 7 ? "" : "Enter at least 7 digits"); if (digits.length < 7) ok = false;
  if (!pickupPlace && !$("#f-pickup").value.trim()) { toast("Choose a pick-up location"); ok = false; }
  if (!ok) return;

  const destination_text = $("#f-destination").value.trim() || null;
  const phone = "+220" + digits;
  pendingBooking = {
    name: `${first.trim()} ${last.trim()}`,
    phone,
    ride_type: "ride",
    pickup_lat: pickupPlace ? pickupPlace.lat : null,
    pickup_lng: pickupPlace ? pickupPlace.lon : null,
    pickup_address_text: pickupPlace ? pickupPlace.address : ($("#f-pickup").value.trim() || null),
    destination_text,
    consent: true,
  };
  state.phone = phone; save();
  show("consent");
});

// --- consent -------------------------------------------------------------
$("#consent-check").addEventListener("change", (e) => {
  $("#consent-continue").disabled = !e.target.checked;
});
$("#consent-back").addEventListener("click", () => show("booking"));
$("#consent-continue").addEventListener("click", async () => {
  const btn = $("#consent-continue");
  btn.disabled = true; btn.textContent = "Sending…";
  try {
    const res = await api("/api/bookings", { method: "POST", body: JSON.stringify(pendingBooking) });
    state.id = res.id; state.token = res.rider_token; save();
    $("#otp-phone").textContent = state.phone;
    show("otp");
  } catch (err) {
    toast(err.message);
  } finally {
    btn.disabled = false; btn.textContent = "Send my code";
  }
});

// --- otp -----------------------------------------------------------------
$("#otp-verify").addEventListener("click", async () => {
  const code = $("#otp-input").value.trim();
  const errEl = $("#otp-error"); errEl.hidden = true;
  if (code.length < 3) { errEl.textContent = "Enter the code from your SMS."; errEl.hidden = false; return; }
  const btn = $("#otp-verify"); btn.disabled = true; btn.textContent = "Verifying…";
  try {
    await api(`/api/bookings/${state.id}/verify-otp`, { method: "POST", body: JSON.stringify({ code }) });
    show("status");
  } catch (err) {
    errEl.textContent = err.message; errEl.hidden = false;
  } finally {
    btn.disabled = false; btn.textContent = "Verify";
  }
});

// --- status polling ------------------------------------------------------
const STATUS_TEXT = {
  pending: ["Almost there…", "Confirming your booking."],
  posted: ["Looking for a driver…", "We're posting your request to nearby drivers."],
  unassigned: ["Finding your area…", "Our team is matching your pickup to a driver area."],
  pending_review: ["Under review", "Our team is taking a look. Please hold on."],
};

function startPolling() {
  stopPolling();
  poll();
  pollTimer = setInterval(poll, POLL_MS);
}
function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

async function poll() {
  if (!state.id) return;
  try {
    const s = await api(`/api/bookings/${state.id}/status?token=${encodeURIComponent(state.token)}`);
    if (s.status === "claimed" || s.status === "confirmed") { renderClaimed(s); return; }
    if (s.status === "completed") { show("rating"); return; }
    if (s.status === "cancelled" || s.status === "fake_flagged" || s.status === "no_show") {
      toast("This booking is closed."); clearBooking(); show("booking"); return;
    }
    const t = STATUS_TEXT[s.status] || STATUS_TEXT.posted;
    $("#status-title").textContent = t[0];
    $("#status-sub").textContent = t[1];
  } catch (err) { /* transient; keep polling */ }
}

function renderClaimed(s) {
  $("#driver-name").textContent = s.driver_name || "Your driver";
  $("#driver-initial").textContent = (s.driver_name || "D").charAt(0).toUpperCase();
  const call = $("#driver-call");
  if (s.driver_phone) { call.href = "tel:" + s.driver_phone; call.textContent = "Call " + s.driver_phone; }
  show("claimed");
}

$("#status-cancel").addEventListener("click", () => {
  if (confirm("Cancel this booking?")) { clearBooking(); show("booking"); }
});

// --- confirm pickup ------------------------------------------------------
$("#confirm-btn").addEventListener("click", async () => {
  const btn = $("#confirm-btn"); btn.disabled = true; btn.textContent = "Confirming…";
  try {
    await api(`/api/bookings/${state.id}/confirm-pickup`, {
      method: "POST", body: JSON.stringify({ confirm_token: state.token }),
    });
    show("rating");
  } catch (err) {
    toast(err.message); btn.disabled = false; btn.textContent = "Confirm pickup";
  }
});

// --- rating --------------------------------------------------------------
document.querySelectorAll(".thumb").forEach((b) => {
  b.addEventListener("click", async () => {
    document.querySelectorAll(".thumb").forEach((x) => x.classList.remove("sel"));
    b.classList.add("sel");
    try {
      await api(`/api/bookings/${state.id}/rate`, {
        method: "POST",
        body: JSON.stringify({
          confirm_token: state.token,
          rating_value: Number(b.dataset.rating),
          comment: $("#rating-comment").value.trim() || null,
        }),
      });
      finishTrip();
    } catch (err) { toast(err.message); }
  });
});
$("#rating-skip").addEventListener("click", finishTrip);
function finishTrip() { const done = state.id; clearBooking(); state.id = done; show("done"); }
$("#book-again").addEventListener("click", () => { clearBooking(); show("booking"); });

// --- SMS confirm deep-link ( /?confirm=<token>&booking=<id> ) -------------
(function handleDeepLink() {
  const q = new URLSearchParams(location.search);
  const confirmToken = q.get("confirm");
  const bookingId = q.get("booking");
  if (confirmToken && bookingId) {
    state.id = Number(bookingId); state.token = confirmToken; save();
    history.replaceState({}, "", location.pathname);
    show("status"); // poll will route to claimed/confirm as appropriate
    return true;
  }
  return false;
})();

// --- boot: resume where the rider left off -------------------------------
if (state.view && state.view !== "booking" && state.id) {
  show(state.view === "consent" ? "booking" : state.view);
} else {
  show("booking");
}

// --- online/offline ------------------------------------------------------
function updateOnline() { $("#offline-bar").hidden = navigator.onLine; }
window.addEventListener("online", updateOnline);
window.addEventListener("offline", updateOnline);
updateOnline();

// --- PWA install prompt --------------------------------------------------
let deferredPrompt = null;
window.addEventListener("beforeinstallprompt", (e) => {
  e.preventDefault(); deferredPrompt = e;
  if (!localStorage.getItem("dawal_install_dismissed")) $("#install-bar").hidden = false;
});
$("#install-btn").addEventListener("click", async () => {
  $("#install-bar").hidden = true;
  if (deferredPrompt) { deferredPrompt.prompt(); await deferredPrompt.userChoice; deferredPrompt = null; }
});
$("#install-dismiss").addEventListener("click", () => {
  $("#install-bar").hidden = true; localStorage.setItem("dawal_install_dismissed", "1");
});

// --- service worker ------------------------------------------------------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => navigator.serviceWorker.register("sw.js").catch(() => {}));
}
