const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = n => "$" + Number(n || 0).toFixed(2);
const store = {
  get(k){ try { return localStorage.getItem(k); } catch { return null; } },
  set(k,v){ try { v == null ? localStorage.removeItem(k) : localStorage.setItem(k, v); } catch {} },
};

let token = store.get("hh-token"), me = null, meta = {categories:[], units:[], ai:false};
let listings = [], cat = "All", openId = null, photoFile = null;

function toast(msg){ const t=$("#toast"); t.textContent=msg; t.hidden=false; clearTimeout(toast._t); toast._t=setTimeout(()=>t.hidden=true,2800); }

async function api(path, {method="GET", json, form} = {}){
  const headers = {};
  if (token) headers.Authorization = "Bearer " + token;
  let body;
  if (json){ headers["Content-Type"]="application/json"; body=JSON.stringify(json); }
  if (form) body = form;
  const r = await fetch(path, {method, headers, body});
  const data = await r.json().catch(()=>({}));
  if (r.status === 401 && token){ logout(); }
  if (!r.ok){
    const d = data.detail;
    throw new Error(typeof d === "string" ? d : Array.isArray(d) ? "Check the form: " + d.map(x=>x.loc?.slice(-1)[0]).join(", ") : "Something went wrong.");
  }
  return data;
}

/* ---------- auth ---------- */
let signupMode = false;
function setAuthMode(s){
  signupMode = s;
  $("#authTitle").textContent = s ? "Create an account" : "Log in";
  $("#authBtn").textContent = s ? "Create account" : "Log in";
  $("#authAlt").textContent = s ? "Already have an account?" : "New here?";
  $("#authSwitch").textContent = s ? "Log in" : "Create an account";
  $("#nameRow").hidden = !s; $("#aName").required = s;
  $("#authErr").textContent = "";
}
$("#authSwitch").onclick = () => setAuthMode(!signupMode);
$("#authForm").onsubmit = async e => {
  e.preventDefault(); $("#authErr").textContent = ""; $("#authBtn").disabled = true;
  try{
    const res = signupMode
      ? await api("/api/signup", {method:"POST", json:{name:$("#aName").value, email:$("#aEmail").value, password:$("#aPass").value}})
      : await api("/api/login", {method:"POST", json:{email:$("#aEmail").value, password:$("#aPass").value}});
    token = res.token; store.set("hh-token", token); me = res.user; $("#aPass").value = ""; start();
  }catch(err){ $("#authErr").textContent = err.message; }
  finally{ $("#authBtn").disabled = false; }
};
async function logout(){
  try { if (token) await fetch("/api/logout", {method:"POST", headers:{Authorization:"Bearer "+token}}); } catch {}
  token = null; me = null; store.set("hh-token", null); showAuth();
}
$("#logout").onclick = logout;
function showAuth(){ $("#app").hidden = true; $("#userbar").hidden = true; $("#authForm").hidden = false; setAuthMode(false); }

/* ---------- tabs ---------- */
document.querySelectorAll(".tabs button").forEach(b => b.onclick = () => {
  document.querySelectorAll(".tabs button").forEach(x => x.setAttribute("aria-selected", x===b));
  ["buy","sell","pick"].forEach(v => $("#view-"+v).hidden = v!==b.dataset.tab);
  if (b.dataset.tab === "buy") loadListings();
  if (b.dataset.tab === "sell") loadMine();
  if (b.dataset.tab === "pick") loadPickups();
});

/* ---------- shop ---------- */
function renderCats(){
  $("#cats").innerHTML = ["All", ...meta.categories].map(c => `<button class="chip" aria-pressed="${c===cat}" data-c="${esc(c)}">${esc(c)}</button>`).join("");
}
$("#cats").onclick = e => { const c = e.target.dataset.c; if(!c) return; cat = c; renderCats(); loadListings(); };

async function loadListings(){
  try { listings = await api("/api/listings?category=" + encodeURIComponent(cat)); renderBuy(); }
  catch(err){ $("#listings").innerHTML = `<div class="empty"><b>Couldn't load listings</b>${esc(err.message)}</div>`; }
}
function renderBuy(){
  $("#listings").innerHTML = listings.length ? listings.map(card).join("")
    : `<div class="empty"><b>${cat==="All" ? "No produce listed yet" : "Nothing in " + esc(cat) + " right now"}</b>Farmers can post from the Sell produce tab.</div>`;
}
function card(l){
  const low = l.qty_left <= Math.max(3, l.qty * 0.15);
  const pic = l.photo_url ? `<img src="${esc(l.photo_url)}" alt="${esc(l.title)}" loading="lazy">` : esc((l.title||"?")[0]);
  const mineL = me && l.seller_id === me.id;
  return `<article class="card">
    <div class="photo">${pic}<span class="price">${money(l.price)}/${esc(l.unit)}</span></div>
    <div class="body">
      <h3>${esc(l.title)}</h3>
      <div class="meta">${esc(l.farm)} · ${esc(l.place)}</div>
      ${l.description ? `<p class="desc">${esc(l.description)}</p>` : ""}
      <div class="left ${low?"low":""}">${l.qty_left} ${esc(l.unit)} left</div>
      ${openId===l.id ? reserveForm(l) : `<button class="btn" data-open="${esc(l.id)}" ${mineL?"disabled":""}>${mineL?"Your listing":"Reserve"}</button>`}
    </div></article>`;
}
function reserveForm(l){
  return `<form class="reserve" data-res="${esc(l.id)}">
    <div class="two"><label>Amount (${esc(l.unit)})<input name="qty" type="number" min="1" max="${l.qty_left}" value="1" required></label>
    <label>Pickup<select name="slot">${l.slots.map(s=>`<option>${esc(s)}</option>`).join("")}</select></label></div>
    <div class="row"><button class="btn" type="submit">Confirm reservation</button><button class="btn ghost" type="button" data-close="1">Cancel</button></div>
  </form>`;
}
$("#listings").addEventListener("click", e => {
  if (e.target.dataset.open){ openId = e.target.dataset.open; renderBuy(); }
  if (e.target.dataset.close){ openId = null; renderBuy(); }
});
$("#listings").addEventListener("submit", async e => {
  e.preventDefault();
  const f = e.target, btn = f.querySelector("button[type=submit]"); btn.disabled = true;
  try{
    await api("/api/reservations", {method:"POST", json:{listing_id:f.dataset.res, qty:Number(f.qty.value), slot:f.slot.value}});
    openId = null; toast("Reserved. See it under Pickups."); loadListings();
  }catch(err){ toast(err.message); btn.disabled = false; }
});

/* ---------- sell ---------- */
$("#photo").onchange = e => {
  const f = e.target.files[0]; if (!f) return;
  photoFile = f;
  const url = URL.createObjectURL(f);
  $("#dropText").innerHTML = `<img src="${url}" alt="Your photo"><br><span class="note">Tap to change</span>`;
};

$("#aiBtn").onclick = async () => {
  const notes = $("#notes").value.trim();
  if (!photoFile && !notes){ $("#aiStatus").textContent = "Add a photo or a few words first."; return; }
  $("#aiBtn").disabled = true; $("#aiStatus").textContent = "Looking at your produce…";
  const form = new FormData(); form.append("notes", notes); if (photoFile) form.append("photo", photoFile);
  try{
    const r = await api("/api/ai/draft", {method:"POST", form});
    if (r.title) $("#title").value = r.title;
    if (r.description) $("#desc").value = r.description;
    if (meta.categories.includes(r.category)) $("#cat").value = r.category;
    if (meta.units.includes(r.unit)) $("#unit").value = r.unit;
    if (Number(r.price) > 0) $("#price").value = Number(r.price).toFixed(2);
    $("#aiBox").hidden = false;
    $("#aiBox").innerHTML = `<strong>Suggested price: ${money(r.price)} per ${esc(r.unit)}</strong>
      <span>Fair range ${money(r.price_low)}–${money(r.price_high)}. ${esc(r.price_reason)}</span>
      ${r.freshness ? `<span>Storage tip for buyers: ${esc(r.freshness)}</span>` : ""}
      ${r.warning ? `<span class="err">${esc(r.warning)}</span>` : ""}
      <span class="note">${r.source==="llm" ? "Written by AI." : "From the built-in price guide (add an AI key for photo-based drafts)."} Adjust it to what you know about your market.</span>`;
    $("#aiStatus").textContent = "Filled in below. Edit anything.";
  }catch(err){ $("#aiStatus").textContent = err.message; }
  finally{ $("#aiBtn").disabled = false; }
};

$("#sellForm").onsubmit = async e => {
  e.preventDefault(); $("#sellErr").textContent = "";
  const form = new FormData();
  [["title","title"],["farm","farm"],["description","desc"],["category","cat"],["unit","unit"],["price","price"],["qty","qty"],["place","place"],["slots","slots"]]
    .forEach(([k,id]) => form.append(k, $("#"+id).value));
  if (photoFile) form.append("photo", photoFile);
  $("#publishBtn").disabled = true;
  try{
    await api("/api/listings", {method:"POST", form});
    store.set("hh-farm", $("#farm").value); store.set("hh-place", $("#place").value); store.set("hh-slots", $("#slots").value);
    ["title","desc","price","qty","notes"].forEach(k => $("#"+k).value = "");
    photoFile = null; $("#photo").value = ""; $("#aiBox").hidden = true; $("#aiStatus").textContent = "";
    $("#dropText").innerHTML = "<b>Add a photo</b><br>Tap to choose a picture of the produce";
    toast("Posted. Buyers can see it now."); loadMine();
  }catch(err){ $("#sellErr").textContent = err.message; }
  finally{ $("#publishBtn").disabled = false; }
};

async function loadMine(){
  try{
    const mine = await api("/api/my/listings");
    $("#mine").innerHTML = mine.length ? mine.map(l => `<div class="res"><div><div class="who">${esc(l.title)}</div>
      <div class="meta">${money(l.price)}/${esc(l.unit)} · ${l.qty_left} of ${l.qty} left</div></div>
      <div class="row">${l.qty_left>0 ? `<button class="btn ghost" data-soldout="${esc(l.id)}">Mark sold out</button>` : `<span class="pill done">Sold out</span>`}
      <button class="btn ghost" data-del="${esc(l.id)}">Remove</button></div></div>`).join("")
      : `<div class="empty"><b>No listings yet</b>Your posted produce shows up here.</div>`;
  }catch(err){ $("#mine").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
}
$("#mine").onclick = async e => {
  const s = e.target.dataset.soldout, d = e.target.dataset.del;
  try{
    if (s) await api("/api/listings/"+s, {method:"PATCH", json:{qty_left:0}});
    if (d) { await api("/api/listings/"+d, {method:"DELETE"}); toast("Removed"); }
    if (s || d) loadMine();
  }catch(err){ toast(err.message); }
};

/* ---------- pickups ---------- */
function resRow(r, asSeller){
  const label = {waiting:"Waiting", done:"Picked up", cancelled:"Cancelled"}[r.status];
  return `<div class="res"><div><div class="who">${asSeller ? esc(r.buyer_name) : esc(r.title)}</div>
    <div class="meta">${r.qty} ${esc(r.unit)} ${asSeller ? esc(r.title) : "from " + esc(r.farm)} · ${money(r.qty*r.price)} · ${esc(r.slot)}${asSeller ? "" : " · " + esc(r.place)}</div></div>
    <div class="row"><span class="pill ${r.status}">${label}</span>
    ${r.status==="waiting" && asSeller ? `<button class="btn ghost" data-st="done" data-id="${esc(r.id)}">Mark picked up</button>` : ""}
    ${r.status==="waiting" ? `<button class="btn ghost" data-st="cancelled" data-id="${esc(r.id)}">Cancel</button>` : ""}</div></div>`;
}
async function loadPickups(){
  try{
    const {buying, selling} = await api("/api/my/reservations");
    $("#incoming").innerHTML = selling.length ? selling.map(r=>resRow(r,true)).join("") : `<div class="empty"><b>No orders yet</b>When someone reserves your produce, it shows up here with their pickup time.</div>`;
    $("#outgoing").innerHTML = buying.length ? buying.map(r=>resRow(r,false)).join("") : `<div class="empty"><b>Nothing reserved</b>Reserve something from the Shop tab.</div>`;
  }catch(err){ $("#incoming").innerHTML = `<p class="err">${esc(err.message)}</p>`; }
}
document.getElementById("view-pick").addEventListener("click", async e => {
  const {st, id} = e.target.dataset; if (!st) return;
  try{ await api("/api/reservations/"+id, {method:"PATCH", json:{status:st}}); loadPickups(); }
  catch(err){ toast(err.message); }
});

/* ---------- boot ---------- */
async function start(){
  $("#authForm").hidden = true; $("#app").hidden = false; $("#userbar").hidden = false;
  $("#who").textContent = me.name;
  renderCats(); loadListings();
}
(async () => {
  try { meta = await api("/api/meta"); } catch {}
  $("#cat").innerHTML = meta.categories.map(c=>`<option>${esc(c)}</option>`).join("");
  $("#unit").innerHTML = meta.units.map(u=>`<option>${esc(u)}</option>`).join("");
  $("#farm").value = store.get("hh-farm") || ""; $("#place").value = store.get("hh-place") || ""; $("#slots").value = store.get("hh-slots") || "";
  if (token){ try { me = await api("/api/me"); return start(); } catch {} }
  showAuth();
})();
