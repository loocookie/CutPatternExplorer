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

console.log(failures === 0 ? "\n전부 통과" : `\n실패 ${failures}개`);
process.exit(failures === 0 ? 0 : 1);
