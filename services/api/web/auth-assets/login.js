"use strict";
/* Sign-in page. Public asset: holds no product data or credentials.
   Live: POST /api/v1/auth/login, then reload "/" so the server returns the app. */
const API = "/api/v1";
const DEMO = window.VRX_DEMO || null;
const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const store = { get(k) { try { return localStorage.getItem(k); } catch (_) { return null; } }, set(k, v) { try { localStorage.setItem(k, v); } catch (_) {} } };
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const wait = ms => new Promise(r => setTimeout(r, ms));
const initials = n => String(n || "?").replace(/^Dr\.?\s+/i, "").split(/\s+/).map(w => w[0]).slice(0, 2).join("").toUpperCase();
const home = () => location.replace(DEMO ? "index.html" : "/");

async function post(path, body) {
  const res = await fetch(API + path, { method: "POST", headers: { "Content-Type": "application/json", Accept: "application/json" }, body: JSON.stringify(body), credentials: "same-origin" });
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw Object.assign(new Error(data.error?.message || (res.status === 429 ? "Too many attempts. Wait a minute and try again." : "That username and password don't match.")), { code: data.error?.code });
  return data;
}

/* ---------- motion preference ---------- */
let motion = store.get("vrx-motion") || (reduce ? "off" : "on");
function applyMotion() {
  document.documentElement.dataset.motion = motion;
  const b = $("#motionToggle");
  b.textContent = motion === "on" ? "Pause animation" : "Play animation";
  b.setAttribute("aria-pressed", String(motion === "off"));
}
$("#motionToggle").addEventListener("click", () => {
  motion = motion === "on" ? "off" : "on"; store.set("vrx-motion", motion); applyMotion();
  motion === "on" ? startStory() : stopStory(true);
});

/* ---------- soft glow that follows the pointer ---------- */
const aura = $("#cursorAura");
if (matchMedia("(hover: hover) and (pointer: fine)").matches && !reduce) {
  let tx = innerWidth * .7, ty = innerHeight * .4, x = tx, y = ty, on = false;
  const step = () => {
    x += (tx - x) * .08; y += (ty - y) * .08;
    aura.style.transform = `translate3d(${x}px, ${y}px, 0)`;
    if (Math.abs(tx - x) + Math.abs(ty - y) > .5) requestAnimationFrame(step); else on = false;
  };
  addEventListener("pointermove", e => { tx = e.clientX; ty = e.clientY; aura.classList.add("on"); if (!on && motion === "on") { on = true; requestAnimationFrame(step); } }, { passive: true });
}

/* ---------- three-scene story ---------- */
const story = { i: 0, timer: 0, typing: 0, raf: 0, level: 0, running: false, line: "Bukhaar teen din se hai. Dolo six fifty, ek tablet, subah aur raat, khaane ke baad, teen din.", durations: [5600, 4600, 5200] };
const scenes = $$(".scene"), stepEls = $$("#steps li");
function playScene(i) {
  story.i = i;
  scenes.forEach((s, k) => s.classList.toggle("on", k === i));
  stepEls.forEach((li, k) => {
    li.classList.toggle("on", k === i); li.classList.toggle("done", k < i);
    const bar = li.querySelector("i"); bar.getAnimations().forEach(a => a.cancel());
    if (k === i) bar.animate([{ transform: "scaleX(0)" }, { transform: "scaleX(1)" }], { duration: story.durations[i], easing: "linear", fill: "forwards" });
  });
  if (i === 0) typeLine();
  clearTimeout(story.timer);
  story.timer = setTimeout(() => playScene((i + 1) % scenes.length), story.durations[i]);
}
function typeLine() {
  const out = $("#typed"); clearInterval(story.typing);
  if (reduce) { out.textContent = story.line; return; }
  let n = 0; out.textContent = "";
  story.typing = setInterval(() => { out.textContent = story.line.slice(0, ++n); if (n >= story.line.length) clearInterval(story.typing); }, 44);
}
function drawWave() {
  const c = $("#heroWave"), dpr = Math.min(devicePixelRatio || 1, 2), w = c.clientWidth, h = c.clientHeight;
  if (w) {
    if (c.width !== w * dpr) { c.width = w * dpr; c.height = h * dpr; }
    const ctx = c.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, w, h);
    const speaking = story.i === 0 && $("#typed").textContent.length < story.line.length;
    story.level += ((speaking ? 1 : .12) - story.level) * .08;
    const t = performance.now() / 1000, bars = Math.floor(w / 7), g = ctx.createLinearGradient(0, 0, w, 0);
    g.addColorStop(0, "#F5964A"); g.addColorStop(.5, "#E7A3C6"); g.addColorStop(1, "#4A4FCB"); ctx.fillStyle = g;
    for (let b = 0; b < bars; b++) {
      const env = Math.sin(Math.PI * (b / bars)), v = Math.sin(b * .45 + t * 7) * .5 + Math.sin(b * .13 - t * 3.1) * .35 + Math.sin(b * 1.7 + t * 11) * .15;
      const bh = Math.max(3, Math.abs(v) * env * h * .9 * story.level + 3);
      ctx.beginPath(); ctx.roundRect(b * 7, (h - bh) / 2, 3.5, bh, 2); ctx.fill();
    }
  }
  if (story.running) story.raf = requestAnimationFrame(drawWave);
}
function startStory() { if (motion === "off") return stopStory(true); if (story.running) return; story.running = true; playScene(story.i); drawWave(); }
function stopStory(freeze) {
  story.running = false; clearTimeout(story.timer); clearInterval(story.typing); cancelAnimationFrame(story.raf);
  if (freeze) { scenes.forEach((s, k) => s.classList.toggle("on", k === 1)); stepEls.forEach((li, k) => { li.classList.toggle("on", k === 1); li.classList.toggle("done", k < 1); }); $("#typed").textContent = story.line; }
}
document.addEventListener("visibilitychange", () => document.hidden ? stopStory() : startStory());

/* ---------- form ---------- */
$("#pwToggle").addEventListener("click", e => {
  const pw = $("#password"), show = pw.type === "password"; pw.type = show ? "text" : "password";
  e.currentTarget.textContent = show ? "Hide" : "Show"; e.currentTarget.setAttribute("aria-label", show ? "Hide password" : "Show password");
});
async function leave() { if (!reduce) { $("#login").classList.add("leaving"); await wait(340); } home(); }

$("#loginForm").addEventListener("submit", async e => {
  e.preventDefault();
  const u = $("#username"), pw = $("#password"), err = $("#loginErr");
  u.removeAttribute("aria-invalid"); pw.removeAttribute("aria-invalid");
  if (!u.value.trim()) { err.textContent = "Enter your username."; u.setAttribute("aria-invalid", "true"); u.focus(); return; }
  if (!pw.value) { err.textContent = "Enter your password."; pw.setAttribute("aria-invalid", "true"); pw.focus(); return; }
  err.textContent = "";
  const btn = $("#signIn"); btn.classList.add("busy"); btn.disabled = true;
  try {
    if (DEMO) {
      await wait(700);
      if (u.value.trim() !== DEMO.username || pw.value !== DEMO.password) throw new Error("That username and password don't match. Try the demo account.");
      try { sessionStorage.setItem("vrx-demo", "1"); } catch (_) {}
    } else await post("/auth/login", { username: u.value.trim(), password: pw.value });
    await leave();
  } catch (x) {
    err.textContent = x.message; pw.setAttribute("aria-invalid", "true"); pw.select();
    $(".auth").animate([{ transform: "translateX(0)" }, { transform: "translateX(-5px)" }, { transform: "translateX(4px)" }, { transform: "translateX(0)" }], { duration: reduce ? 0 : 260, easing: "ease-out" });
  } finally { btn.classList.remove("busy"); btn.disabled = false; }
});

$("#devList").addEventListener("click", async e => {
  const b = e.target.closest("[data-user]"); if (!b) return;
  b.disabled = true;
  try { await post("/auth/dev-login", { user_id: b.dataset.user }); await leave(); }
  catch (x) { $("#loginErr").textContent = x.message; b.disabled = false; }
});

async function boot() {
  applyMotion();
  if (new URLSearchParams(location.search).has("expired")) $("#loginErr").textContent = "Your session ended. Sign in again.";
  if (DEMO) {
    $("#demoNote").hidden = false;
    $("#useDemo").onclick = () => { $("#username").value = DEMO.username; $("#password").value = DEMO.password; $("#loginErr").textContent = ""; $("#signIn").focus(); };
  } else {
    try {
      const opt = await fetch(API + "/auth/options", { credentials: "same-origin" }).then(r => r.ok ? r.json() : {});
      if (opt.dev_login) {
        const d = await fetch(API + "/auth/dev-users", { credentials: "same-origin" }).then(r => r.json());
        const users = d.items || d.users || [];
        $("#devList").innerHTML = users.map(u => `<button type="button" class="docpick" data-user="${esc(u.id)}"><span class="avatar">${esc(initials(u.display_name || u.name))}</span><span><b>${esc(u.display_name || u.name)}</b><span>${esc(u.specialty || "")}</span></span></button>`).join("");
        $("#devBox").hidden = !users.length;
      }
    } catch (_) { /* the form still works */ }
  }
  startStory();
  $("#username").focus({ preventScroll: true });
}
boot();
