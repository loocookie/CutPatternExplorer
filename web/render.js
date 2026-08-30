// Canvas 2D 렌더러. 설계 문서 §11.1, §11.2, §11.3.
//
// 파이썬은 기하가 바뀔 때만 점 배열을 넘기고, 카메라와 매 프레임 다시 그리기는
// 여기가 소유한다. 이 경계가 성능을 정한다 (§11.1).

"use strict";

const ARC = 0;
const MARKER = 1;

// 축 집합별 색. vpython 뷰어와 같은 팔레트다 (§11)
const PALETTE = [
  [230, 64, 64], [51, 140, 242], [51, 191, 89],
  [242, 179, 38], [179, 89, 242], [38, 204, 199],
];

const STYLE = {
  sphere: "rgba(214, 222, 235, 0.55)",
  silhouette: "rgba(120, 134, 158, 0.55)",
  // 뒤쪽 호는 반투명 구를 통해 보이므로 흐리게. 앞뒤 구분이 이걸로 난다 (§11.3)
  backAlpha: 0.22,
  frontAlpha: 1.0,
  arcWidth: 2.0,
  markerWidth: 3.0,
  markerAlpha: 0.85,
  label: "12px ui-sans-serif, system-ui, sans-serif",
};

// ---- 3x3 회전 ----------------------------------------------------------

function matMul(a, b) {
  const m = new Float64Array(9);
  for (let i = 0; i < 3; i++)
    for (let j = 0; j < 3; j++)
      m[i * 3 + j] = a[i * 3] * b[j] + a[i * 3 + 1] * b[3 + j] + a[i * 3 + 2] * b[6 + j];
  return m;
}

function axisAngle(x, y, z, angle) {
  const n = Math.hypot(x, y, z);
  if (n < 1e-12) return new Float64Array([1, 0, 0, 0, 1, 0, 0, 0, 1]);
  x /= n; y /= n; z /= n;
  const s = Math.sin(angle), c = Math.cos(angle), t = 1 - c;
  return new Float64Array([
    t * x * x + c,     t * x * y - s * z, t * x * z + s * y,
    t * x * y + s * z, t * y * y + c,     t * y * z - s * x,
    t * x * z - s * y, t * y * z + s * x, t * z * z + c,
  ]);
}

// ---- 뷰 ----------------------------------------------------------------

class SphereView {
  constructor(canvas) {
    this.canvas = canvas;
    this.ctx = canvas.getContext("2d");
    this.rot = axisAngle(1, 0.4, 0, -0.5);
    this.scene = null;
    this.view = null;          // 변환된 좌표. 장면이 바뀔 때만 다시 잡는다
    this.hidden = new Set();   // 꺼진 축 집합 인덱스 (§11.5)
    this.showMarkers = true;
    this.showLabels = true;
    this._bindDrag();
  }

  setScene(scene) {
    this.scene = scene;
    this.view = new Float64Array(scene.xyz.length);
    this.draw();
  }

  // 마우스 위치를 구 위의 점으로. 밖이면 실루엣으로 밀어 넣는다
  _ball(ev) {
    const r = this.canvas.getBoundingClientRect();
    const R = Math.min(r.width, r.height) * 0.45;
    const x = (ev.clientX - r.left - r.width / 2) / R;
    const y = -(ev.clientY - r.top - r.height / 2) / R;
    const d = x * x + y * y;
    if (d <= 1) return [x, y, Math.sqrt(1 - d)];
    const s = 1 / Math.sqrt(d);
    return [x * s, y * s, 0];
  }

  _bindDrag() {
    let last = null;
    const down = (ev) => { last = this._ball(ev); this.canvas.setPointerCapture(ev.pointerId); };
    const move = (ev) => {
      if (!last) return;
      const now = this._ball(ev);
      // arcball: 두 점 사이 회전을 누적한다
      const ax = last[1] * now[2] - last[2] * now[1];
      const ay = last[2] * now[0] - last[0] * now[2];
      const az = last[0] * now[1] - last[1] * now[0];
      const dot = Math.min(1, Math.max(-1, last[0] * now[0] + last[1] * now[1] + last[2] * now[2]));
      const angle = Math.acos(dot);
      if (angle > 1e-6) this.rot = matMul(axisAngle(ax, ay, az, angle), this.rot);
      last = now;
      this.draw();
    };
    const up = (ev) => { last = null; try { this.canvas.releasePointerCapture(ev.pointerId); } catch (_) {} };
    this.canvas.addEventListener("pointerdown", down);
    this.canvas.addEventListener("pointermove", move);
    this.canvas.addEventListener("pointerup", up);
    this.canvas.addEventListener("pointercancel", up);
  }

  // ---- 그리기 ---------------------------------------------------------

  draw() {
    const scene = this.scene;
    if (!scene) return;
    const ctx = this.ctx, canvas = this.canvas;
    const dpr = window.devicePixelRatio || 1;
    const w = canvas.clientWidth, h = canvas.clientHeight;
    // 레이아웃 전이면 0 이다. 그때 그리면 캔버스만 지우고 끝난다
    if (!w || !h) return;
    // w * dpr 은 소수일 수 있다. 대입하면 잘리므로 비교가 늘 참이 되어 매
    // 프레임 캔버스를 다시 잡게 된다. 반올림한 값으로 비교하고 대입한다
    const pw = Math.round(w * dpr), ph = Math.round(h * dpr);
    if (canvas.width !== pw || canvas.height !== ph) {
      canvas.width = pw; canvas.height = ph;
    }
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, w, h);

    const cx = w / 2, cy = h / 2, R = Math.min(w, h) * 0.45;
    const m = this.rot, xyz = scene.xyz, view = this.view;

    // §11.1 정사영. 전체를 한 번에 변환한다
    for (let k = 0; k < xyz.length; k += 3) {
      const x = xyz[k], y = xyz[k + 1], z = xyz[k + 2];
      view[k]     = m[0] * x + m[1] * y + m[2] * z;
      view[k + 1] = m[3] * x + m[4] * y + m[5] * z;
      view[k + 2] = m[6] * x + m[7] * y + m[8] * z;
    }

    // §11.3 앞뒤 구분: 뒤쪽 호 -> 반투명 원반 -> 앞쪽 호
    this._strokeAll(cx, cy, R, false);
    ctx.beginPath();
    ctx.arc(cx, cy, R, 0, Math.PI * 2);
    ctx.fillStyle = STYLE.sphere;
    ctx.fill();
    ctx.strokeStyle = STYLE.silhouette;
    ctx.lineWidth = 1;
    ctx.stroke();
    this._strokeAll(cx, cy, R, true);

    if (this.showMarkers && this.showLabels) this._labels(cx, cy, R);
  }

  // front 가 참이면 depth > 0 인 조각만 그린다.
  // 실루엣을 가로지르는 호는 부호가 바뀌는 지점에서 잘라 두 층에 나눠 담는다 (§11.3)
  _strokeAll(cx, cy, R, front) {
    const ctx = this.ctx, scene = this.scene, view = this.view;
    ctx.lineJoin = "round";
    ctx.lineCap = "round";
    for (let i = 0; i < scene.starts.length; i++) {
      const kind = scene.kinds[i];
      if (kind === MARKER && !this.showMarkers) continue;
      const group = scene.groups[i];
      if (this.hidden.has(group)) continue;

      const rgb = PALETTE[group % PALETTE.length];
      const base = kind === MARKER ? STYLE.markerAlpha : STYLE.frontAlpha;
      const alpha = front ? base : base * STYLE.backAlpha;
      ctx.strokeStyle = `rgba(${rgb[0]},${rgb[1]},${rgb[2]},${alpha})`;
      ctx.lineWidth = kind === MARKER ? STYLE.markerWidth : STYLE.arcWidth;

      const start = scene.starts[i], count = scene.counts[i];
      ctx.beginPath();
      let open = false;
      for (let k = 0; k < count - 1; k++) {
        const a = (start + k) * 3, b = (start + k + 1) * 3;
        const za = view[a + 2], zb = view[b + 2];
        const ina = front ? za >= 0 : za <= 0;
        const inb = front ? zb >= 0 : zb <= 0;
        if (!ina && !inb) { open = false; continue; }

        let x0 = view[a], y0 = view[a + 1], x1 = view[b], y1 = view[b + 1];
        if (ina !== inb) {
          // z = 0 인 지점에서 자른다. 그 점은 실루엣 위이므로 화면 좌표가 정확하다
          const t = za / (za - zb);
          const xm = x0 + (x1 - x0) * t, ym = y0 + (y1 - y0) * t;
          if (ina) { x1 = xm; y1 = ym; } else { x0 = xm; y0 = ym; }
        }
        if (!open) { ctx.moveTo(cx + R * x0, cy - R * y0); open = true; }
        ctx.lineTo(cx + R * x1, cy - R * y1);
        if (ina && !inb) open = false;   // 실루엣을 넘어 나갔다. 다음은 새 조각
      }
      ctx.stroke();
    }
  }

  // 라벨은 구에 가려지지 않으므로 앞쪽 것만 그린다 (§11.4)
  _labels(cx, cy, R) {
    const ctx = this.ctx, m = this.rot;
    ctx.font = STYLE.label;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    for (const [text, x, y, z, group] of this.scene.labels) {
      if (this.hidden.has(group)) continue;
      const vz = m[6] * x + m[7] * y + m[8] * z;
      if (vz <= 0) continue;
      const vx = m[0] * x + m[1] * y + m[2] * z;
      const vy = m[3] * x + m[4] * y + m[5] * z;
      const rgb = PALETTE[group % PALETTE.length];
      const sx = cx + R * vx, sy = cy - R * vy;
      ctx.strokeStyle = "rgba(255,255,255,0.85)";
      ctx.lineWidth = 3;
      ctx.strokeText(text, sx, sy);
      ctx.fillStyle = `rgb(${rgb[0]},${rgb[1]},${rgb[2]})`;
      ctx.fillText(text, sx, sy);
    }
  }
}

window.SphereView = SphereView;
window.PALETTE = PALETTE;
