const API = window.location.origin;

function toast(message, type = "") {
  let el = document.getElementById("__toast");
  if (!el) {
    el = document.createElement("div");
    el.id = "__toast";
    el.className = "toast";
    document.body.appendChild(el);
  }
  el.textContent = message;
  el.className = "toast show " + type;
  clearTimeout(window.__toastTimer);
  window.__toastTimer = setTimeout(() => {
    el.classList.remove("show");
  }, 3000);
}

async function api(path, options = {}) {
  const opts = {
    credentials: "same-origin",
    headers: { "Content-Type": "application/json" },
    ...options,
  };
  if (opts.body && typeof opts.body !== "string") {
    opts.body = JSON.stringify(opts.body);
  }
  const r = await fetch(API + path, opts);
  let data;
  try { data = await r.json(); } catch { data = null; }
  if (!r.ok) {
    const err = new Error((data && data.error) || "Request failed");
    err.status = r.status;
    err.data = data;
    throw err;
  }
  return data;
}

async function logout() {
  try {
    await api("/api/auth/logout", { method: "POST" });
  } catch (e) {}
  window.location.href = "/login";
}

function initUserDropdown() {
  const trigger = document.querySelector(".topnav-user");
  if (!trigger) return;
  const dropdown = trigger.querySelector(".dropdown");
  if (!dropdown) return;
  trigger.addEventListener("click", (e) => {
    e.stopPropagation();
    dropdown.classList.toggle("open");
  });
  document.addEventListener("click", () => {
    dropdown.classList.remove("open");
  });
}

function initLangToggle() {
  const btn = document.getElementById("langToggleBtn");
  if (!btn) return;
  btn.addEventListener("click", () => {
    const current = getLang();
    setLang(current === "ar" ? "en" : "ar");
    if (typeof onLangChange === "function") onLangChange(getLang());
  });
}

function ratingClass(rating) {
  const map = {
    "Excellent": "badge-excellent", "V.Good": "badge-vgood", "Good": "badge-good",
    "Medium": "badge-medium", "Weak": "badge-weak", "Bad": "badge-bad", "Pending": "badge-pending"
  };
  return map[rating] || "badge-pending";
}

function ratingLabel(rating) {
  return t("rating." + rating);
}

function scoreColor(pct) {
  if (pct >= 75) return "success";
  if (pct >= 55) return "warn";
  return "danger";
}

function fmtMonth(monthStr) {
  if (!monthStr) return "—";
  const [y, m] = monthStr.split("-");
  const lang = getLang();
  const namesAr = ["يناير","فبراير","مارس","أبريل","مايو","يونيو","يوليو","أغسطس","سبتمبر","أكتوبر","نوفمبر","ديسمبر"];
  const namesEn = ["January","February","March","April","May","June","July","August","September","October","November","December"];
  const names = lang === "en" ? namesEn : namesAr;
  return names[parseInt(m) - 1] + " " + y;
}

function currentMonth() {
  const d = new Date();
  return d.getFullYear() + "-" + (d.getMonth() + 1).toString().padStart(2, "0");
}

function fmtNum(n, decimals = 0) {
  if (n == null || isNaN(n)) return "—";
  const locale = getLang() === "ar" ? "ar-EG" : "en-US";
  return Number(n).toLocaleString(locale, {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtMoney(n) {
  if (n == null || isNaN(n)) return "—";
  const locale = getLang() === "ar" ? "ar-EG" : "en-US";
  return Number(n).toLocaleString(locale, { maximumFractionDigits: 0 });
}

function openModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.add("open");
}

function closeModal(id) {
  const m = document.getElementById(id);
  if (m) m.classList.remove("open");
}

document.addEventListener("DOMContentLoaded", () => {
  initUserDropdown();
  initLangToggle();
  document.querySelectorAll(".modal-backdrop").forEach(m => {
    m.addEventListener("click", (e) => {
      if (e.target === m) m.classList.remove("open");
    });
  });
});
