// 정의가 밖으로 내보낼 통로를 끊는다. 설계 문서 §19.5.
//
//   node web/revoke.test.js
//
// **이 검사가 있는 이유는 `delete self.fetch` 가 거짓말을 하기 때문이다.**
// `fetch` 는 전역의 own property 가 아니라 `WorkerGlobalScope.prototype` 에
// 있어서, `delete` 는 `true` 를 돌려주고 이름은 그대로 산다. 브라우저에서
// 눈으로 보면 "지웠다" 로 보이고, 구멍은 그대로 남는다.
//
// worker.js 는 모듈이고 `self` 를 만지므로 node 에서 그대로 import 할 수 없다.
// 함수 두 개를 소스에서 오려내 가짜 전역에 물려 돌린다 — 진짜 worker 전역과
// 같은 모양(프로토타입에 `fetch`, own property 에 생성자들)으로 만든다.

"use strict";
const fs = require("fs");
const path = require("path");

let failures = 0;
function check(name, cond, extra) {
  if (cond) console.log("  OK   " + name);
  else { failures++; console.log("  FAIL " + name, extra !== undefined ? extra : ""); }
}

const WORKER = fs.readFileSync(path.join(__dirname, "worker.js"), "utf8");

// 목록과 두 함수만 오려낸다. 뒤는 Pyodide 를 만지므로 여기서 돌릴 수 없다
const from = WORKER.indexOf("const NETWORK_GLOBALS");
const to = WORKER.indexOf("let py = null;");
check("worker.js 에서 끊는 부분을 찾는다", from !== -1 && to > from);

const load = new Function(
  "self",
  WORKER.slice(from, to) + "\nreturn { revoke, revokeNetwork, NETWORK_GLOBALS };"
);

/** 진짜 worker 전역과 같은 모양. `fetch` 류는 프로토타입, 생성자는 own. */
function fakeGlobal(names) {
  const proto = {};
  for (const name of ["fetch", "importScripts"]) {
    if (names.includes(name)) proto[name] = function () {};
  }
  const self = Object.create(proto);
  for (const name of names) {
    if (name === "fetch" || name === "importScripts") continue;
    self[name] = name === "caches" ? {} : function () {};
  }
  return self;
}

// ---- 우선, 순진한 방법이 실패한다는 것부터 ----------------------------------
{
  const self = fakeGlobal(["fetch"]);
  const returned = delete self.fetch;
  check("delete self.fetch 는 true 를 주고 아무것도 안 지운다",
    returned === true && typeof self.fetch === "function",
    "이게 거짓이면 아래 검사는 아무것도 증명하지 않는다");
}

// ---- 전부 끊긴다 -------------------------------------------------------------
{
  const api = load(fakeGlobal([]));   // 목록만 꺼내려고 한 번 부른다
  const names = api.NETWORK_GLOBALS;
  check("끊을 목록에 fetch 와 Worker 가 있다",
    names.includes("fetch") && names.includes("Worker"),
    // Worker 는 그 자체가 통로여서가 아니라, 중첩 worker 가 손대지 않은
    // 전역을 새로 받아 지운 것이 전부 돌아오기 때문이다
    names.join(", "));

  const self = fakeGlobal(names);
  for (const name of names) {
    check("  " + name + " 이(가) 처음엔 있다", typeof self[name] !== "undefined");
  }

  const it = load(self);
  let threw = null;
  try { it.revokeNetwork(); } catch (e) { threw = e; }
  check("끊는 동안 안 죽는다", threw === null, threw && threw.message);

  const alive = names.filter((n) => typeof self[n] !== "undefined");
  check("전부 끊겼다", alive.length === 0, alive.join(", "));
}

// ---- 프로토타입에서 못 지우면 덮어서 가린다 ----------------------------------
{
  const proto = {};
  Object.defineProperty(proto, "fetch", { value: function () {}, configurable: false });
  const self = Object.create(proto);
  // strict 모드에서 non-configurable 을 delete 하면 TypeError 가 난다.
  // revoke 가 그걸 삼키고 덮는 쪽으로 넘어가야 한다
  const it = load(self);
  let threw = null;
  try { it.revoke("fetch"); } catch (e) { threw = e; }
  check("지울 수 없는 fetch 에서도 안 죽는다", threw === null, threw && threw.message);
  check("지울 수 없으면 가린다", typeof self.fetch === "undefined");
}

// ---- 가린 것은 되돌릴 수 없다 ------------------------------------------------
{
  const self = fakeGlobal(["fetch"]);
  const it = load(self);
  it.revoke("fetch");
  // 정의가 도로 열려고 해도 안 된다. non-configurable 이라 지우지도 덮지도 못한다
  let ok = true;
  try { delete self.fetch; } catch (_) {}
  try { self.fetch = function () {}; } catch (_) {}
  try {
    Object.defineProperty(self, "fetch", { value: function () {} });
  } catch (_) { ok = ok; }
  check("끊은 뒤에는 도로 못 넣는다", typeof self.fetch === "undefined");
}

// ---- 하나라도 남으면 부팅을 실패시킨다 ---------------------------------------
{
  // 끊을 수 없는 전역을 가진 브라우저를 흉내낸다. 반쯤 끊긴 채로 돌면
  // 화면은 멀쩡하고 구멍만 남으므로, 조용히 넘어가면 안 된다
  const self = fakeGlobal([]);
  Object.defineProperty(self, "fetch", {
    value: function () {}, configurable: false, writable: false,
  });
  const it = load(self);
  let threw = null;
  try { it.revokeNetwork(); } catch (e) { threw = e; }
  check("못 끊으면 던진다", threw !== null && /fetch/.test(threw.message),
    threw && threw.message);
}

console.log(failures === 0 ? "\n전부 통과" : "\n실패 " + failures + "개");
process.exit(failures === 0 ? 0 : 1);
