// Pyodide 부팅과 정의 실행. 설계 문서 §19.
//
// 파이썬은 정의를 평가해 장면을 만들고, 카메라와 다시 그리기는 render.js 가
// 소유한다 (§11.1). 슬라이더가 움직일 때만 파이썬으로 넘어간다.

"use strict";

const PYODIDE = "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/pyodide.mjs";

// 엔진이 표준 라이브러리만 쓰므로 loadPackage 가 없다 (§12.2). 런타임 하나면 끝
const BOOT = `
import array, sys, json
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
    """정의를 평가하고 장면을 만든다. 좌표는 여기서 안 돌려준다.

    좌표를 JSON 으로 실으면 평탄화로 아낀 것을 문자열 파싱으로 도로 쓴다
    (§11.1). 실측으로 tessellation 을 4배 촘촘하게 하면 json.dumps 가 1.4ms
    에서 3.9ms 로 늘고 문자열이 54KB 에서 183KB 가 되며, 브라우저에서는 그만큼의
    JSON.parse 가 더 붙는다. 좌표는 `scene_bytes` 로 따로 가져간다.
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
    // 좌표는 JSON 을 태우지 않는다. 문자열로 만들었다 다시 파싱하면 평탄화로
    // 아낀 것을 도로 쓴다 (§11.1)
    const proxy = this.py.globals.get("evaluate")(JSON.stringify(angles), maxStep);
    const out = proxy.toJs({ dict_converter: Object.fromEntries });
    proxy.destroy();

    const buf = this.py.globals.get("scene_bytes")();
    const bytes = buf.toJs();
    buf.destroy();
    const xyz = new Float64Array(bytes.buffer, bytes.byteOffset, bytes.byteLength / 8);

    return {
      scene: {
        xyz,
        starts: out.starts, counts: out.counts,
        groups: out.groups, kinds: out.kinds,
        labels: out.labels, axisSets: out.axisSets,
      },
      carriers: out.carriers, length: out.length, note: out.note,
    };
  }
}

window.Engine = Engine;
