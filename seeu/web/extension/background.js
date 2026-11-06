// SeeU 浏览器助手(C-1.4,10-20)
// 插件只通过 Chrome 官方「本机消息」跟本机中转程序 com.seeu.bridge 说话(不联网);
// 中转程序再转给 SeeU(seeu/web.py)。只能碰用户在弹窗里点过「允许」的网站(Chrome 自己的可选网站权限)。
// C-0.5(10-22):网站名单跟开关那条路合成一份(本机 ~/.seeu/seeu_web/allow.json,中转程序读写)。
//   要碰一个网站 = Chrome 授权了 且 在 SeeU 名单里。弹窗里允许/移除 → 两边一起改;
//   命令行 `python3 -m seeu disallow 网址` 移出名单 → 插件马上不碰,下次连上顺手收回 Chrome 授权;
//   命令行 allow 只进名单,Chrome 授权还得用户在弹窗里点一次(Chrome 规定只能用户亲手给)。

const HOST = "com.seeu.bridge";
const VERSION = chrome.runtime.getManifest().version;
let port = null;
let retryMs = 2000;
let badgeTimer = null;
let seeuList = null;      // SeeU 统一名单(网站 = 协议://域名);null = 还不知道(老中转程序不带名单时不查这一层)
let qidNext = 0;
const listWaiting = {};   // qid -> resolve

// 问中转程序要/改名单(op = get / add / remove),5 秒没回就当没连上
function listCall(op, origin) {
  return new Promise((resolve, reject) => {
    if (!port) return reject(new Error("没连上本机 SeeU"));
    const qid = ++qidNext;
    const timer = setTimeout(() => { delete listWaiting[qid]; reject(new Error("本机 SeeU 5 秒没回话")); }, 5000);
    listWaiting[qid] = r => { clearTimeout(timer); r.error ? reject(new Error(r.error)) : resolve(r.list); };
    port.postMessage({ list: op, origin: origin || "", qid });
  }).then(lst => { seeuList = lst; return lst; });
}

const toOrigin = pat => pat.replace(/\/\*$/, "");

// 连上后对一次账:第一次用新版先把 Chrome 里已授权的网站并进名单(老用户不丢),以后名单里没有的就收回 Chrome 授权
async function syncList() {
  try {
    const granted = ((await chrome.permissions.getAll()).origins || []).filter(o => o !== "<all_urls>");
    const { merged_v1 } = await chrome.storage.local.get("merged_v1");
    if (!merged_v1) {
      for (const o of granted) await listCall("add", toOrigin(o));
      await chrome.storage.local.set({ merged_v1: true });
    }
    const lst = await listCall("get");
    const stale = granted.filter(o => !lst.includes(toOrigin(o)));
    if (stale.length) await chrome.permissions.remove({ origins: stale });
  } catch (_) { /* 没连上就下次再对 */ }
}

// Chrome 自己的扩展设置页里移除网站 → 名单也跟着移除(弹窗里的改动另外显式同步)
chrome.permissions.onRemoved.addListener(p => {
  for (const o of (p.origins || [])) if (o !== "<all_urls>") listCall("remove", toOrigin(o)).catch(() => {});
});

function setStatus(s) {
  chrome.storage.session.set({ status: s, statusAt: Date.now() }).catch(() => {});
}

function connect() {
  if (port) return;
  try {
    port = chrome.runtime.connectNative(HOST);
  } catch (e) {
    port = null;
    setStatus("没连上本机程序:" + e.message);
    setTimeout(connect, retryMs);
    return;
  }
  setStatus("已连上");
  port.onMessage.addListener(onRequest);
  port.onDisconnect.addListener(() => {
    const err = chrome.runtime.lastError ? chrome.runtime.lastError.message : "";
    port = null;
    setStatus("没连上本机程序" + (err ? ":" + err : ""));
    retryMs = Math.min(retryMs * 2, 60000);   // 退避重连,最长 1 分钟一次
    setTimeout(connect, retryMs);
  });
  port.postMessage({ hello: true, version: VERSION, ua: navigator.userAgent });
  retryMs = 2000;
  syncList();
}

chrome.runtime.onStartup.addListener(connect);
chrome.runtime.onInstalled.addListener(connect);
chrome.runtime.onMessage.addListener((msg, _s, reply) => {
  if (msg && msg.reconnect) { connect(); reply({ ok: true }); }
  if (msg && msg.list) {              // 弹窗要/改名单(弹窗连不了本机程序,经这里转)
    listCall(msg.list, msg.origin).then(list => reply({ list }), e => reply({ error: e.message }));
    return true;
  }
});
connect();

function busy() {
  chrome.action.setBadgeBackgroundColor({ color: "#7F77DD" });
  chrome.action.setBadgeText({ text: "●" });
  clearTimeout(badgeTimer);
  badgeTimer = setTimeout(() => chrome.action.setBadgeText({ text: "" }), 2500);
}

async function onRequest(req) {
  if (req && req.qid !== undefined) {   // 名单回包
    const w = listWaiting[req.qid];
    if (w) { delete listWaiting[req.qid]; w(req); }
    return;
  }
  if (!req || req.id === undefined) return;
  if (Array.isArray(req.allow)) seeuList = req.allow;
  busy();
  let out;
  try {
    out = { id: req.id, ok: true, result: await handle(req.cmd, req.args || {}) };
  } catch (e) {
    out = { id: req.id, ok: false, error: String(e && e.message || e), code: (e && e.code) || "error" };
  }
  if (port) port.postMessage(out);
}

function fail(code, msg) {
  const e = new Error(msg);
  e.code = code;
  return e;
}

function originPattern(url) {
  const u = new URL(url);
  if (!/^https?:$/.test(u.protocol)) return null;
  return u.origin + "/*";
}

async function allowed(url) {
  if (!url) return false;
  const pat = originPattern(url);
  if (!pat) return false;
  if (seeuList && !seeuList.includes(toOrigin(pat))) return false;   // 不在 SeeU 统一名单里
  return chrome.permissions.contains({ origins: [pat] });
}

async function pickTab(tabId) {
  let tab;
  if (tabId !== undefined && tabId !== null) {
    tab = await chrome.tabs.get(tabId).catch(() => null);
    if (!tab) throw fail("no_tab", "没有这个标签页(可能已关掉)");
  } else {
    [tab] = await chrome.tabs.query({ active: true, lastFocusedWindow: true });
    if (!tab) throw fail("no_tab", "没有打开的标签页");
  }
  if (!(await allowed(tab.url)))   // 没允许的网站拿不到网址,也碰不了
    throw fail("not_allowed", "这个网站还没允许 SeeU 操作:在这个网页上点浏览器右上角的 SeeU 图标,选「允许这个网站」" +
      "(用命令加进名单的网站,也要在这里点一次,Chrome 才放行)");
  return tab;
}

async function waitLoaded(tabId, timeoutMs) {
  const t0 = Date.now();
  while (Date.now() - t0 < timeoutMs) {
    const t = await chrome.tabs.get(tabId).catch(() => null);
    if (!t) throw fail("no_tab", "标签页没了");
    if (t.status === "complete") return t;
    await new Promise(r => setTimeout(r, 250));
  }
  throw fail("timeout", `等了 ${Math.round(timeoutMs / 1000)} 秒页面还没加载完`);
}

async function run(tab, func, args) {
  const [r] = await chrome.scripting.executeScript({ target: { tabId: tab.id }, func, args });
  if (!r) throw fail("script", "页面里的程序没跑起来");
  if (r.result && r.result.__err) throw fail(r.result.code || "page", r.result.__err);
  return r.result;
}

async function handle(cmd, a) {
  switch (cmd) {
    case "ping":
      return { version: VERSION, ua: navigator.userAgent };
    case "reload":                      // 改了插件代码后让 SeeU 自己重载(开发者模式加载的插件不会自动更新)
      setTimeout(() => chrome.runtime.reload(), 200);
      return { reloading: true };
    case "allowed": {                   // 名单里且 Chrome 也授权了的(真正能碰的)
      const p = await chrome.permissions.getAll();
      return (p.origins || []).filter(o => o !== "<all_urls>" && (!seeuList || seeuList.includes(toOrigin(o))));
    }
    case "tabs": {
      const all = await chrome.tabs.query({});
      const out = [];
      for (const t of all) {
        if (await allowed(t.url))
          out.push({ id: t.id, title: t.title, url: t.url, active: t.active, windowId: t.windowId, status: t.status });
      }
      return { tabs: out, hidden: all.length - out.length };   // hidden = 没允许的网站,不告诉 SeeU 是什么
    }
    case "open": {
      if (!/^https?:\/\//.test(a.url || "")) throw fail("bad_url", "只开 http/https 网址");
      const t = await chrome.tabs.create({ url: a.url, active: !!a.active });
      const done = await waitLoaded(t.id, (a.timeout || 20) * 1000).catch(e => ({ err: e.message }));
      return { id: t.id, allowed: await allowed(a.url), loaded: !done.err, note: done.err || "" };
    }
    case "activate": {
      const t = await pickTab(a.tab);
      await chrome.tabs.update(t.id, { active: true });
      return { id: t.id };
    }
    case "close": {
      const t = await pickTab(a.tab);
      await chrome.tabs.remove(t.id);
      return { id: t.id };
    }
    case "wait": {
      const t = await pickTab(a.tab);
      await waitLoaded(t.id, (a.timeout || 20) * 1000);
      return { id: t.id };
    }
    case "snapshot": {
      const t = await pickTab(a.tab);
      const r = await run(t, pageSnapshot, [a.max || 400, a.text_max || 20000]);
      r.tab = { id: t.id, title: t.title, url: t.url, active: t.active };
      return r;
    }
    case "act": {
      const t = await pickTab(a.tab);
      return await run(t, pageAct, [a.i, a.action, a.value === undefined ? null : a.value, a.mode || "replace"]);
    }
    case "read": {
      const t = await pickTab(a.tab);
      return await run(t, pageRead, [a.max || 50000]);
    }
    default:
      throw fail("bad_cmd", "不认识的命令:" + cmd);
  }
}

// ---------------- 下面两个函数会被注入网页里跑(要自带一切,不能引用外面的变量) ----------------

function pageSnapshot(max, textMax) {
  const SEL = 'a[href],button,input,select,textarea,summary,[role=button],[role=link],[role=checkbox],[role=radio],' +
    '[role=tab],[role=menuitem],[role=switch],[role=option],[role=combobox],[role=textbox],[contenteditable=""],' +
    '[contenteditable=true],[tabindex]:not([tabindex="-1"])';
  const vw = innerWidth, vh = innerHeight;
  const seen = new Set();
  const els = [];
  const items = [];
  const clean = s => (s || "").replace(/\s+/g, " ").trim();
  const labelOf = el => {
    const al = el.getAttribute("aria-label");
    if (al) return clean(al);
    const by = el.getAttribute("aria-labelledby");
    if (by) {
      const t = by.split(/\s+/).map(id => document.getElementById(id)).filter(Boolean).map(n => n.innerText).join(" ");
      if (clean(t)) return clean(t);
    }
    if (el.labels && el.labels.length) {
      // 标签包着控件时(<label>城市 <select>…</select></label>),去掉控件自己的字(下拉选项等)只留标签文字
      const t = [...el.labels].map(l => {
        const c = l.cloneNode(true);
        c.querySelectorAll("input,select,textarea,button").forEach(n => n.remove());
        return c.textContent;
      }).join(" ");
      if (clean(t)) return clean(t);
    }
    if (el.tagName === "INPUT" && /^(button|submit|reset)$/.test(el.type)) return clean(el.value);
    if (el.tagName === "IMG") return clean(el.alt);
    const t = clean(el.innerText || el.textContent);
    if (t) return t.slice(0, 80);
    return clean(el.getAttribute("placeholder") || el.getAttribute("title") || el.getAttribute("alt") ||
      (el.querySelector("img[alt]") || {}).alt || "");
  };
  // 不碰的框:返回种类,不是返回 ""(C-0.5)。🔴 跟 seeu/ax.py 的 SECRET_WORDS 同一套词,改一边要改另一边;
  // 本函数被注入网页跑,不能引用外面的变量,pageSnapshot / pageAct 各抄一份
  const secretKind = el => {
    if (el.tagName !== "INPUT") return "";
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    if (/(^|\s)cc-/.test(ac)) return "银行卡框";
    if (/new-password/.test(ac)) return "新密码框";
    if (/one-time-code/.test(ac)) return "验证码框";
    if (/^(button|submit|reset|checkbox|radio|hidden|file|image|range|color|search)$/.test(el.type)) return "";
    const t = [el.getAttribute("aria-label"), el.getAttribute("placeholder"), el.name, el.id, el.title,
      ...[...(el.labels || [])].map(l => l.textContent)].filter(Boolean).join(" ");
    if (/新密码|确认密码|重复密码|再次输入密码|new[ _-]?pass(word)?|confirm[ _-]?pass(word)?|re-?type[ _-]?pass(word)?|repeat[ _-]?pass(word)?/i.test(t))
      return "新密码框";
    if (/验证码|校验码|动态码|动态密码|短信码|一次性密码|captcha|verif(y|ication)[ _-]?code|sms[ _-]?code|one[ _-]?time[ _-]?(code|pass)|\botp\b|security[ _-]?code|auth(entication)?[ _-]?code|\b2fa\b|two[ _-]?factor|vcode|checkcode/i.test(t))
      return "验证码框";
    if (el.type === "password" || /current-password/.test(ac) || /密码|口令|pass(word|code)|\bpwd\b/i.test(t)) return "密码框";
    return "";
  };
  for (const el of document.querySelectorAll(SEL)) {
    if (els.length >= max) break;
    if (seen.has(el)) continue;
    seen.add(el);
    if (el.tagName === "INPUT" && el.type === "hidden") continue;
    const r = el.getBoundingClientRect();
    if (r.width < 1 || r.height < 1) continue;
    const cs = getComputedStyle(el);
    if (cs.visibility === "hidden" || cs.display === "none" || +cs.opacity === 0) continue;
    const role = el.getAttribute("role") || (el.tagName === "INPUT" ? "input:" + el.type : el.tagName.toLowerCase());
    const it = { i: els.length, role, name: labelOf(el), disabled: !!el.disabled || el.getAttribute("aria-disabled") === "true",
      rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)],
      inView: r.bottom > 0 && r.right > 0 && r.top < vh && r.left < vw };
    const kind = secretKind(el);
    if (kind) it.secret = kind;
    else if ("value" in el && el.tagName !== "BUTTON" && !(el.tagName === "INPUT" && /^(button|submit|reset)$/.test(el.type)))
      it.value = String(el.value).slice(0, 200);
    if (el.isContentEditable) it.value = clean(el.innerText).slice(0, 200);
    if (el.type === "checkbox" || el.type === "radio") it.checked = el.checked;
    const ac = el.getAttribute("aria-checked");
    if (ac !== null) it.checked = ac === "true";
    const ph = el.getAttribute("placeholder");
    if (ph) it.hint = clean(ph);
    if (el.tagName === "SELECT") it.options = [...el.options].slice(0, 50).map(o => clean(o.text));
    if (el.tagName === "A") it.href = el.href;
    els.push(el);
    items.push(it);
  }
  window.__seeuEls = els;   // 隔离环境里的全局,下次 act 按编号找回元素(网页自己的脚本看不到)
  return {
    url: location.href, title: document.title, items,
    text: (document.body ? document.body.innerText : "").slice(0, textMax),
    view: { w: vw, h: vh, sx: screenX, sy: screenY, ow: outerWidth, oh: outerHeight, dpr: devicePixelRatio,
            scrollY: Math.round(scrollY), docH: document.documentElement.scrollHeight }
  };
}

function pageAct(i, action, value, mode) {
  const err = (code, msg) => ({ __err: msg, code });
  if (action === "scroll") {
    const dy = Number(value) || innerHeight * 0.8;
    scrollBy(0, dy);
    return { scrollY: Math.round(scrollY) };
  }
  const els = window.__seeuEls || [];
  const el = els[i];
  if (!el) return err("stale", "没有这个编号,先重新看一次页面");
  if (!el.isConnected) return err("stale", "这个控件已经不在页面上了(页面变了),先重新看一次");
  // 同 pageSnapshot 里的 secretKind(注入网页跑,只能各抄一份)
  const secretKind = el => {
    if (el.tagName !== "INPUT") return "";
    const ac = (el.getAttribute("autocomplete") || "").toLowerCase();
    if (/(^|\s)cc-/.test(ac)) return "银行卡框";
    if (/new-password/.test(ac)) return "新密码框";
    if (/one-time-code/.test(ac)) return "验证码框";
    if (/^(button|submit|reset|checkbox|radio|hidden|file|image|range|color|search)$/.test(el.type)) return "";
    const t = [el.getAttribute("aria-label"), el.getAttribute("placeholder"), el.name, el.id, el.title,
      ...[...(el.labels || [])].map(l => l.textContent)].filter(Boolean).join(" ");
    if (/新密码|确认密码|重复密码|再次输入密码|new[ _-]?pass(word)?|confirm[ _-]?pass(word)?|re-?type[ _-]?pass(word)?|repeat[ _-]?pass(word)?/i.test(t))
      return "新密码框";
    if (/验证码|校验码|动态码|动态密码|短信码|一次性密码|captcha|verif(y|ication)[ _-]?code|sms[ _-]?code|one[ _-]?time[ _-]?(code|pass)|\botp\b|security[ _-]?code|auth(entication)?[ _-]?code|\b2fa\b|two[ _-]?factor|vcode|checkcode/i.test(t))
      return "验证码框";
    if (el.type === "password" || /current-password/.test(ac) || /密码|口令|pass(word|code)|\bpwd\b/i.test(t)) return "密码框";
    return "";
  };
  const kind = secretKind(el);
  if (kind) return err("refused", kind + ",SeeU 不碰(这一步请你自己来)");
  el.scrollIntoView({ block: "center", inline: "center" });
  const r = el.getBoundingClientRect();
  const cx = r.x + r.width / 2, cy = r.y + r.height / 2;
  // has:打字后「整段字在不在框里」在网页里比完只回对错(11-06:原来只回前 200 字让外面比,超过 200 字就误报没生效,AI 重打出重复内容)
  const full = () => "value" in el ? String(el.value) : (el.isContentEditable ? el.innerText : undefined);
  const state = () => ({ value: full() === undefined ? undefined : full().slice(0, 200),
    has: (action === "type" && typeof value === "string" && full() !== undefined) ? full().includes(value) : undefined,
    checked: (el.type === "checkbox" || el.type === "radio") ? el.checked : undefined, url: location.href,
    rect: [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] });
  const fire = (type, Ctor) => el.dispatchEvent(new Ctor(type, { bubbles: true, cancelable: true, composed: true,
    clientX: cx, clientY: cy, button: 0, buttons: type.endsWith("down") ? 1 : 0, pointerType: "mouse", isPrimary: true }));
  const click = () => {
    fire("pointerover", PointerEvent); fire("mouseover", MouseEvent);
    fire("pointerdown", PointerEvent); fire("mousedown", MouseEvent);
    if (el.focus) el.focus({ preventScroll: true });
    fire("pointerup", PointerEvent); fire("mouseup", MouseEvent);
    fire("click", MouseEvent);
  };
  if (action === "click") { click(); return state(); }
  if (action === "focus") { el.focus(); return state(); }
  if (action === "check") {           // value = true/false:想要的勾选状态,已经是就不动
    const want = value !== false && value !== "false";
    const cur = (el.type === "checkbox" || el.type === "radio") ? el.checked : el.getAttribute("aria-checked") === "true";
    if (cur !== want) click();
    return state();
  }
  if (action === "select") {          // value = 选项文字或值
    if (el.tagName !== "SELECT") return err("bad_target", "这不是下拉框");
    const opt = [...el.options].find(o => o.text.trim() === String(value) || o.value === String(value)) ||
      [...el.options].find(o => o.text.includes(String(value)));
    if (!opt) return err("not_found", "下拉框里没有「" + value + "」");
    el.value = opt.value;
    el.dispatchEvent(new Event("input", { bubbles: true }));
    el.dispatchEvent(new Event("change", { bubbles: true }));
    return state();
  }
  if (action === "type") {            // mode = replace(清空再写)/ append(接在后面)
    const text = String(value == null ? "" : value);
    el.focus();
    if (el.isContentEditable) {
      if (mode === "replace") document.execCommand("selectAll", false);
      document.execCommand("insertText", false, text);
    } else if ("value" in el) {
      // 用原生的 value 设置器 + input 事件,React/Vue 这类框架才认(直接 el.value = 会被框架当没变)
      const proto = el.tagName === "TEXTAREA" ? HTMLTextAreaElement.prototype : HTMLInputElement.prototype;
      const setter = Object.getOwnPropertyDescriptor(proto, "value").set;
      setter.call(el, mode === "append" ? el.value + text : text);
      el.dispatchEvent(new InputEvent("input", { bubbles: true, inputType: "insertText", data: text }));
      el.dispatchEvent(new Event("change", { bubbles: true }));
    } else {
      return err("bad_target", "这个控件不能打字");
    }
    return state();
  }
  if (action === "enter") {
    for (const t of ["keydown", "keypress", "keyup"])
      el.dispatchEvent(new KeyboardEvent(t, { key: "Enter", code: "Enter", keyCode: 13, which: 13, bubbles: true }));
    if (el.form && el.tagName === "INPUT") { /* 不替调用方提交表单:要提交就点提交按钮 */ }
    return state();
  }
  return err("bad_action", "不认识的动作:" + action);
}

function pageRead(max) {
  return { url: location.href, title: document.title, text: (document.body ? document.body.innerText : "").slice(0, max) };
}
