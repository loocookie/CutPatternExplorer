// Pyodide 부팅과 정의 실행. 설계 문서 §19.
//
// 파이썬은 정의를 평가해 장면을 만들고, 카메라와 다시 그리기는 render.js 가
// 소유한다 (§11.1). 슬라이더가 움직일 때만 파이썬으로 넘어간다.

"use strict";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

// 엔진이 표준 라이브러리만 쓰므로 loadPackage 가 없다 (§12.2). 런타임 하나면 끝
const BOOT = `
import sys, json, traceback
sys.path.insert(0, "/engine")

from cutpattern.dsl import Puzzle
from cutpattern.render.scene import build_scene


def load(source):
    """정의를 실행하고 Puzzle 을 찾아 돌려준다.

    조각 모델이 없으므로 정의는 with puzzle(...) 블록 하나로 끝난다. 이름을
    강제하지 않고 namespace 에서 Puzzle 인스턴스를 찾는다.
    """
    ns = {"__name__": "__cutpattern__"}
    exec(compile(source, "<정의>", "exec"), ns)
    found = [v for v in ns.values() if isinstance(v, Puzzle)]
    if not found:
        raise ValueError("정의에 puzzle 블록이 없다. with puzzle(...) as p: 로 감싼다")
    return found[-1]


_state = {}


def prepare(source):
    p = load(source)
    _state["puzzle"] = p
    inputs = list(p.family.cut_angle_inputs())
    return json.dumps({
        "name": p.name,
        "inputs": inputs,
        "axisSets": [a.id for a in p.axis_sets],
        "ops": len(p.family.operations),
    })


def evaluate(angles_json, max_step):
    from cutpattern.engine.operations import Truncated
    p = _state["puzzle"]
    angles = json.loads(angles_json)
    reg, log = p.evaluate(angles, on_illegal="truncate")
    scene = build_scene(reg, p.family, max_step=max_step)
    trunc = [r for r in log if isinstance(r, Truncated)]
    note = ""
    if trunc:
        t = trunc[0]
        note = "각도 변경으로 연산 #%d(%s) 이후 %d개가 불가능해짐: %s" % (
            t.op_index, t.axis_id, t.remaining, t.reason
        )
    return json.dumps({
        "scene": {
            "xyz": scene.xyz, "starts": scene.starts, "counts": scene.counts,
            "groups": scene.groups, "kinds": scene.kinds,
            "labels": [list(x) for x in scene.labels], "axisSets": scene.axis_sets,
        },
        "carriers": len(reg),
        "length": reg.total_arc_length(),
        "note": note,
    })
`;

class Engine {
  constructor(onStatus) {
    this.py = null;
    this.onStatus = onStatus || (() => {});
  }

  async boot() {
    this.onStatus("Pyodide 를 받는 중…");
    const { loadPyodide } = await import(PYODIDE);
    this.py = await loadPyodide();

    // 번들을 파일 시스템에 푼다. 요청 하나로 받은 것이라 순서만 맞추면 된다
    this.onStatus("엔진을 올리는 중…");
    const FS = this.py.FS;
    const made = new Set();
    const mkdirp = (dir) => {
      const parts = dir.split("/").filter(Boolean);
      let cur = "";
      for (const part of parts) {
        cur += "/" + part;
        if (!made.has(cur)) { try { FS.mkdir(cur); } catch (_) {} made.add(cur); }
      }
    };
    mkdirp("/engine");
    for (const [path, source] of Object.entries(window.ENGINE_SOURCES)) {
      const full = "/engine/" + path;
      mkdirp(full.slice(0, full.lastIndexOf("/")));
      FS.writeFile(full, source, { encoding: "utf8" });
    }

    this.py.runPython(BOOT);
    this.onStatus("");
  }

  // 정의를 실행하고 슬라이더 정보를 돌려준다
  prepare(source) {
    return JSON.parse(this.py.globals.get("prepare")(source));
  }

  evaluate(angles, maxStep) {
    const raw = this.py.globals.get("evaluate")(JSON.stringify(angles), maxStep);
    const out = JSON.parse(raw);
    out.scene.xyz = Float64Array.from(out.scene.xyz);
    return out;
  }
}

window.Engine = Engine;
