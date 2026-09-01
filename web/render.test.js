// 실루엣 자르기 검증. 설계 문서 §11.3.
//
// 브라우저 없이 도는 부분만 본다. 캔버스 컨텍스트를 스텁으로 갈아 끼우고
// moveTo / lineTo 호출을 받아 적는다. 이 로직이 틀리면 호가 구를 관통해
// 보이거나 조각이 끊기는데, 그림으로는 알아채기 어렵다.
//
//   node web/render.test.js

"use strict";
const fs = require("fs");
global.window = {};
eval(fs.readFileSync(__dirname + "/render.js", "utf8"));

function stubCtx() {
  const calls = [];
  return {
    calls,
    beginPath: () => calls.push(["begin"]),
    moveTo: (x, y) => calls.push(["move", x, y]),
    lineTo: (x, y) => calls.push(["line", x, y]),
    stroke: () => calls.push(["stroke"]),
    arc: () => {}, fill: () => {}, clearRect: () => {}, setTransform: () => {},
    strokeText: () => {}, fillText: () => {},
    set strokeStyle(v) {}, set lineWidth(v) {}, set lineJoin(v) {},
    set lineCap(v) {}, set font(v) {}, set fillStyle(v) {},
    set textAlign(v) {}, set textBaseline(v) {},
  };
}

function viewOf(points) {
  // 항등 회전이면 view 는 입력 그대로다
  const v = new Float64Array(points.length);
  v.set(points);
  return v;
}

function run(points, front) {
  const view = new SphereViewStub(points);
  const ctx = stubCtx();
  view.ctx = ctx;
  view._strokeAll(0, 0, 1, front);
  return ctx.calls.filter((c) => c[0] !== "begin" && c[0] !== "stroke");
}

class SphereViewStub extends window.SphereView {
  constructor(points) {
    super({
      getContext: () => stubCtx(),
      addEventListener: () => {},
      clientWidth: 100, clientHeight: 100,
    });
    this.scene = {
      xyz: points, starts: [0], counts: [points.length / 3],
      groups: [0], kinds: [0], labels: [], axisSets: ["a"],
    };
    this.view = viewOf(points);
  }
}

let failures = 0;
function check(name, cond, extra) {
  if (cond) { console.log("  OK   " + name); }
  else { failures++; console.log("  FAIL " + name, extra !== undefined ? extra : ""); }
}

// z 가 + -> - 로 넘어가는 폴리라인. 앞 조각과 뒤 조각으로 갈려야 한다
const crossing = [
  0, 0,  1,
  1, 0,  0.5,
  1, 0, -0.5,
  0, 0, -1,
];
const frontCalls = run(crossing, true);
const backCalls = run(crossing, false);

check("앞면은 한 조각으로 이어진다",
  frontCalls[0][0] === "move" && frontCalls.slice(1).every((c) => c[0] === "line"),
  frontCalls.map((c) => c[0]));
check("뒷면도 한 조각으로 이어진다",
  backCalls[0][0] === "move" && backCalls.slice(1).every((c) => c[0] === "line"),
  backCalls.map((c) => c[0]));

// z = 0 에서 정확히 잘렸는가. 세 번째 점(z=0.5)과 네 번째(z=-0.5) 사이 중점
const lastFront = frontCalls[frontCalls.length - 1];
check("앞 조각이 실루엣에서 끝난다 (x = 1)", Math.abs(lastFront[1] - 1) < 1e-12, lastFront);
const firstBack = backCalls[0];
check("뒤 조각이 같은 지점에서 시작한다", Math.abs(firstBack[1] - 1) < 1e-12, firstBack);

// 전부 앞쪽이면 자르지 않는다
const allFront = [0, 0, 1, 0.6, 0, 0.8, 0.8, 0, 0.6];
check("전부 앞쪽이면 조각이 하나", run(allFront, true).filter((c) => c[0] === "move").length === 1);
check("전부 앞쪽이면 뒷면에는 아무것도 없다", run(allFront, false).length === 0);

// + - + 로 두 번 넘나들면 앞쪽이 두 조각이어야 한다
const twice = [0, 0, 1, 1, 0, 0.4, 1, 0, -0.4, 0.4, 0, 0.6, 0, 0, 1];
check("두 번 넘나들면 앞 조각이 둘",
  run(twice, true).filter((c) => c[0] === "move").length === 2,
  run(twice, true).map((c) => c[0]));

// ---- 실제 장면으로 draw() 전체를 태운다 -------------------------------
//
// 필드 이름이 어긋나거나 인덱스가 범위를 벗어나는 배선 오류는 브라우저를 열기
// 전에 여기서 잡힌다.

const scenesPath = __dirname + "/scenes.js";
if (!fs.existsSync(scenesPath)) {
  console.log("");
  console.log("  건너뜀: web/scenes.js 가 없다. python web/export_scenes.py 를 먼저 돌린다");
  console.log(failures === 0 ? "\n전부 통과" : "\n실패 " + failures + "개");
  process.exit(failures === 0 ? 0 : 1);
}
eval(fs.readFileSync(scenesPath, "utf8"));

for (const name of Object.keys(window.SCENES)) {
  const raw = window.SCENES[name];
  const ctx = stubCtx();
  const v = new window.SphereView({
    getContext: () => ctx, addEventListener: () => {},
    clientWidth: 800, clientHeight: 600, width: 0, height: 0,
  });
  v.ctx = ctx;
  v.setScene({ ...raw, xyz: Float64Array.from(raw.xyz) });

  const moves = ctx.calls.filter((c) => c[0] === "move").length;
  const lines = ctx.calls.filter((c) => c[0] === "line").length;
  const finite = ctx.calls.every(
    (c) => c.length < 2 || (Number.isFinite(c[1]) && Number.isFinite(c[2]))
  );
  check(name + ": 조각을 그린다 (move " + moves + ", line " + lines + ")",
        moves > 0 && lines > raw.starts.length);
  check(name + ": 좌표가 전부 유한하다", finite);

  // 축 집합을 하나 끄면 그리는 양이 준다 (§11.5)
  const before = ctx.calls.length;
  v.hidden.add(0);
  ctx.calls.length = 0;
  v.draw();
  check(name + ": 축 집합을 끄면 덜 그린다", ctx.calls.length < before);
}

// ---- 크기 변화 -------------------------------------------------------
//
// 캔버스 내부 해상도는 dpr 배라 CSS 폭보다 크다. grid 항목의 min-width 가
// auto 면 그 값이 min-content 로 잡혀 열이 넓어지고, 넓어진 폭으로 다시 내부
// 해상도를 키우는 되먹임이 생긴다. CSS 로 고리를 끊었고 (index.html),
// 여기서는 그리기 쪽 몫을 본다.

function sizedView(w, h, dpr) {
  const ctx = stubCtx();
  const canvas = {
    getContext: () => ctx, addEventListener: () => {},
    clientWidth: w, clientHeight: h, width: 0, height: 0,
  };
  const saved = global.window.devicePixelRatio;
  global.window.devicePixelRatio = dpr;
  const v = new window.SphereView(canvas);
  v.ctx = ctx;
  v.scene = {
    xyz: new Float64Array([0, 0, 1, 1, 0, 0, 0, 1, 0]),
    starts: [0], counts: [3], groups: [0], kinds: [0], labels: [], axisSets: ["a"],
  };
  v.view = new Float64Array(v.scene.xyz.length);
  global.window.devicePixelRatio = saved;
  return { v, ctx, canvas, dpr };
}

{
  // 레이아웃 전에는 폭이 0 이다. 그때 그리면 캔버스만 지우고 끝난다
  const { v, ctx } = sizedView(0, 0, 1);
  v.draw();
  check("크기가 0 이면 아무것도 그리지 않는다", ctx.calls.length === 0, ctx.calls.length);
}

{
  // dpr 이 소수면 w * dpr 도 소수다. 반올림해서 비교하지 않으면 매 프레임
  // 캔버스를 다시 잡고, 그때마다 화면이 지워진다
  const { v, canvas, dpr } = sizedView(813, 611, 1.25);
  global.window.devicePixelRatio = dpr;
  v.draw();
  const first = [canvas.width, canvas.height];
  check("내부 해상도가 정수다",
    Number.isInteger(canvas.width) && Number.isInteger(canvas.height), first);
  canvas.width = first[0]; canvas.height = first[1];
  let resized = 0;
  Object.defineProperty(canvas, "width", {
    get: () => first[0], set: () => { resized++; }, configurable: true,
  });
  v.draw();
  check("같은 크기로 다시 그려도 캔버스를 다시 잡지 않는다", resized === 0, resized);
  global.window.devicePixelRatio = undefined;
}

// ---- 확대 (§11.6) --------------------------------------------------------
{
  const v = new SphereViewStub([0, 0, 1, 1, 0, 0]);

  check("기본 배율은 1", v.zoom === 1);

  const before = v._radius(100, 100);
  v.zoomBy(2);
  check("배율이 반지름에 곱해진다", v._radius(100, 100) === before * 2,
    v._radius(100, 100));

  // 드래그가 커서를 따라오려면 _ball 이 같은 반지름을 써야 한다 (§11.6)
  v.canvas.getBoundingClientRect = () => ({ left: 0, top: 0, width: 100, height: 100 });
  const R = v._radius(100, 100);
  const pt = v._ball({ clientX: 50 + R * 0.5, clientY: 50 });
  check("_ball 이 같은 반지름을 쓴다", Math.abs(pt[0] - 0.5) < 1e-12, pt);

  // 한계. 너무 줄이면 점이 되고 너무 키우면 실루엣이 화면을 벗어난다
  v.zoom = 1;
  for (let i = 0; i < 40; i++) v.zoomBy(0.5);
  check("아래로 한계가 있다", v.zoom === 0.4, v.zoom);
  check("한계에서는 안 바뀐다고 알린다", v.zoomBy(0.5) === false);

  for (let i = 0; i < 40; i++) v.zoomBy(2);
  check("위로 한계가 있다", v.zoom === 8, v.zoom);
  check("한계에서는 안 바뀐다고 알린다", v.zoomBy(2) === false);
}

// ---- 핀치와 휠 (§11.6) ---------------------------------------------------
//
// 기기 없이 확인해야 하는 부분이다. 리스너를 붙잡아 두고 포인터 이벤트를
// 손으로 흘려보낸다.
{
  const on = {};
  const canvas = {
    getContext: () => stubCtx(),
    addEventListener: (name, fn) => { on[name] = fn; },
    setPointerCapture: () => {}, releasePointerCapture: () => {},
    getBoundingClientRect: () => ({ left: 0, top: 0, width: 100, height: 100 }),
    clientWidth: 100, clientHeight: 100,
  };
  const v = new window.SphereView(canvas);
  v.scene = {
    xyz: [0, 0, 1], starts: [0], counts: [1],
    groups: [0], kinds: [0], labels: [], axisSets: ["a"],
  };
  v.view = new Float64Array([0, 0, 1]);

  check("휠과 포인터를 모두 듣는다",
    !!(on.wheel && on.pointerdown && on.pointermove && on.pointerup));

  // 휠을 위로 굴리면(deltaY < 0) 커진다
  v.zoom = 1;
  on.wheel({ deltaY: -100, preventDefault: () => {} });
  check("휠 위로 = 확대", v.zoom > 1, v.zoom);
  on.wheel({ deltaY: 100, preventDefault: () => {} });
  check("휠 아래로 = 축소", Math.abs(v.zoom - 1) < 1e-12, v.zoom);

  let prevented = 0;
  on.wheel({ deltaY: -10, preventDefault: () => { prevented++; } });
  check("휠 기본 동작을 막는다 — 안 막으면 페이지가 같이 스크롤된다", prevented === 1);

  // 두 손가락을 벌리면 그 비율만큼 확대된다
  v.zoom = 1;
  const rot = v.rot.slice ? v.rot.slice() : v.rot;
  on.pointerdown({ pointerId: 1, clientX: 40, clientY: 50 });
  on.pointerdown({ pointerId: 2, clientX: 60, clientY: 50 });   // 간격 20
  on.pointermove({ pointerId: 2, clientX: 80, clientY: 50 });   // 간격 40
  check("두 배로 벌리면 배율도 두 배", Math.abs(v.zoom - 2) < 1e-12, v.zoom);

  // 손가락 두 개일 때는 회전이 멈춰야 한다. 안 그러면 벌리는 동안 그림이 휘청인다
  const same = JSON.stringify([...v.rot]) === JSON.stringify([...rot]);
  check("핀치 중에는 회전하지 않는다", same);

  // 하나를 떼면 남은 손가락에서 회전을 이어 간다
  on.pointerup({ pointerId: 2 });
  on.pointermove({ pointerId: 1, clientX: 45, clientY: 55 });
  check("하나 떼면 회전이 돌아온다", JSON.stringify([...v.rot]) !== JSON.stringify([...rot]));
  check("떼어도 배율은 그대로", Math.abs(v.zoom - 2) < 1e-12, v.zoom);
}

console.log(failures === 0 ? "\n전부 통과" : `\n실패 ${failures}개`);
process.exit(failures === 0 ? 0 : 1);
