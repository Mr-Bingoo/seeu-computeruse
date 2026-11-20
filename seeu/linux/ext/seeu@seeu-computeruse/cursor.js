// SeeU 代理光标(Linux 版,11-18):跟 Mac 版 seeu_lib/cursor_overlay.py、Windows 版 seeu/win/cursor.py 同一套样子和数字。
//   - 后台模式 = 紫色 + 「SeeU」;借用户鼠标键盘 = 亮橙 + 署名。颜色由 SeeU 传(读 设置.json)。
//   - 箭头白描边、身后一团光晕、右下角名牌胶囊;移动走一条弧线、到点冲过一点再回、按速度倾斜;点击时箭头缩一下 + 一圈波纹。
//   - 停下 5 秒后原地呼吸(放大 18%)、每 3 次呼吸扫一道反光、尖端闪一下;60 秒没动作淡出。
// 纯显示:reactive:false,鼠标直接穿过去,不抢焦点。画在 Shell 顶层(addTopChrome)。改数字先对照 win/cursor.py 顶上那一段。
import Cairo from 'cairo';
import GLib from 'gi://GLib';
import St from 'gi://St';
import Pango from 'gi://Pango';
import PangoCairo from 'gi://PangoCairo';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';

const WIN_W = 150, WIN_H = 90;            // 画布大小(同 Mac 的点)
const TIP = [40, 40];                      // 箭头尖端在画布里的位置
const MOVE_S = 0.28, MOVE_MAX_S = 0.65;
const RING_S = 0.45, FADE_AFTER_S = 60;
const ARC_K = 0.22, ARC_MAX = 90, OVERSHOOT = 1.25;
const TILT_K = 0.04, TILT_MAX = 0.35, GLOW_R = 30;
const GLOW_K = 0.55;     // 光晕浓度:渐变比 Windows 一圈圈叠的实,11-18 跟 Mac 真截图对过调到这个
const PRESS_S = [0.09, 0.17];
const IDLE_AFTER_S = 5, BREATH_AMP = 0.18, BREATH_S = 2.8;
const FOCUS_EVERY = 3, FOCUS_S = 1.0;
const SHINE_TAIL = [12.5, 16.5], SHINE_TIP = [0.8, 0.6], SHINE_W = 5.0;
const ARROW_C = [7, 9];
// 11-18 C-3.0 多任务(同 Mac / Windows 11-17):一个任务一只光标;排队中整只变淡 + 箭头右上飘 z、不呼吸
const MAX_CURSORS = 8, WAIT_ALPHA = 0.45, WAIT_MAX_S = 40, WAIT_FADE_S = 0.25;
const ZZ_S = 2.7, ZZ_FROM = [17, 3], ZZ_TO = [32, -22];
// 箭头外形(相对尖端,同 Mac):M 起点、L 直线、Q 二次曲线
const ARROW = [['M', 0.5, 1.5], ['L', 4, 17.5], ['Q', 4.6, 19.8, 6.2, 18.2], ['L', 9.2, 13.5], ['L', 14.8, 12.6],
  ['Q', 17, 12.1, 15.3, 10.6], ['L', 2, 0], ['Q', 0, -0.8, 0.5, 1.5]];

function rgb01(hex) {
  const m = /^#?([0-9a-f]{6})$/i.exec(hex || '');
  const v = m ? parseInt(m[1], 16) : 0x7F77DD;
  return [((v >> 16) & 255) / 255, ((v >> 8) & 255) / 255, (v & 255) / 255];
}

const now = () => GLib.get_monotonic_time() / 1e6;

export function travelS(x0, y0, x1, y1) {
  return Math.min(MOVE_MAX_S, 0.22 + Math.hypot(x1 - x0, y1 - y0) * 0.0009);
}

function easeBack(p, k = OVERSHOOT) {
  p -= 1;
  return 1 + (k + 1) * p * p * p + k * p * p;
}

function arcPoint(f, t, c, p) {
  const q = 1 - p;
  return [q * q * f[0] + 2 * q * p * c[0] + p * p * t[0], q * q * f[1] + 2 * q * p * c[1] + p * p * t[1]];
}

function arcCtl(f, t) {
  const side = Date.now() % 2 ? 1 : -1;
  const mx = (f[0] + t[0]) / 2, my = (f[1] + t[1]) / 2;
  const dx = t[0] - f[0], dy = t[1] - f[1], d = Math.hypot(dx, dy);
  if (d < 1) return [mx, my];
  const off = Math.min(ARC_MAX, d * ARC_K);
  let nx = -dy / d, ny = dx / d;
  if (ny > 0) { nx = -nx; ny = -ny; }
  if (side < 0) { nx = -nx; ny = -ny; }
  return [mx + nx * off, my + ny * off];
}

function pressScale(t) {
  const [a, b] = PRESS_S;
  if (t < 0 || t > a + b) return 1;
  return t < a ? 1 - 0.18 * (t / a) : 0.82 + 0.18 * ((t - a) / b);
}

const breathK = t => 0.5 - 0.5 * Math.cos(2 * Math.PI * t / BREATH_S);

function shine(t) {
  const total = BREATH_S * FOCUS_EVERY, u = t % total, f0 = total - FOCUS_S;
  let band = null, op = 0, fl = 0;
  if (u >= f0) {
    const q = (u - f0) / FOCUS_S, e = q * q * (3 - 2 * q);
    band = e; op = q < 0.999 ? 0.35 + 0.6 * e : 0;
  }
  if (u < 0.45) fl = t >= total ? 0.9 * (1 - u / 0.45) : 0;
  else if (u > total - 0.15) fl = 0.9 * (u - (total - 0.15)) / 0.15;
  return [band, op, fl];
}

function textColor([r, g, b]) {
  return 0.299 * r + 0.587 * g + 0.114 * b > 0.62 ? [0.10, 0.17, 0.27] : [1, 1, 1];
}

export class ProxyCursor {
  constructor() {
    this.area = new St.DrawingArea({reactive: false, width: WIN_W, height: WIN_H});
    this.area.hide();
    Main.layoutManager.addTopChrome(this.area);
    this.area.connect('repaint', a => this._draw(a));
    this.st = {cur: null, frm: null, to: null, ctl: null, t0: 0, dur: 0, tilt: 0, arrive: 0, press: null, ring: null,
      label: 'SeeU', color: [0.5, 0.47, 0.87], last: 0, alpha: 0, shown: false, fade: FADE_AFTER_S,
      labelRaw: 'SeeU', auto: false, waiting: false, waitT: 0, waitFade: 0};
    this._timer = 0;
    this.labelFn = null;        // 名牌写什么由 CursorSet 定(只剩一只写 SeeU,多只写任务名)
  }

  destroy() {
    if (this._timer) GLib.source_remove(this._timer);
    this._timer = 0;
    Main.layoutManager.removeChrome(this.area);
    this.area.destroy();
  }

  // kind = move | click;fadeMs = 停下多久后淡出(默认 60 秒,同 Mac);fadeMs = 0 马上藏
  show(kind, x, y, label, color, fadeMs, auto = false) {
    const st = this.st, t = now();
    if (!fadeMs) { st.shown = false; st.waiting = false; st.last = t - st.fade - 1; this._run(); return 0; }
    if (st.waiting) { st.waiting = false; st.waitFade = t + WAIT_FADE_S + 0.15; }   // 动了 = 不在排队了
    st.labelRaw = st.label = String(label || 'SeeU').slice(0, 40);
    st.auto = !!auto;
    st.color = rgb01(color);
    st.fade = Math.max(1, fadeMs / 1000);
    st.last = t;
    let delay = 0;
    if (st.cur === null || !st.shown || st.alpha < 0.05) {
      Object.assign(st, {cur: [x, y], frm: null, to: null, arrive: t});      // 从看不见到看见:直接出现在那里(同 Mac)
    } else {
      const dur = travelS(st.cur[0], st.cur[1], x, y);
      Object.assign(st, {frm: st.cur, to: [x, y], t0: t, dur, ctl: arcCtl(st.cur, [x, y]), arrive: t + dur});
      delay = dur;
    }
    st.shown = true;
    if (kind === 'click') { st.ring = t + delay; st.press = t + delay; }
    this._run();
    return delay;
  }

  // 排队中:打瞌睡(飘 z + 变淡);轮到了收
  wait(on) {
    const st = this.st, t = now();
    if (!!on !== st.waiting) {
      st.waiting = !!on;
      st.waitFade = t + WAIT_FADE_S + 0.15;
      if (on) st.waitT = t;
    }
    st.last = t;
    if (st.cur !== null) this._run();
  }

  live() {
    const st = this.st;
    return st.shown && st.cur !== null && now() - st.last < st.fade;
  }

  _run() {
    if (this._timer) return;
    this._timer = GLib.timeout_add(GLib.PRIORITY_DEFAULT, 16, () => {
      const alive = this._step();
      if (!alive) this._timer = 0;
      return alive ? GLib.SOURCE_CONTINUE : GLib.SOURCE_REMOVE;
    });
  }

  _step() {
    const st = this.st, t = now();
    if (st.cur === null) return false;
    if (st.to !== null) {
      const p = Math.min(1, (t - st.t0) / Math.max(0.05, st.dur));
      const prev = st.cur;
      st.cur = arcPoint(st.frm, st.to, st.ctl, Math.min(easeBack(p), 1.15));
      const vx = st.cur[0] - prev[0];
      const want = p < 1 ? Math.max(-TILT_MAX, Math.min(TILT_MAX, vx * TILT_K)) : 0;
      st.tilt += (want - st.tilt) * 0.18;
      if (p >= 1) { st.cur = st.to; st.to = null; }
    } else {
      st.tilt += (0 - st.tilt) * 0.18;
      if (Math.abs(st.tilt) < 0.002) st.tilt = 0;
    }
    if (st.waiting) {
      if (t - st.waitT > WAIT_MAX_S) { st.waiting = false; st.waitFade = t + WAIT_FADE_S + 0.15; }   // 没人来收就自己停
      else st.last = Math.max(st.last, t - 1);                                                      // 排队中不淡出
    }
    let want = st.shown && t - st.last < st.fade ? 1 : 0;
    if (st.waiting) want = Math.min(want, WAIT_ALPHA);
    if (want > 0 && t < st.waitFade) {                // 变淡 / 轮到变亮:0.25 秒匀速过渡
      const d = (1 / 60) / WAIT_FADE_S;
      st.alpha = want > st.alpha ? Math.min(want, st.alpha + d) : Math.max(want, st.alpha - d);
    } else {
      st.alpha += (want - st.alpha) * (want > st.alpha ? 0.35 : 0.12);
    }
    if (st.alpha < 0.02 && want === 0) {
      this.area.hide();
      st.alpha = 0;
      return false;
    }
    this.area.set_position(Math.round(st.cur[0] - TIP[0]), Math.round(st.cur[1] - TIP[1]));
    this.area.opacity = Math.round(255 * Math.min(1, st.alpha));
    if (!this.area.visible) this.area.show();
    this.area.queue_repaint();
    return true;
  }

  _arrowPath(cr) {
    let cur = null;
    for (const s of ARROW) {
      if (s[0] === 'M') { cr.moveTo(s[1], s[2]); cur = [s[1], s[2]]; }
      else if (s[0] === 'L') { cr.lineTo(s[1], s[2]); cur = [s[1], s[2]]; }
      else { cr.curveTo(s[1], s[2], s[1], s[2], s[3], s[4]); cur = [s[3], s[4]]; }   // 二次 → 三次(两个控制点同点,同 Mac 画法)
    }
    cr.closePath();
  }

  _draw(area) {
    const cr = area.get_context();
    const st = this.st, t = now(), col = st.color;
    const [tx, ty] = TIP;
    const still = st.to === null && Math.abs(st.tilt) < 0.002;
    const bt = t - st.arrive - IDLE_AFTER_S;
    const breathing = still && bt >= 0 && !st.waiting;      // 排队中(打瞌睡)不呼吸:两种等法分开(用户 11-17 定)
    const bk = breathing ? breathK(bt) : 0;
    // 光晕:径向渐变。平时透明度 0.19~0.41 来回;呼吸时跟着呼吸、略放大;点击时鼓一下
    let ga, gs;
    if (breathing) { ga = 0.19 + 0.22 * bk; gs = 1 + 0.1 * bk; }
    else { ga = 0.30 - 0.11 * Math.cos(Math.PI * t / (0.45 * Math.PI)); gs = 1; }
    if (st.press !== null) {
      const q = (t - st.press) / 0.4;
      if (q >= 0 && q <= 1) gs = 1 + 0.27 * (q < 0.25 ? q / 0.25 : Math.max(0, 1 - (q - 0.25) / 0.75));
    }
    const gcx = tx + 6, gcy = ty + 8, R = GLOW_R * gs;
    // 同 Windows:14 圈同心圆叠出来的那团光(圈里叠的透明度换成等价的渐变)
    const pat = new Cairo.RadialGradient(gcx, gcy, 0, gcx, gcy, R);
    const n = 14;
    for (let i = 0; i <= n; i++) {
      let a = 0;                                    // 半径 i/n 处叠了几层:外面那些圈都盖着它
      for (let j = Math.max(1, i); j <= n; j++) a = a + (1 - a) * ga * (1 - (j - 1) / n) * 0.22;
      pat.addColorStopRGBA(i / n, col[0], col[1], col[2], a * GLOW_K);
    }
    cr.setSource(pat);
    cr.arc(gcx, gcy, R, 0, 2 * Math.PI);
    cr.fill();
    // 点击波纹
    if (st.ring !== null && t >= st.ring) {
      const p = Math.min(1, (t - st.ring) / RING_S);
      if (p < 1) {
        cr.setSourceRGBA(col[0], col[1], col[2], 0.8 * (1 - p));
        cr.setLineWidth(2.5);
        cr.arc(tx, ty, 5 + 20 * p, 0, 2 * Math.PI);
        cr.stroke();
      }
    }
    // 箭头:先以尖端为中心放大 k(呼吸),再绕箭头中心缩放 sc(点击按下)、旋转(倾斜)
    const sc = st.press !== null ? pressScale(t - st.press) : 1;
    const k = 1 + BREATH_AMP * bk;
    cr.save();
    cr.translate(tx, ty);
    cr.scale(k, k);
    cr.translate(ARROW_C[0], ARROW_C[1]);
    cr.rotate(st.tilt);
    cr.scale(sc, sc);
    cr.translate(-ARROW_C[0], -ARROW_C[1]);
    this._arrowPath(cr);
    cr.setSourceRGBA(col[0], col[1], col[2], 1);
    cr.fillPreserve();
    if (breathing) {                                 // 反光:从尾部扫到尖端,只在箭头里面;到点尖端闪一下
      const [band, op, fl] = shine(bt);
      if (band !== null && op > 0.01) {
        cr.save();
        cr.clipPreserve();
        let ux = SHINE_TIP[0] - SHINE_TAIL[0], uy = SHINE_TIP[1] - SHINE_TAIL[1];
        const ul = Math.hypot(ux, uy); ux /= ul; uy /= ul;
        const cx = SHINE_TAIL[0] + (SHINE_TIP[0] - SHINE_TAIL[0]) * band, cy = SHINE_TAIL[1] + (SHINE_TIP[1] - SHINE_TAIL[1]) * band;
        cr.newPath();
        for (let j = -8; j <= 8; j++) {
          const o = j * SHINE_W / 8, a = op * (1 - Math.abs(j) / 9) * 0.32;
          const px = cx + ux * o, py = cy + uy * o;
          cr.setSourceRGBA(1, 1, 1, a);
          cr.setLineWidth(SHINE_W / 8 * 1.6);
          cr.moveTo(px - uy * 30, py + ux * 30); cr.lineTo(px + uy * 30, py - ux * 30);
          cr.stroke();
        }
        cr.restore();
        this._arrowPath(cr);
      }
      if (fl > 0.01) {
        const path = cr.copyPath();
        cr.newPath();
        const g = new Cairo.RadialGradient(1.4, 1.5, 0, 1.4, 1.5, 4.5);
        g.addColorStopRGBA(0, 1, 1, 1, Math.min(1, fl * 0.3 * 5 * 0.6));
        g.addColorStopRGBA(1, 1, 1, 1, 0);
        cr.setSource(g);
        cr.arc(1.4, 1.5, 4.5, 0, 2 * Math.PI);
        cr.fill();
        cr.appendPath(path);
      }
    }
    cr.setSourceRGBA(1, 1, 1, 1);
    cr.setLineWidth(1.6 / sc);
    cr.setLineJoin(Cairo.LineJoin.ROUND);
    cr.stroke();
    cr.restore();
    // 名牌:箭头右下的小胶囊(同 Mac 10 号半粗)
    const lay = PangoCairo.create_layout(cr);
    lay.set_font_description(Pango.FontDescription.from_string('Sans Semi-Bold 7.5'));
    st.label = this.labelFn ? this.labelFn(this) : st.labelRaw;
    lay.set_text(st.label, -1);
    const [, logical] = lay.get_pixel_extents();
    const tw = logical.width, th = logical.height;
    const pw = tw + 12, ph = th + 4, px = tx + 13, py = ty + 17, rr = ph / 2;
    cr.newPath();
    cr.arc(px + rr, py + rr, rr, Math.PI / 2, 3 * Math.PI / 2);
    cr.arc(px + pw - rr, py + rr, rr, -Math.PI / 2, Math.PI / 2);
    cr.closePath();
    cr.setSourceRGBA(col[0], col[1], col[2], 1);
    cr.fill();
    const tc = textColor(col);
    cr.setSourceRGBA(tc[0], tc[1], tc[2], 1);
    cr.moveTo(px + 6, py + 2);
    PangoCairo.show_layout(cr, lay);
    if (st.waiting) this._zz(cr, t, tx, ty, col);
    cr.$dispose();
  }

  // 打瞌睡:箭头右上方飘起 3 个 z(任务色、白描边),越飘越大、淡出;3 个错开 1/3(同 Mac / Windows)
  _zz(cr, t, tx, ty, col) {
    const st = this.st;
    for (let i = 0; i < 3; i++) {
      if (t - st.waitT < i * ZZ_S / 3) continue;
      const q = ((((t - st.waitT) / ZZ_S - i / 3) % 1) + 1) % 1;
      const op = q < 0.2 ? q / 0.2 : Math.max(0, 1 - (q - 0.2) / 0.8);
      const e = 1 - (1 - q) * (1 - q);
      const cx = tx + ZZ_FROM[0] + (ZZ_TO[0] - ZZ_FROM[0]) * e, cy = ty + ZZ_FROM[1] + (ZZ_TO[1] - ZZ_FROM[1]) * e;
      const lay = PangoCairo.create_layout(cr);
      const fd = Pango.FontDescription.from_string('Sans Bold');
      fd.set_absolute_size(10 * (0.6 + 0.9 * q) * Pango.SCALE);
      lay.set_font_description(fd);
      lay.set_text('z', -1);
      const [, lg] = lay.get_pixel_extents();
      const x0 = cx - lg.width / 2, y0 = cy - lg.height / 2;
      cr.setSourceRGBA(1, 1, 1, 0.9 * op);
      for (const [dx, dy] of [[-1, 0], [1, 0], [0, -1], [0, 1], [-0.7, -0.7], [0.7, 0.7], [-0.7, 0.7], [0.7, -0.7]]) {
        cr.moveTo(x0 + dx, y0 + dy);
        PangoCairo.show_layout(cr, lay);
      }
      cr.setSourceRGBA(col[0], col[1], col[2], op);
      cr.moveTo(x0, y0);
      PangoCairo.show_layout(cr, lay);
    }
  }
}

// 一个任务一只光标(key = 任务显示名:Claude、Claude2…;老调用不带 = '_' 共用一只)。
// auto = 名牌按规则:屏幕上只剩它一只时写「SeeU」,多只时写任务名;借鼠标的署名光标 auto = false 照写署名。
export class CursorSet {
  constructor() {
    this.map = new Map();
  }

  _get(key) {
    const t = now();
    for (const [k, c] of this.map) {                // 淡出完又过了一会的回收(别的任务的不受影响)
      if (!c.live() && !c.st.waiting && t - c.st.last > c.st.fade + 5) { c.destroy(); this.map.delete(k); }
    }
    let c = this.map.get(key);
    if (!c) {
      if (this.map.size >= MAX_CURSORS) {           // 有上限:挤掉最久没动的那只
        let oldK = null, oldT = Infinity;
        for (const [k, x] of this.map) if (x.st.last < oldT) { oldT = x.st.last; oldK = k; }
        this.map.get(oldK).destroy(); this.map.delete(oldK);
      }
      c = new ProxyCursor();
      c.labelFn = me => {
        let n = 0;
        for (const x of this.map.values()) if (x.live() || x === me) n++;
        return me.st.auto && n <= 1 ? 'SeeU' : me.st.labelRaw;
      };
      this.map.set(key, c);
    }
    return c;
  }

  show(kind, x, y, label, color, ms, key = '_', auto = false) {
    return this._get(key || '_').show(kind, x, y, label, color, ms, auto);
  }

  wait(key, on) {
    const c = this.map.get(key || '_');
    if (c) c.wait(on);
  }

  // key = '' 全藏(老行为);带 key 只藏那一只
  hide(key) {
    for (const [k, c] of this.map) if (!key || k === key) c.show('move', 0, 0, '', '', 0);
  }

  destroy() {
    for (const c of this.map.values()) c.destroy();
    this.map.clear();
  }
}
