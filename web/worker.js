// 정의를 실행하는 worker. 설계 문서 §19.5.
//
// **정의는 여기서만 돈다.** worker 에는 document 가 없으므로 남이 쓴 코드가
// 페이지를 바꾸거나 다른 곳으로 보낼 수 없다. 무한 루프에 빠져도 메인 스레드는
// 멀쩡하고, terminate() 로 죽일 수 있다.
//
// 메인 스레드는 결과 데이터만 받는다. 좌표 버퍼는 transferable 이라 복사 없이
// 넘어간다 (§11.1).

"use strict";

// 런타임은 같은 출처에서 온다 (§19.14). CDN 에서 받으면 connect-src 에 그
// 출처를 열어 두어야 하고, 그러면 정의도 그리로 보낼 수 있다.
//
// **버전이 없다.** 버전은 web/pyodide.sha256 한 곳에만 적힌다.
// python web/fetch_pyodide.py 가 받아 둔다 — 안 돌리면 여기서 404 로 죽는다.
// 폴백은 두지 않는다. 폴백이 있으면 막으려던 구멍이 그대로 남는다
const PYODIDE_DIR = new URL("./pyodide/", import.meta.url).href;

/** indexURL 을 **명시로** 넘긴다.
 *
 * 안 넘기면 Pyodide 가 일부러 예외를 던져 스택 트레이스에서 제 파일 이름을
 * 뽑아 쓴다. 여기서는 위치를 이미 아는데 그 추론에 기댈 이유가 없다.
 */
const PYODIDE_OPTIONS = { indexURL: PYODIDE_DIR };

// 정의가 밖으로 내보낼 수 있는 통로 (§19.5). Pyodide 는 `js` 모듈로 전역을
// 그대로 열어 주므로, 여기 남는 것은 `import js` 한 줄이면 닿는다.
//
// `Worker` 가 목록에 있는 이유는 그것 자체가 통로여서가 아니라, 중첩 worker 가
// **손대지 않은 전역**을 새로 받기 때문이다. 하나 띄우면 지운 것이 다 돌아온다.
// `caches` 도 마찬가지로 `add(url)` 이 실제 요청을 낸다.
//
// 부팅이 **끝난 뒤에** 지운다. Pyodide 자신이 wasm 과 stdlib 을 fetch 로 받는다.
const NETWORK_GLOBALS = [
  "fetch", "XMLHttpRequest", "WebSocket", "EventSource", "WebTransport",
  "Worker", "SharedWorker", "importScripts", "caches",
];

/** 전역 하나를 끊는다. 끊었는지는 **이름을 다시 읽어** 확인한다.
 *
 * `delete self.fetch` 는 아무것도 안 지운다. `fetch` 는 self 의 own property 가
 * 아니라 `WorkerGlobalScope.prototype` 에 있어서, delete 는 `true` 를 돌려주고
 * 이름은 그대로 살아 있다. 지운 줄 알고 넘어가기 딱 좋다.
 *
 * 그래서 둘을 다 한다 — 사슬을 훑어 지우고, **지워졌든 아니든** own property
 * 로 못질한다. non-configurable 이라 지우지도 덮지도 못한다.
 *
 * 지워진 뒤에도 못질하는 것은, 이름이 비어 있으면 그 자리에 다시 대입할 수
 * 있기 때문이다. 원본을 되찾는 길은 아니지만 — 정의는 여기가 끝난 뒤에 도니
 * 참조를 잡을 시점이 없다 — 열어 둘 이유도 없다.
 */
function revoke(name) {
  for (let obj = self; obj; obj = Object.getPrototypeOf(obj)) {
    if (Object.prototype.hasOwnProperty.call(obj, name)) {
      try { delete obj[name]; } catch (_) {}
    }
  }
  try {
    Object.defineProperty(self, name, {
      value: undefined, writable: false, configurable: false,
    });
  } catch (_) {}
}

/** 부팅이 끝난 뒤 통로를 전부 끊는다. 하나라도 남으면 **부팅을 실패시킨다.**
 *
 * 반쯤 끊긴 채로 도는 것이 제일 나쁘다 — 화면은 멀쩡하고 구멍만 남는다.
 * 여기서 죽으면 워치독이 아니라 오류 메시지가 뜨므로 원인이 그 자리에 보인다.
 */
function revokeNetwork() {
  for (const name of NETWORK_GLOBALS) revoke(name);
  const alive = NETWORK_GLOBALS.filter((n) => typeof self[n] !== "undefined");
  if (alive.length) {
    throw new Error("Could not close the network paths: " + alive.join(", "));
  }
}


let py = null;

// 모듈 worker 는 strict 모드다. 맨이름 대신 self 를 명시해 둔다
function status(text) {
  self.postMessage({ type: "status", text });
}

// 모듈 평가 중이나 handler 밖에서 터진 것도 메인 스레드가 알아야 한다.
// 안 그러면 onerror 의 빈 메시지("worker 오류")만 남고 원인을 알 수 없다
self.onerror = (ev) => {
  self.postMessage({
    type: "fatal",
    error: [ev && ev.message, ev && ev.filename, ev && ev.lineno]
      .filter(Boolean).join(" ") || "Unknown error inside the worker",
  });
};

async function boot() {
  status("Downloading Pyodide…");
  const { loadPyodide } = await import(PYODIDE_DIR + "pyodide.mjs");
  py = await loadPyodide(PYODIDE_OPTIONS);

  status("Loading the engine…");
  await import("./engine.js?v=fa49d597");   // globalThis.ENGINE_SOURCES 를 채운다

  const FS = py.FS;
  const made = new Set();
  const mkdirp = (dir) => {
    let cur = "";
    for (const part of dir.split("/").filter(Boolean)) {
      cur += "/" + part;
      if (!made.has(cur)) { try { FS.mkdir(cur); } catch (_) {} made.add(cur); }
    }
  };
  mkdirp("/engine");
  for (const [path, source] of Object.entries(globalThis.ENGINE_SOURCES)) {
    const full = "/engine/" + path;
    mkdirp(full.slice(0, full.lastIndexOf("/")));
    FS.writeFile(full, source, { encoding: "utf8" });
  }

  // 정의 실행 층은 파일로 온다. JS 문자열에 박으면 파이썬 docstring 의
  // 백틱이 템플릿 리터럴을 끊는다 (web/boot.py 머리말)
  py.runPython(globalThis.ENGINE_SOURCES["boot.py"]);

  // 여기부터는 정의가 돌 수 있다. 그 전에 통로를 끊는다 (§19.5)
  revokeNetwork();
  status("");
}

// Pyodide 의 toJs 는 dict_converter 를 주지 않으면 dict 를 Map 으로 준다.
// 주더라도 판본에 따라 중첩까지 미치지 않을 수 있는데, Map 이 섞이면
// Object.entries 가 **조용히 빈 배열**을 돌려준다. 화면이 비는데 오류는 없다.
// 경계에서 한 번 눌러 평범한 객체로 만든다.
function toPlain(value) {
  if (value instanceof Map) {
    const out = {};
    for (const [k, v] of value) out[k] = toPlain(v);
    return out;
  }
  if (Array.isArray(value)) return value.map(toPlain);
  return value;
}

function call(name, args) {
  const fn = py.globals.get(name);
  const proxy = fn(...args);
  const out = proxy.toJs ? proxy.toJs({ dict_converter: Object.fromEntries }) : proxy;
  if (proxy.destroy) proxy.destroy();
  fn.destroy();
  return toPlain(out);
}

function sceneBytes(name) {
  const fn = py.globals.get(name);
  const proxy = fn();
  const view = proxy.toJs();
  proxy.destroy();
  fn.destroy();
  // WASM 메모리를 가리키는 view 를 그대로 넘기면 안 된다. 복사본을 transfer 한다
  return view.slice().buffer;
}

/** 파이썬 예외는 traceback 이 통째로 message 에 들어온다. 마지막 줄이 본론이다. */
function describe(e) {
  const text = String((e && e.message) || e);
  const lines = text.trim().split("\n").filter((l) => l.trim());
  const last = lines[lines.length - 1] || text;
  // 파이썬 쪽 오류면 마지막 줄만, 그 밖에는 그대로
  return lines.length > 3 ? last : text;
}

const HANDLERS = {
  prepare: (msg) => ({ result: call("prepare", [msg.source]) }),
  addAxisSet: (msg) => ({ result: call("add_axis_set", [msg.source, msg.factory]) }),
  removeAxisSet: (msg) => ({ result: call("remove_axis_set", [msg.source, msg.setId]) }),
  axisOp: (msg) => ({ result: call("axis_op", [msg.source, msg.setId, msg.op]) }),
  evaluate: (msg) => {
    const result = call("evaluate", [JSON.stringify(msg.angles), msg.maxStep]);
    const buffer = sceneBytes("scene_bytes");
    return { result, buffer };
  },
  // 편집 모드의 무대 (§19.15). 절단 각도를 안 받는다 — 마커는 축 방향만 쓴다
  axisScene: (msg) => {
    const result = call("axis_scene", [msg.source]);
    const buffer = sceneBytes("axis_scene_bytes");
    return { result, buffer };
  },
};

self.onmessage = async (ev) => {
  const msg = ev.data;
  if (msg.type === "boot") {
    try { await boot(); self.postMessage({ id: msg.id, ok: true }); }
    catch (e) {
      self.postMessage({ id: msg.id, ok: false, error: describe(e) });
    }
    return;
  }
  try {
    if (!py) throw new Error("The engine is not ready yet");
    const { result, buffer } = HANDLERS[msg.type](msg);
    self.postMessage({ id: msg.id, ok: true, result, buffer }, buffer ? [buffer] : []);
  } catch (e) {
    self.postMessage({ id: msg.id, ok: false, error: describe(e) });
  }
};
