// SeeU 的 GNOME Shell 小插件(Linux 版;第 1 段 11-18 起,第 3 段 11-18 出第 2 版)。
// 只做:报窗口位置 / 上下顺序 / 前台、报鼠标位置;画提示条、代理光标(带名牌)、悬浮标、屏幕四周光圈;
//       借真鼠标时挪指针(warp)、把目标窗口拉到前台再还回去、读写剪贴板(借键盘打中文用,打完还原)。
// 真正的点击 / 按键不在这里发:走系统「远程操作」授权(xdg-desktop-portal RemoteDesktop),用户点过允许、系统右上角会亮提示。
// 🔴 不在 Shell 里截图:GNOME 50 上在 Shell 里截图会让整个会话崩掉登出(Cua issue #3985 / #5416),截图走系统截图授权。
// 锁屏时 GNOME 会自动停用小插件(没写 unlock-dialog 模式)→ D-Bus 名字 org.seeu.SeeU 消失,SeeU 拿这个当「锁屏就停手」的信号之一;
// 画的东西随之全部删掉。所有画的东西都是 reactive:false,鼠标直接穿过去,不挡用户。
import Gio from 'gi://Gio';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Clutter from 'gi://Clutter';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as Config from 'resource:///org/gnome/shell/misc/config.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';
import {CursorSet} from './cursor.js';
import {FloatView, Glow} from './float.js';

const API = 4;
const IFACE = `<node><interface name="org.seeu.SeeU">
  <method name="Ping"><arg type="s" direction="out" name="json"/></method>
  <method name="GetRects"><arg type="s" direction="out" name="json"/></method>
  <method name="GetPointer"><arg type="i" direction="out" name="x"/><arg type="i" direction="out" name="y"/></method>
  <method name="Warp"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/></method>
  <method name="GetFocus"><arg type="u" direction="out" name="id"/></method>
  <method name="Activate"><arg type="u" direction="in" name="id"/><arg type="b" direction="out" name="ok"/></method>
  <method name="GetClipboard"><arg type="b" direction="out" name="has_other"/><arg type="s" direction="out" name="text"/></method>
  <method name="SetClipboard"><arg type="s" direction="in" name="text"/></method>
  <method name="Toast"><arg type="s" direction="in" name="text"/><arg type="u" direction="in" name="ms"/></method>
  <method name="Dot"><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/><arg type="b" direction="in" name="show"/></method>
  <method name="Cursor"><arg type="s" direction="in" name="kind"/><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/>
    <arg type="s" direction="in" name="name"/><arg type="s" direction="in" name="color"/><arg type="u" direction="in" name="ms"/>
    <arg type="d" direction="out" name="travel"/></method>
  <method name="CursorK"><arg type="s" direction="in" name="kind"/><arg type="i" direction="in" name="x"/><arg type="i" direction="in" name="y"/>
    <arg type="s" direction="in" name="name"/><arg type="s" direction="in" name="color"/><arg type="u" direction="in" name="ms"/>
    <arg type="s" direction="in" name="key"/><arg type="b" direction="in" name="auto"/><arg type="d" direction="out" name="travel"/></method>
  <method name="CursorWait"><arg type="s" direction="in" name="key"/><arg type="b" direction="in" name="on"/></method>
  <method name="CursorHide"><arg type="s" direction="in" name="key"/></method>
  <method name="Badge"><arg type="s" direction="in" name="title"/><arg type="s" direction="in" name="text"/>
    <arg type="s" direction="in" name="color"/><arg type="u" direction="in" name="ms"/></method>
  <method name="Halo"><arg type="s" direction="in" name="color"/><arg type="b" direction="in" name="show"/></method>
  <method name="Glow"><arg type="s" direction="in" name="color"/><arg type="d" direction="in" name="secs"/></method>
  <method name="Float"><arg type="s" direction="in" name="json"/></method>
  <method name="FloatGeo"><arg type="s" direction="out" name="json"/></method>
  <signal name="FloatEvent"><arg type="s" name="kind"/><arg type="d" name="x"/><arg type="d" name="y"/><arg type="b" name="real"/></signal>
</interface></node>`;

function rgb(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  const v = m ? parseInt(m[1], 16) : 0x7F77DD;
  return [(v >> 16) & 255, (v >> 8) & 255, v & 255];
}

function css(hex, a) {
  const [r, g, b] = rgb(hex);
  return `rgba(${r},${g},${b},${a})`;
}

export default class SeeUHelper extends Extension {
  enable() {
    this._impl = Gio.DBusExportedObject.wrapJSObject(IFACE, this);
    this._impl.export(Gio.DBus.session, '/org/seeu_lib/SeeU');
    this._nameId = Gio.bus_own_name(Gio.BusType.SESSION, 'org.seeu.SeeU',
      Gio.BusNameOwnerFlags.NONE, null, null, null);
    this._actors = [];
    this._timers = {};
    const add = a => { a.hide(); Main.layoutManager.addTopChrome(a); this._actors.push(a); return a; };

    // reactive:false = 不接收点击,鼠标直接穿过去(GNOME 50 实测;50 起 addTopChrome 没有 affectsInputRegion 参数了)
    this._toast = add(new St.Label({
      style: 'background-color: rgba(28,28,30,0.88); color: #fff; padding: 10px 18px; border-radius: 14px; font-size: 15px;',
      reactive: false,
    }));
    this._dot = add(new St.Widget({
      style: 'background-color: rgba(10,132,255,0.9); border-radius: 9px; border: 2px solid white;',
      width: 18, height: 18, reactive: false,
    }));

    // 代理光标:跟 Mac / Windows 同一套样子(画法在 cursor.js)
    this._cursor = new CursorSet();     // 第 4 版:一个任务一只光标

    // 悬浮标:右上角一条小胶囊,写「哪个程序 · 这一步 · 为什么」
    this._badge = add(new St.BoxLayout({reactive: false, vertical: true}));
    this._bTitle = new St.Label({reactive: false, style: 'font-weight: bold; font-size: 13px; color: #fff;'});
    this._bText = new St.Label({reactive: false, style: 'font-size: 12px; color: rgba(255,255,255,0.85);'});
    this._badge.add_child(this._bTitle);
    this._badge.add_child(this._bText);

    // 屏幕四周光圈:借真鼠标时亮(告诉用户「现在是 SeeU 在动你的鼠标」),第 3 版起跟 Mac / Windows 一样渐隐 + 呼吸
    this._glow = new Glow();
    // 第 3 版:能点能拖的悬浮标(胶囊 / 卡片 / 多任务岛 / 看画面),画什么由 Python 那头的 floatwin 每帧发来
    this._float = new FloatView((kind, x, y, real) => {
      try {
        this._impl.emit_signal('FloatEvent', new GLib.Variant('(sddb)', [kind, x, y, !!real]));
      } catch (e) { /* 发不出去不要紧 */ }
    });
  }

  disable() {
    for (const k of Object.keys(this._timers || {})) GLib.source_remove(this._timers[k]);
    this._timers = {};
    for (const a of this._actors || []) { Main.layoutManager.removeChrome(a); a.destroy(); }
    this._actors = [];
    if (this._cursor) this._cursor.destroy();
    this._cursor = null;
    if (this._glow) this._glow.destroy();
    this._glow = null;
    if (this._float) this._float.destroy();
    this._float = null;
    this._toast = this._dot = this._badge = this._bTitle = this._bText = null;
    if (this._nameId) Gio.bus_unown_name(this._nameId);
    this._nameId = 0;
    if (this._impl) this._impl.unexport();
    this._impl = null;
  }

  _later(key, ms, fn) {
    if (this._timers[key]) GLib.source_remove(this._timers[key]);
    this._timers[key] = GLib.timeout_add(GLib.PRIORITY_DEFAULT, Math.max(300, ms), () => {
      delete this._timers[key]; fn(); return GLib.SOURCE_REMOVE;
    });
  }

  _win(id) {
    for (const a of global.get_window_actors()) {
      const w = a.meta_window;
      if (w && w.get_id() === id) return w;
    }
    return null;
  }

  Ping() {
    // modal > 0 = Shell 自己的弹框开着(钥匙环 / 管理员密码框、系统授权框、概览、运行框…):这时键鼠都给弹框,SeeU 不借
    return JSON.stringify({api: API, version: this.metadata.version, locked: Main.sessionMode.isLocked,
      mode: Main.sessionMode.currentMode, shell: Config.PACKAGE_VERSION, modal: Main.modalCount || 0,
      overview: Main.overview.visible});
  }

  GetRects() {
    const out = [];
    const active = global.workspace_manager.get_active_workspace();
    global.get_window_actors().forEach((a, z) => {
      const w = a.meta_window;
      if (!w) return;
      const f = w.get_frame_rect(), b = w.get_buffer_rect();
      const ws = w.get_workspace();
      out.push({
        id: w.get_id(), pid: w.get_pid(), title: w.get_title() || '', wm_class: w.get_wm_class() || '',
        app_id: w.get_gtk_application_id ? (w.get_gtk_application_id() || '') : '',
        x: f.x, y: f.y, w: f.width, h: f.height, buf_x: b.x, buf_y: b.y,
        z, focus: w.has_focus(), minimized: w.minimized, on_all: w.is_on_all_workspaces(),
        workspace: ws ? ws.index() : -1, active_ws: w.is_on_all_workspaces() || ws === active,
        type: w.get_window_type(), xwayland: w.get_client_type() === 1, skip: w.skip_taskbar,
      });
    });
    return JSON.stringify(out);
  }

  GetPointer() {
    const [x, y] = global.get_pointer();
    return [x, y];
  }

  // 借真鼠标时把指针挪到 (x, y)。只挪位置,不点(点击走系统远程操作授权)
  Warp(x, y) {
    Clutter.get_default_backend().get_default_seat().warp_pointer(x, y);
  }

  GetFocus() {
    const w = global.display.focus_window;
    return w ? w.get_id() : 0;
  }

  // 借真鼠标 / 键盘前把目标窗口拉到前台;SeeU 只在同一个工作区、没最小化时调(Python 那头先查)
  Activate(id) {
    const w = this._win(id);
    if (!w) return false;
    Main.activateWindow(w, global.get_current_time());
    return true;
  }

  // 剪贴板:借键盘打中文时用(先存用户原来的、贴完还回去)。has_other = 剪贴板里有不是文字的东西(图片、文件),这时 SeeU 不动它
  GetClipboardAsync(params, invocation) {
    const clip = St.Clipboard.get_default();
    const types = clip.get_mimetypes(St.ClipboardType.CLIPBOARD) || [];
    // 11-20 复查:有图片、文件就算 other(原来有文字就当纯文字,贴完只还回文字、图丢了);
    // 第二轮复查:只多了网页格式(text/html、vscode-editor-data…)的照常借,不然从 VS Code / 浏览器复制过东西就打不了中文
    const other = types.some(t => { const l = t.toLowerCase(); return l.startsWith('image/') || l === 'text/uri-list' ||
      l.startsWith('x-special/') || l.includes('copied-files') || l.startsWith('application/x-kde-cutselection'); });
    clip.get_text(St.ClipboardType.CLIPBOARD, (c, text) => {
      invocation.return_value(new GLib.Variant('(bs)', [other, text || '']));
    });
  }

  SetClipboard(text) {
    St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, text);
  }

  Toast(text, ms) {
    this._toast.text = text;
    this._toast.show();
    const m = Main.layoutManager.primaryMonitor;
    const [, nat] = this._toast.get_preferred_width(-1);
    this._toast.set_position(m.x + Math.round((m.width - nat) / 2), m.y + 48);
    this._later('toast', ms, () => this._toast.hide());
  }

  Dot(x, y, show) {
    if (!show) { this._dot.hide(); return; }
    this._dot.set_position(x - 9, y - 9);
    this._dot.show();
  }

  // 代理光标:kind = move | click;ms = 停下多久后淡出(0 = 马上藏)。返回走到位要几秒(SeeU 可以等这么久再动手,让波纹跟动作对上)
  Cursor(kind, x, y, name, color, ms) {
    return this._cursor.show(kind, x, y, name, color, ms, '_', false);
  }

  // 第 4 版(11-18 C-3.0):key = 哪个任务的光标;auto = 名牌按规则(只剩一只写 SeeU)
  CursorK(kind, x, y, name, color, ms, key, auto) {
    return this._cursor.show(kind, x, y, name, color, ms, key || '_', auto);
  }

  CursorWait(key, on) {
    this._cursor.wait(key, on);
  }

  CursorHide(key) {
    this._cursor.hide(key);
  }

  // 悬浮标:右上角,左边一条颜色(后台紫 / 借鼠标橙),ms 后收起
  Badge(title, text, color, ms) {
    if (!ms) { this._badge.hide(); return; }
    this._bTitle.text = title;
    this._bText.text = text;
    this._bText.visible = !!text;
    this._badge.style = `background-color: rgba(28,28,30,0.9); border-left: 4px solid ${css(color, 1)};` +
      ' border-radius: 12px; padding: 8px 14px; max-width: 360px;';
    const m = Main.layoutManager.primaryMonitor;
    this._badge.show();
    const [, nat] = this._badge.get_preferred_width(-1);
    this._badge.set_position(m.x + m.width - Math.min(nat, 380) - 16, m.y + Main.panel.height + 12);
    this._later('badge', ms, () => this._badge.hide());
  }

  Halo(color, show) {
    this._glow.set(rgb(color), show ? 15 : 0);     // 15 秒兜底:Python 那头没来得及关也会自己灭
  }

  // 光圈亮 secs 秒(动作还在就反复调来续);0 = 淡出
  Glow(color, secs) {
    this._glow.set(rgb(color), secs);
  }

  Float(json) {
    let m = null;
    try { m = JSON.parse(json); } catch (e) { m = null; }
    this._float.update(m);
  }

  // 悬浮标摆放要的:主屏可用范围(去掉顶栏)、深浅色
  FloatGeo() {
    const i = Main.layoutManager.primaryIndex;
    const wa = Main.layoutManager.getWorkAreaForMonitor(i);
    let dark = true;
    try { dark = St.Settings.get().color_scheme === St.SystemColorScheme.PREFER_DARK; } catch (e) { /* 老版本 */ }
    return JSON.stringify({x: wa.x, y: wa.y, w: wa.width, h: wa.height, dark});
  }
}
