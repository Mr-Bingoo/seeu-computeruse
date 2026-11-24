// SeeU 悬浮标(Linux 版,11-18 C-3.0):胶囊 ↔ 卡片 ↔ 多任务岛 + 按钮栏 + 看画面,样子和交互跟 Mac / Windows 同一套。
// 分工:画什么、什么时候变由 Python 那头算(seeu/linux/floatwin.py,直接用 Windows 版 win/floatwin.py 的 scene / island 纯计算),
//       每一帧把「画布放哪、画哪些东西」用 Float(json) 发过来;这里只负责照着画(Cairo + Pango),再把鼠标的移入 / 按下 / 拖 / 松开
//       用 FloatEvent 信号报回去。所以三个平台长得一样,改样子改 Python 那头。
// 看画面:不截图(GNOME 50 在 Shell 里截图会崩),直接放一份被操作窗口的实时影子(Clutter.Clone,跟概览里的窗口缩略图同一个做法)。
// 真手按:按下那一下来自有设备节点的硬件(/dev/input/…)、并且在系统里挂在真总线上(不在 /sys/devices/virtual/ 下)才算;
//   系统远程操作(SeeU 借鼠标走的就是它)注入的设备没有节点,uinput 造的设备挂在 virtual 下,都不算 → I See 开不了。
//   不看设备名:虚拟机里真鼠标也叫「Parallels Virtual Mouse」(11-19 C-3.1 用户亲手点不开,查出来就是名字里带 virtual 被拒)。
import Cairo from 'cairo';
import Clutter from 'gi://Clutter';
import GLib from 'gi://GLib';
import Gio from 'gi://Gio';
import Meta from 'gi://Meta';
import St from 'gi://St';
import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

export const FONT = 'Noto Sans CJK SC';          // Python 那头量字宽用同一个字体(floatwin.FONT)

function col(c, a) {
  // c = [r, g, b] 或 [r, g, b, a](0~255,同 Windows 版 prims 里的颜色)
  const al = c.length > 3 ? c[3] / 255 : 1;
  return [c[0] / 255, c[1] / 255, c[2] / 255, al * (a === undefined ? 1 : a)];
}

function rrPath(cr, x, y, w, h, r) {
  r = Math.max(0.5, Math.min(r, w / 2, h / 2));
  cr.newPath();
  cr.arc(x + w - r, y + r, r, -Math.PI / 2, 0);
  cr.arc(x + w - r, y + h - r, r, 0, Math.PI / 2);
  cr.arc(x + r, y + h - r, r, Math.PI / 2, Math.PI);
  cr.arc(x + r, y + r, r, Math.PI, 3 * Math.PI / 2);
  cr.closePath();
}

const fonts = {};
function font(size, bold) {
  const k = size + (bold ? 'b' : '');
  if (!fonts[k]) {
    const f = Pango.FontDescription.from_string(FONT);
    f.set_absolute_size(size * Pango.SCALE);
    f.set_weight(bold ? Pango.Weight.BOLD : Pango.Weight.NORMAL);
    fonts[k] = f;
  }
  return fonts[k];
}

function layout(cr, text, size, bold) {
  const lay = PangoCairo.create_layout(cr);
  lay.set_font_description(font(size, bold));
  lay.set_text(String(text), -1);
  const [, lg] = lay.get_extents();
  return [lay, lg.width / Pango.SCALE, lg.height / Pango.SCALE];
}

function isReal(ev) {
  try {
    const d = ev.get_source_device ? ev.get_source_device() : null;
    if (!d) return false;
    const node = d.get_device_node ? d.get_device_node() : null;
    return !!node && node.startsWith('/dev/input/') && onRealBus(node);
  } catch (e) {
    return false;
  }
}

const _bus = new Map();   // 设备节点 → 是否挂在真总线上(查一次记住)
function onRealBus(node) {
  if (_bus.has(node)) return _bus.get(node);
  let ok = false;
  try {
    const name = node.split('/').pop();
    const info = Gio.File.new_for_path(`/sys/class/input/${name}`)
      .query_info('standard::symlink-target', Gio.FileQueryInfoFlags.NOFOLLOW_SYMLINKS, null);
    const target = info.get_symlink_target() || '';
    ok = target.includes('/devices/') && !target.includes('/devices/virtual/');
  } catch (e) {
    ok = false;
  }
  _bus.set(node, ok);
  return ok;
}

// 11-23 C-3.9 整体复查(小插件第 14 版):Python 那头的显示进程卡死 / 被强杀时,最后一帧会一直留在屏幕上。
// 它正常时每秒至少发十几帧 → 这么久没收到新的一帧就自己藏起来(它恢复后下一帧照常画出来)。
const STALE_S = 10;

const EDGE_CURSOR = {l: 'WEST_RESIZE', r: 'EAST_RESIZE', t: 'NORTH_RESIZE', b: 'SOUTH_RESIZE',
  tl: 'NW_RESIZE', br: 'SE_RESIZE', tr: 'NE_RESIZE', bl: 'SW_RESIZE'};

export class FloatView {
  constructor(emit) {
    this._emit = emit;                       // (kind, x, y, real) → D-Bus 信号
    this.m = null;
    this.box = new St.Widget({reactive: false, x: 0, y: 0, width: 10, height: 10});
    this.box.hide();
    Main.layoutManager.addTopChrome(this.box);
    this.under = new St.DrawingArea({reactive: false});
    this.clip = new St.Widget({reactive: false, clip_to_allocation: true});
    this.over = new St.DrawingArea({reactive: false});
    this.hit = new St.Widget({reactive: true, track_hover: true});
    for (const a of [this.under, this.clip, this.over, this.hit]) this.box.add_child(a);
    this.clip.hide();
    this.clone = null;
    this.cloneWid = 0;
    this.under.connect('repaint', a => this._paint(a, 0));
    this.over.connect('repaint', a => this._paint(a, 1));
    this._grab = null;
    this._cursorSet = false;
    this._watchId = 0;
    this._lastFrame = 0;
    const pt = ev => { const [x, y] = ev.get_coords(); return [x, y]; };
    this.hit.connect('button-press-event', (a, ev) => {
      if (ev.get_button() !== 1) return Clutter.EVENT_PROPAGATE;
      if (!this._grab) {
        try { this._grab = global.stage.grab(this.hit); } catch (e) { this._grab = null; }
      }
      this._emit('press', ...pt(ev), isReal(ev));
      return Clutter.EVENT_STOP;
    });
    this.hit.connect('button-release-event', (a, ev) => {
      if (ev.get_button() !== 1) return Clutter.EVENT_PROPAGATE;
      this._ungrab();
      this._emit('release', ...pt(ev), isReal(ev));
      return Clutter.EVENT_STOP;
    });
    this.hit.connect('motion-event', (a, ev) => {
      this._emit('motion', ...pt(ev), isReal(ev));
      return Clutter.EVENT_STOP;
    });
    this.hit.connect('enter-event', (a, ev) => { this._emit('enter', ...pt(ev), false); return Clutter.EVENT_PROPAGATE; });
    this.hit.connect('leave-event', (a, ev) => {
      if (!this._grab) this._setCursor('');
      this._emit('leave', ...pt(ev), false);
      return Clutter.EVENT_PROPAGATE;
    });
  }

  _ungrab() {
    if (this._grab) {
      try { this._grab.dismiss(); } catch (e) { /* 已经没了 */ }
      this._grab = null;
    }
  }

  _setCursor(edge) {
    try {
      const name = EDGE_CURSOR[edge];
      if (name && Meta.Cursor[name] !== undefined) {
        global.display.set_cursor(Meta.Cursor[name]);
        this._cursorSet = true;
      } else if (this._cursorSet) {
        global.display.set_cursor(Meta.Cursor.DEFAULT);
        this._cursorSet = false;
      }
    } catch (e) { /* 光标样子换不了不要紧 */ }
  }

  // 盯着「多久没新帧」:显示着才盯(2 秒看一次),藏了就停
  _watch(on) {
    if (on && !this._watchId) {
      this._watchId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 2, () => {
        if (GLib.get_monotonic_time() - this._lastFrame > STALE_S * 1000000) {
          this._watchId = 0;
          this.update(null);
          return GLib.SOURCE_REMOVE;
        }
        return GLib.SOURCE_CONTINUE;
      });
    } else if (!on && this._watchId) {
      GLib.source_remove(this._watchId);
      this._watchId = 0;
    }
  }

  destroy() {
    this._watch(false);
    this._ungrab();
    this._setCursor('');
    this._dropClone();
    Main.layoutManager.removeChrome(this.box);
    this.box.destroy();
    this.box = null;
  }

  // m = {show, x, y, w, h(画布在屏幕上的位置和大小), shape:[x,y,w,h,r], prims:[...], through, cursor, wid, glass}
  update(m) {
    if (!m || !m.show) {
      this._watch(false);
      this.m = null;
      this._ungrab();
      this._setCursor('');
      this._dropClone();
      this.box.hide();
      return;
    }
    this._lastFrame = GLib.get_monotonic_time();
    this._watch(true);
    this.m = m;
    const [W, H] = [Math.max(1, Math.ceil(m.w)), Math.max(1, Math.ceil(m.h))];
    this.box.set_position(Math.round(m.x), Math.round(m.y));
    this.box.set_size(W, H);
    for (const a of [this.under, this.over]) { a.set_position(0, 0); a.set_size(W, H); }
    const [sx, sy, sw, sh] = m.shape;
    this.hit.set_position(Math.floor(sx), Math.floor(sy));
    this.hit.set_size(Math.ceil(sw), Math.ceil(sh));
    this.hit.reactive = !m.through;
    if (m.through) { this._ungrab(); this._setCursor(''); } else if (m.cursor !== undefined) this._setCursor(m.cursor);
    this._placeClone(m);
    this.box.show();
    this.under.queue_repaint();
    this.over.queue_repaint();
  }

  _dropClone() {
    if (this.clone) { this.clone.destroy(); this.clone = null; }
    this.cloneWid = 0;
    if (this.clip) this.clip.hide();
  }

  _placeClone(m) {
    const img = (m.prims || []).find(p => p[0] === 'img');
    const win = img && m.wid ? this._win(m.wid) : null;
    if (!img || !win) { this._dropClone(); return; }
    const actor = win.get_compositor_private();
    if (!actor) { this._dropClone(); return; }
    if (!this.clone || this.cloneWid !== m.wid) {
      this._dropClone();
      this.clone = new Clutter.Clone({source: actor, reactive: false});
      this.clip.add_child(this.clone);
      this.cloneWid = m.wid;
    }
    const [, ix, iy, iw, ih] = img;
    this.clip.set_position(Math.round(ix), Math.round(iy));
    this.clip.set_size(Math.round(iw), Math.round(ih));
    const f = win.get_frame_rect(), b = win.get_buffer_rect();
    // 影子是整块窗口(含阴影那圈);按「看得见的那块」缩放、挪开阴影
    const kx = iw / Math.max(1, f.width), ky = ih / Math.max(1, f.height);
    const [ax, ay] = [actor.get_x(), actor.get_y()];
    this.clone.set_scale(kx, ky);
    this.clone.set_position((ax - f.x) * kx, (ay - f.y) * ky);
    this.clip.show();
  }

  _win(id) {
    for (const a of global.get_window_actors()) {
      const w = a.meta_window;
      if (w && w.get_id() === id) return w;
    }
    return null;
  }

  // layer 0 = 画面下面(阴影、底、文字…直到 img);layer 1 = 画面上面(画面的圆角、点击波纹、按钮栏…)
  _paint(area, layer) {
    const cr = area.get_context();
    const m = this.m;
    if (!m) { cr.$dispose(); return; }
    const [x, y, w, h, r] = m.shape;
    const prims = m.prims || [];
    const iImg = prims.findIndex(p => p[0] === 'img');
    const hasPic = iImg >= 0 && this.clip.visible;
    let from = 0, to = prims.length;
    if (layer === 1) {
      if (!hasPic) { cr.$dispose(); return; }
      from = iImg;
    } else if (hasPic) {
      to = iImg + 1;
    }
    if (layer === 0) {
      for (let i = 8; i > 0; i--) {             // 阴影(同 Windows)
        rrPath(cr, x - i, y - i + 3, w + 2 * i, h + 2 * i, r + i);
        cr.setSourceRGBA(0, 0, 0, 7 / 255);
        cr.fill();
      }
    }
    const clipShape = () => { rrPath(cr, x, y, w, h, r); cr.clip(); };
    cr.save();
    if (layer === 1) clipShape();
    for (let i = from; i < to; i++) {
      const p = prims[i];
      const k = p[0];
      if (k === 'rr') {
        rrPath(cr, p[1], p[2], p[3], p[4], p[5]);
        cr.setSourceRGBA(...col(p[6]));
        cr.fill();
        if (p[1] === x && p[2] === y && p[3] === w && p[4] === h) clipShape();
      } else if (k === 'ring') {
        cr.restore(); cr.save();
        rrPath(cr, p[1] + 0.5, p[2] + 0.5, p[3] - 1, p[4] - 1, p[5] - 0.5);
        cr.setSourceRGBA(...col(p[6]));
        cr.setLineWidth(p[7]);
        cr.stroke();
        clipShape();
      } else if (k === 'dot') {
        cr.newPath();
        cr.arc(p[1], p[2], Math.max(0.1, p[3]), 0, 2 * Math.PI);
        cr.setSourceRGBA(...col(p[4]));
        cr.fill();
      } else if (k === 'eye') {
        const [, cx, cy, rad, c] = p;
        const x0 = cx - rad * 1.25, x1 = cx + rad * 1.25;
        cr.newPath();
        cr.moveTo(x0, cy);
        cr.curveTo(cx - rad * 0.5, cy - rad * 1.1, cx + rad * 0.5, cy - rad * 1.1, x1, cy);
        cr.curveTo(cx + rad * 0.5, cy + rad * 1.1, cx - rad * 0.5, cy + rad * 1.1, x0, cy);
        cr.closePath();
        cr.setSourceRGBA(...col(c));
        cr.setLineWidth(1.5);
        cr.setLineJoin(Cairo.LineJoin.ROUND);
        cr.stroke();
        cr.newPath();
        cr.arc(cx, cy, rad * 0.42, 0, 2 * Math.PI);
        cr.fill();
      } else if (k === 'circ') {
        cr.newPath();
        cr.arc(p[1], p[2], Math.max(0.1, p[3]), 0, 2 * Math.PI);
        cr.setSourceRGBA(...col(p[4]));
        cr.setLineWidth(p[5]);
        cr.stroke();
      } else if (k === 'arc') {
        const [, cx, cy, rad, a0, sweep, c, wd] = p;
        const s = a0 * Math.PI / 180, e = (a0 + sweep) * Math.PI / 180;
        cr.newPath();
        if (sweep >= 0) cr.arc(cx, cy, rad, s, e); else cr.arcNegative(cx, cy, rad, s, e);
        cr.setSourceRGBA(...col(c));
        cr.setLineWidth(wd);
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.stroke();
      } else if (k === 'line') {
        cr.newPath();
        cr.moveTo(p[1], p[2]);
        cr.lineTo(p[3], p[4]);
        cr.setSourceRGBA(...col(p[5]));
        cr.setLineWidth(p[6]);
        cr.setLineCap(Cairo.LineCap.ROUND);
        cr.stroke();
      } else if (k === 'img') {
        const [, ix, iy, iw, ih, ir] = p;
        if (layer === 0) {                         // 底:画面还没出来时先是一块暗的
          rrPath(cr, ix, iy, iw, ih, ir);
          cr.setSourceRGBA(0, 0, 0, 70 / 255);
          cr.fill();
        } else {                                   // 画面四个角:用卡片底色盖成圆角
          cr.save();
          cr.setFillRule(Cairo.FillRule.EVEN_ODD);
          cr.newPath();
          cr.rectangle(ix - 1, iy - 1, iw + 2, ih + 2);
          const r2 = Math.max(0.5, Math.min(ir, iw / 2, ih / 2));
          cr.moveTo(ix + iw - r2, iy);
          cr.arc(ix + iw - r2, iy + r2, r2, -Math.PI / 2, 0);
          cr.arc(ix + iw - r2, iy + ih - r2, r2, 0, Math.PI / 2);
          cr.arc(ix + r2, iy + ih - r2, r2, Math.PI / 2, Math.PI);
          cr.arc(ix + r2, iy + r2, r2, Math.PI, 3 * Math.PI / 2);
          cr.closePath();
          cr.setSourceRGBA(...col(m.glass || [42, 41, 49, 250]));
          cr.fill();
          cr.restore();
        }
      } else if (k === 'shim') {                   // 文字微光:同样的字叠一层亮的,只露出一条两头淡的竖带
        const [, tx, cy, text, size, bold, c, sxv] = p;
        const [lay, , th] = layout(cr, text, size, bold);
        const n = 8, SW = m.shim_w || 48;
        for (let j = 0; j < n; j++) {
          const fa = 1 - Math.abs(j + 0.5 - n / 2) / (n / 2);
          const x0 = tx + sxv - SW / 2 + j * SW / n;
          cr.save();
          cr.newPath();
          cr.rectangle(x0, cy - th, SW / n, 2 * th);
          cr.clip();
          const cc = col(c);
          cr.setSourceRGBA(cc[0], cc[1], cc[2], cc[3] * fa);
          cr.moveTo(tx, cy - th / 2);
          PangoCairo.show_layout(cr, lay);
          cr.restore();
        }
      } else if (k === 'txt') {
        const [, tx, cy, text, size, bold, c, al] = p;
        const [lay, tw, th] = layout(cr, text, size, bold);
        const px = tx - (al === 'r' ? tw : al === 'c' ? tw / 2 : 0);
        cr.setSourceRGBA(...col(c));
        cr.moveTo(px, cy - th / 2);
        PangoCairo.show_layout(cr, lay);
      }
    }
    cr.restore();
    cr.$dispose();
  }
}

// 屏幕四周光圈(借鼠标 / 后台操作时亮,同 Mac / Windows:四边一圈圈由外向内渐隐、淡入淡出、慢慢呼吸)
const GLOW_W = 26, GLOW_FADE_S = 0.35, GLOW_PERIOD_S = 1.8, GLOW_BREATH = 0.55;
const now = () => GLib.get_monotonic_time() / 1e6;

export class Glow {
  constructor() {
    this.area = new St.DrawingArea({reactive: false});
    this.area.hide();
    Main.layoutManager.addTopChrome(this.area);
    this.area.connect('repaint', a => this._draw(a));
    this.c = [255, 159, 10];
    this.until = 0;
    this.env = 0;
    this.t = now();
    this._timer = 0;
  }

  destroy() {
    if (this._timer) GLib.source_remove(this._timer);
    this._timer = 0;
    Main.layoutManager.removeChrome(this.area);
    this.area.destroy();
  }

  // secs = 亮多久(动作还在就反复调来续);0 = 淡出
  set(rgb, secs) {
    this.c = rgb;
    this.until = secs > 0 ? now() + Math.min(600, secs) : 0;
    const m = Main.layoutManager.primaryMonitor;
    this.area.set_position(m.x, m.y);
    this.area.set_size(m.width, m.height);
    if (!this._timer) {
      this.t = now();
      this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 40, () => this._tick());
    }
  }

  _tick() {
    const t = now(), dt = Math.min(0.1, t - this.t);
    this.t = t;
    const tgt = t < this.until ? 1 : 0, step = dt / GLOW_FADE_S;
    this.env = tgt > this.env ? Math.min(tgt, this.env + step) : Math.max(tgt, this.env - step);
    const a = this.env * (1 - GLOW_BREATH * (0.5 - 0.5 * Math.cos(2 * Math.PI * t / GLOW_PERIOD_S)));
    if (a <= 0.005 && tgt === 0) {
      this.area.hide();
      this._timer = 0;
      return GLib.SOURCE_REMOVE;
    }
    this.area.opacity = Math.round(255 * a);
    if (!this.area.visible) { this.area.show(); this.area.queue_repaint(); }
    return GLib.SOURCE_CONTINUE;
  }

  _draw(area) {
    const cr = area.get_context();
    const [W, H] = area.get_surface_size();
    const n = 10;
    for (let i = 0; i < n; i++) {
      const kk = 1 - i / n, inset = i * GLOW_W / n + 1;
      rrPath(cr, inset, inset, W - 2 * inset, H - 2 * inset, 12);
      cr.setSourceRGBA(this.c[0] / 255, this.c[1] / 255, this.c[2] / 255, 0.85 * kk * kk);
      cr.setLineWidth(GLOW_W / n + 0.6);
      cr.stroke();
    }
    cr.$dispose();
  }
}
