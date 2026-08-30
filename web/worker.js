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

// 엔진이 표준 라이브러리만 쓰므로 loadPackage 가 없다 (§12.2)
const BOOT = `
import array, sys, json
sys.path.insert(0, "/engine")

import math

import cutpattern.dsl as _dsl
from cutpattern import solids as _solids
from cutpattern.dsl import Puzzle
from cutpattern.render.scene import build_scene


def _namespace():
    """정의가 시작하는 이름 공간 (§19.7).

    저작 계층을 통째로 미리 넣어 둔다. 정의마다 같은 import 두 줄을 쓰게 하면
    정보가 0인 줄이 반복된다. GlowScript 가 vpython 에 하는 것과 같다.

    `dsl` 과 `solids` 의 `__all__` 은 겹치는 이름이 없다. 겹치면 어느 쪽이
    이겼는지가 보이지 않으므로, 겹치는 순간 알도록 확인한다.
    """
    ns = {"__name__": "__cutpattern__", "math": math, "S": _solids, "solids": _solids}
    clash = set(_dsl.__all__) & set(_solids.__all__)
    if clash:
        raise RuntimeError("저작 계층 이름이 겹친다: %s" % sorted(clash))
    for module in (_dsl, _solids):
        for name in module.__all__:
            ns[name] = getattr(module, name)
    return ns


def load(source):
    """정의를 실행하고 Puzzle 을 찾아 돌려준다.

    조각 모델이 없으므로 정의는 with puzzle(...) 블록 하나로 끝난다. 이름을
    강제하지 않고 namespace 에서 Puzzle 인스턴스를 찾는다.

    명시적인 import 도 그대로 동작한다. 미리 넣는 것은 이름 공간을 채우는
    것일 뿐 import 를 막지 않는다 — 예전에 만든 공유 링크와 예제가 살아 있어야
    한다.
    """
    ns = _namespace()
    exec(compile(source, "<정의>", "exec"), ns)
    found = [v for v in ns.values() if isinstance(v, Puzzle)]
    if not found:
        raise ValueError("정의에 puzzle 블록이 없다. with puzzle(...) as p: 로 감싼다")
    return found[-1]


_state = {}


def prepare(source):
    p = load(source)
    _state["puzzle"] = p
    return {
        "name": p.name,
        "inputs": list(p.family.cut_angle_inputs()),
        "axisSets": [a.id for a in p.axis_sets],
        "ops": len(p.family.operations),
    }


def evaluate(angles_json, max_step):
    """정의를 평가하고 장면을 만든다. 좌표는 여기서 안 돌려준다.

    좌표를 JSON 으로 실으면 평탄화로 아낀 것을 문자열 파싱으로 도로 쓴다
    (§11.1). 실측으로 tessellation 을 4배 촘촘하게 하면 json.dumps 가 1.4ms
    에서 3.9ms 로 늘고 문자열이 54KB 에서 183KB 가 된다. 좌표는 scene_bytes
    로 따로 가져간다.
    """
    from cutpattern.engine.operations import Truncated
    p = _state["puzzle"]
    angles = json.loads(angles_json)
    reg, log = p.evaluate(angles, on_illegal="truncate")
    scene = build_scene(reg, p.family, max_step=max_step)
    _state["scene"] = scene
    trunc = [r for r in log if isinstance(r, Truncated)]
    note = ""
    if trunc:
        t = trunc[0]
        note = "각도 변경으로 연산 #%d(%s) 이후 %d개가 불가능해짐: %s" % (
            t.op_index, t.axis_id, t.remaining, t.reason
        )
    # 좌표를 뺀 나머지는 작다. 폴리라인 개수에 비례하고 점 개수와 무관하다
    return {
        "starts": scene.starts, "counts": scene.counts,
        "groups": scene.groups, "kinds": scene.kinds,
        "labels": [list(x) for x in scene.labels], "axisSets": scene.axis_sets,
        "carriers": len(reg),
        "length": reg.total_arc_length(),
        "note": note,
    }


def scene_bytes():
    """좌표를 float64 바이트열로. 파싱 없이 Float64Array 가 된다.

    WASM 과 JS 가 둘 다 little-endian 이므로 바이트 순서를 맞출 필요가 없다.
    """
    return array.array("d", _state["scene"].xyz).tobytes()
`;

let py = null;

function status(text) {
  postMessage({ type: "status", text });
}

async function boot() {
  status("Pyodide 를 받는 중…");
  const { loadPyodide } = await import(PYODIDE);
  py = await loadPyodide();

  status("엔진을 올리는 중…");
  await import("./engine.js");   // globalThis.ENGINE_SOURCES 를 채운다

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

  py.runPython(BOOT);
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

const HANDLERS = {
  prepare: (msg) => ({ result: call("prepare", [msg.source]) }),
  evaluate: (msg) => {
    const result = call("evaluate", [JSON.stringify(msg.angles), msg.maxStep]);
    const buffer = sceneBytes();
    return { result, buffer };
  },
};

onmessage = async (ev) => {
  const msg = ev.data;
  if (msg.type === "boot") {
    try { await boot(); postMessage({ id: msg.id, ok: true }); }
    catch (e) { postMessage({ id: msg.id, ok: false, error: String(e && e.message || e) }); }
    return;
  }
  try {
    const { result, buffer } = HANDLERS[msg.type](msg);
    postMessage({ id: msg.id, ok: true, result, buffer }, buffer ? [buffer] : []);
  } catch (e) {
    postMessage({ id: msg.id, ok: false, error: String(e && e.message || e) });
  }
};
