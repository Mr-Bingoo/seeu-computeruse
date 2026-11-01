const $ = id => document.getElementById(id);

async function refreshStatus() {
  const { status } = await chrome.storage.session.get("status").catch(() => ({}));
  const ok = status === "已连上";
  $("dot").className = "dot " + (ok ? "ok" : "bad");
  $("status").textContent = ok ? "已连上本机 SeeU" : (status || "没连上本机 SeeU") + "(先在终端跑一次安装命令)";
  if (!ok) chrome.runtime.sendMessage({ reconnect: true }).catch(() => {});
}

// C-0.5:名单 = SeeU 统一名单(本机 allow.json,开关那条路同一份);能碰 = 在名单里 且 Chrome 授权了
const toOrigin = pat => pat.replace(/\/\*$/, "");
const toPat = o => o + "/*";

async function seeuList(op, origin) {
  const r = await chrome.runtime.sendMessage({ list: op || "get", origin }).catch(e => ({ error: e.message }));
  if (!r || r.error) throw new Error((r && r.error) || "没连上本机 SeeU");
  return r.list;
}

async function granted() {
  return ((await chrome.permissions.getAll()).origins || []).filter(o => o !== "<all_urls>").map(toOrigin);
}

function row(text, buttons, note) {
  const li = document.createElement("li");
  const s = document.createElement("span");
  s.textContent = text;
  if (note) { const m = document.createElement("span"); m.className = "muted"; m.textContent = " " + note; s.appendChild(m); }
  li.append(s, ...buttons);
  return li;
}

function btn(text, fn, main) {
  const b = document.createElement("button");
  b.textContent = text;
  if (main) b.className = "main";
  b.onclick = async () => { try { await fn(); } catch (e) { $("origin").textContent = e.message; } render(); };
  return b;
}

async function allowSite(o) {
  if (!(await chrome.permissions.request({ origins: [toPat(o)] }))) return;   // 用户在 Chrome 框里点了拒绝
  try { await seeuList("add", o); }
  catch (e) { await chrome.permissions.remove({ origins: [toPat(o)] }); throw e; }   // 名单没写进去就不留半截授权
}

async function removeSite(o) {
  await chrome.permissions.remove({ origins: [toPat(o)] }).catch(() => {});
  await seeuList("remove", o);
}

async function refreshList() {
  const ul = $("list");
  ul.textContent = "";
  const g = await granted();
  let lst;
  try { lst = await seeuList(); }
  catch (_) {   // 没连上本机 SeeU:只能显示 Chrome 这边授权过的
    for (const o of g) ul.appendChild(row(o, [], "(没连上 SeeU,名单看不全)"));
    if (!g.length) ul.appendChild(row("还没有", []));
    return;
  }
  if (!lst.length) ul.appendChild(row("还没有", []));
  for (const o of lst) {
    const ok = g.includes(o);
    ul.appendChild(row(o, ok ? [btn("移除", () => removeSite(o))]
                             : [btn("在 Chrome 里允许", () => allowSite(o), true), btn("移除", () => removeSite(o))],
                       ok ? "" : "(Chrome 还没点允许)"));
  }
}

async function refreshSite() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  const b = $("toggle");
  let o = null;
  try {
    const u = new URL(tab && (tab.url || tab.pendingUrl) || "");
    if (/^https?:$/.test(u.protocol)) o = u.origin;
  } catch (_) { }
  // 没允许的网站 Chrome 不给插件看网址,这里只能先显示「这个网站」
  $("origin").textContent = o || (tab && tab.url ? "这个页面不支持(只支持 http/https 网页)" : "这个网站(允许后才显示网址)");
  if (!o) { b.hidden = true; return; }
  let inList = false;
  try { inList = (await seeuList()).includes(o); } catch (_) { }
  const has = inList && await chrome.permissions.contains({ origins: [toPat(o)] });
  b.hidden = false;
  b.textContent = has ? "取消允许" : "允许这个网站";
  b.className = has ? "" : "main";
  b.onclick = async () => {
    try { has ? await removeSite(o) : await allowSite(o); }
    catch (e) { $("origin").textContent = e.message + "(先在终端跑一次安装命令)"; return; }
    render();
  };
}

$("privacy").onclick = e => { e.preventDefault(); chrome.tabs.create({ url: chrome.runtime.getURL("privacy.html") }); };

function render() { refreshStatus(); refreshList(); refreshSite(); }
render();
