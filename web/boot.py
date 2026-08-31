"""브라우저에서 정의를 실행하는 층. 설계 문서 §19.

worker 가 Pyodide 를 올린 뒤 이 파일을 실행한다 (`web/worker.js`).

**JS 문자열에 박지 않고 파일로 둔다.** 전에는 worker.js 의 백틱 템플릿
리터럴 안에 있었는데, 파이썬 docstring 이 백틱을 쓰는 순간 리터럴이 거기서
끊겨 worker.js 전체가 문법 오류가 됐다. 브라우저는 빈 메시지의 로드 실패만
알려 주므로 원인을 찾기 어렵다. 파일이면 그 구멍이 아예 없고, 테스트도
문자열을 오려내지 않고 그대로 import 한다.
"""

import array, ast, inspect, json, sys
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


def _compile(source):
    """문법 오류를 우리 규약의 말로 바꿔 준다.

    편집창의 정의는 **함수가 아니라 스크립트**다. 그런데 examples/ 가 전부
    `def build(): ... return p` 모양이라 `return p` 로 끝내기 쉽고, 파이썬 기본
    메시지("'return' outside function")는 그 규약을 설명해 주지 않는다.
    """
    try:
        return compile(source, "<정의>", "exec")
    except SyntaxError as exc:
        where = " (%d번째 줄)" % exc.lineno if exc.lineno else ""
        if exc.msg and "return" in exc.msg and "outside function" in exc.msg:
            raise SyntaxError(
                "정의는 함수가 아니라 그냥 실행되는 코드다%s. `return p` 를 지운다 — "
                "`with puzzle(...) as p:` 블록만 있으면 찾아서 쓴다." % where
            ) from None
        raise SyntaxError("문법 오류%s: %s" % (where, exc.msg)) from None


def load(source):
    """정의를 실행하고 Puzzle 을 찾아 돌려준다.

    조각 모델이 없으므로 정의는 with puzzle(...) 블록 하나로 끝난다. 이름을
    강제하지 않고 namespace 에서 Puzzle 인스턴스를 찾는다.

    명시적인 import 도 그대로 동작한다. 미리 넣는 것은 이름 공간을 채우는
    것일 뿐 import 를 막지 않는다 — 예전에 만든 공유 링크와 예제가 살아 있어야
    한다.
    """
    ns = _namespace()
    exec(_compile(source), ns)
    found = [v for v in ns.values() if isinstance(v, Puzzle)]
    if not found:
        # 예제 파일을 통째로 붙여 넣으면 정의가 함수 안에 있고 아무도 안 부른다
        callables = [k for k, v in ns.items()
                     if callable(v) and getattr(v, "__module__", None) == "__cutpattern__"]
        if callables:
            raise ValueError(
                "정의가 함수 %s 안에 있고 아무도 부르지 않았다. 함수를 벗기거나 "
                "맨 아래에서 호출한다." % ", ".join(sorted(callables))
            )
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


# ---- 메뉴가 코드를 쓴다 (§19.9) ----------------------------------------


def _taken_names(tree, ns):
    """이미 쓰인 이름. 미리 넣어 둔 저작 계층 이름도 포함한다 (§19.7).

    문자열로 찾으면 주석 안의 단어까지 세어 틀린다. 파싱한 트리에서 본다.
    """
    used = set(ns)
    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            used.add(node.id)
        elif isinstance(node, (ast.FunctionDef, ast.ClassDef)):
            used.add(node.name)
        elif isinstance(node, ast.arg):
            used.add(node.arg)
    return used


def _existing_ids(tree, ns):
    """이미 쓰인 축 집합 id. **문자열**이라 파이썬 이름과 겹쳐도 된다.

    슬라이더에 그대로 나오므로 `rhombic_dodecahedron2` 보다
    `rhombic_dodecahedron` 이 낫다.
    """
    ids = set()
    for node in ast.walk(tree):
        if (isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id in ns
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and isinstance(node.args[0].value, str)):
            ids.add(node.args[0].value)
    return ids


def _free_name(base, taken):
    if base not in taken:
        return base
    n = 2
    while f"{base}{n}" in taken:
        n += 1
    return f"{base}{n}"


def _offsets(source):
    """(줄, 열) -> 절대 위치. ast 가 주는 좌표를 문자열 인덱스로 바꾼다."""
    starts = [0]
    for line in source.splitlines(True):
        starts.append(starts[-1] + len(line))
    return lambda lineno, col: starts[lineno - 1] + col


SKELETON = '''%(call)s

with puzzle("%(id)s", %(var)s) as p:
    split(%(var)s)
'''


def _naming(factory):
    """프리셋이 정해 둔 짧은 이름과 축 id 접두사를 꺼낸다.

    축 id 는 이미 **약자 + 숫자**다 (`c0..c5`, `rd0..rd11`). 메뉴가 만드는
    변수도 같은 규약을 따르는 것이 자연스럽다 — `faces2` 보다 `c` 가 짧고,
    한두 글자 접두사는 저작 계층 이름과 겹칠 일이 없다.
    """
    params = inspect.signature(_namespace()[factory]).parameters
    default_id = params["id"].default
    prefix = params["prefix"].default if "prefix" in params else "a"
    if not isinstance(default_id, str):
        default_id = factory
    return default_id, prefix


def _call(factory, set_id, var, prefix, canonical):
    """축 집합을 만드는 한 줄. 접두사가 기본과 다를 때만 적는다.

    같은 입체를 두 번 넣으면 축 id 가 겹친다 — 접두사가 입체마다 고정이라
    `rd0` 이 두 집합에 생긴다. 축 id 는 전 집합에서 유일해야 하므로 (§5)
    두 번째부터는 접두사를 달리 준다.
    """
    if prefix == canonical:
        return '%s = %s("%s")' % (var, factory, set_id)
    return '%s = %s("%s", prefix="%s")' % (var, factory, set_id, prefix)


def add_axis_set(source, factory):
    """축 집합 하나를 정의에 끼워 넣고 새 소스를 돌려준다 (§19.9).

    메뉴는 **코드를 쓴다.** 숨은 상태를 들고 있으면 메뉴로 시작해 손으로 이어
    쓰는 길이 막히고, DSL 이 파이썬인 이유가 사라진다 (§9.1).

    맨 뒤에 붙일 수는 없다. 넣을 자리가 셋이다.

        edges = rhombic_dodecahedron("edges")     (1) with 블록 앞
        with puzzle("t", faces, edges) as p:      (2) 인자 목록. 곧 슬라이더 목록이다
            split(faces)
            split(edges)                          (3) 블록 **직속** 본문 맨 끝

    (3) 이 직속이어야 한다. `with turned(...)` 같은 중첩 블록 안에 들어가면
    회전된 상태에서 자르는 것이 되어 전혀 다른 퍼즐이 된다.

    문자열을 오려 붙이지 않고 `ast` 로 위치만 얻어 원본을 쪼갠다. `ast.unparse`
    로 재생성하면 주석과 서식이 다 날아간다.
    """
    ns = _namespace()
    if factory not in ns:
        raise ValueError("모르는 축 집합: %r" % factory)

    default_id, canonical = _naming(factory)

    stripped = source.strip()
    if not stripped:
        var = _free_name(canonical, set(ns))
        return SKELETON % {
            "call": _call(factory, default_id, var, canonical, canonical),
            "var": var, "id": default_id,
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(
            "코드에 문법 오류가 있어 넣을 수 없다 (%d번째 줄). 먼저 고친다."
            % (exc.lineno or 0)
        ) from None

    blocks = [
        node for node in tree.body
        if isinstance(node, ast.With)
        and isinstance(node.items[0].context_expr, ast.Call)
        and getattr(node.items[0].context_expr.func, "id", None) == "puzzle"
    ]
    taken = _taken_names(tree, ns)
    var = _free_name(canonical, taken)
    set_id = _free_name(default_id, _existing_ids(tree, ns))
    # 변수가 밀렸다는 것은 같은 입체가 이미 있다는 뜻이다. 축 id 도 밀려야 한다
    prefix = canonical if var == canonical else var

    if not blocks:
        # puzzle 블록이 없다. 골격째 만든다
        return source.rstrip("\n") + "\n\n" + SKELETON % {
            "call": _call(factory, set_id, var, prefix, canonical),
            "var": var, "id": set_id,
        }

    block = blocks[-1]              # 마지막 블록을 쓴다. load() 와 같은 규약
    call = block.items[0].context_expr
    if not call.args:
        raise ValueError("puzzle() 에 이름이 없다. puzzle(\"이름\", 축집합) 꼴이어야 한다")

    at = _offsets(source)
    body = block.body
    indent = " " * body[0].col_offset

    # 뒤에서부터 넣는다. 앞을 먼저 넣으면 뒤 위치가 밀린다
    edits = [
        # (3) 블록 직속 본문 맨 끝
        (at(body[-1].end_lineno, 0) + len(source.splitlines(True)[body[-1].end_lineno - 1]),
         "%ssplit(%s)\n" % (indent, var)),
        # (2) 인자 목록 = 슬라이더 목록
        (at(call.args[-1].end_lineno, call.args[-1].end_col_offset), ", %s" % var),
        # (1) with 블록 앞
        (at(block.lineno, 0), _call(factory, set_id, var, prefix, canonical) + '\n\n'),
    ]
    out = source
    for pos, text in edits:
        out = out[:pos] + text + out[pos:]
    return out
