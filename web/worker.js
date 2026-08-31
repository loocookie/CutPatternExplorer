// 정의를 실행하는 worker. 설계 문서 §19.5.
//
// **정의는 여기서만 돈다.** worker 에는 document 가 없으므로 남이 쓴 코드가
// 페이지를 바꾸거나 다른 곳으로 보낼 수 없다. 무한 루프에 빠져도 메인 스레드는
// 멀쩡하고, terminate() 로 죽일 수 있다.
//
// 메인 스레드는 결과 데이터만 받는다. 좌표 버퍼는 transferable 이라 복사 없이
// 넘어간다 (§11.1).

"use strict";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";


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
  const { loadPyodide } = await import(PYODIDE);
  py = await loadPyodide();

  status("Loading the engine…");
  await import("./engine.js?v=dffef604");   // globalThis.ENGINE_SOURCES 를 채운다

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

function sceneBytes() {
  const fn = py.globals.get("scene_bytes");
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
  axisOp: (msg) => ({ result: call("axis_op", [msg.source, msg.setId, msg.op, msg.other]) }),
  evaluate: (msg) => {
    const result = call("evaluate", [JSON.stringify(msg.angles), msg.maxStep]);
    const buffer = sceneBytes();
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
