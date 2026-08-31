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
from cutpattern.dsl import AxisSet, Puzzle
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
        raise RuntimeError("authoring names collide: %s" % sorted(clash))
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
        where = " (line %d)" % exc.lineno if exc.lineno else ""
        if exc.msg and "return" in exc.msg and "outside function" in exc.msg:
            raise SyntaxError(
                "a definition is a script, not a function%s. drop `return p` — "
                "a `with puzzle(...) as p:` block is all it takes." % where
            ) from None
        raise SyntaxError("syntax error%s: %s" % (where, exc.msg)) from None


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
    # 이름에 묶인 축 집합을 재 둔다. 편집 메뉴가 실제 축 id 를 채워 넣는다
    # (§19.12). puzzle() 인자가 아닌 것도 있다 — 기준으로만 쓰는 집합이 그렇다
    bound = [(key, v) for key, v in ns.items()
             if isinstance(v, AxisSet) and not key.startswith("_")]
    _state["sets"] = [
        {"id": v.id, "var": key, "axes": [a.id for a in v]} for key, v in bound
    ]
    # 편집 모드의 무대가 이걸 쓴다 (§19.15). 목록만으로는 마커를 못 만든다 —
    # 축 방향이 있어야 한다
    _state["axis_sets"] = [v for _, v in bound]
    found = [v for v in ns.values() if isinstance(v, Puzzle)]
    if not found:
        # 예제 파일을 통째로 붙여 넣으면 정의가 함수 안에 있고 아무도 안 부른다
        callables = [k for k, v in ns.items()
                     if callable(v) and getattr(v, "__module__", None) == "__cutpattern__"]
        if callables:
            raise ValueError(
                "the definition is inside %s and nothing calls it. unwrap the function "
                "or call it at the bottom." % ", ".join(sorted(callables))
            )
        raise ValueError("no puzzle block in the definition. wrap it in `with puzzle(...) as p:`")
    return found[-1]


_state = {}


def prepare(source):
    p = load(source)
    _state["puzzle"] = p
    return {
        "name": p.name,
        "inputs": list(p.family.cut_angle_inputs()),
        "axisSets": [a.id for a in p.axis_sets],
        # 그려지는 것만이 축 집합의 전부가 아니다. 기준으로만 쓰는 집합도
        # 고치고 지울 수 있어야 한다 (§19.12)
        "sets": _state.get("sets", []),
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
        note = "changing the angle made %d operations after #%d(%s) impossible: %s" % (
            t.remaining, t.op_index, t.axis_id, t.reason
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


def axis_scene():
    """축 마커만 담은 장면. 편집 모드의 무대다 (§19.15).

    이름 공간의 **모든** 축 집합을 쓴다. `puzzle()` 인자가 아닌 것 — 기준으로만
    쓰는 집합 — 도 고치려면 어디 있는지 보여야 한다 (§19.12).

    절단 각도를 안 받는다. 마커는 축 방향만 쓴다 (§11.4).
    """
    from cutpattern.render.scene import build_marker_scene

    scene = build_marker_scene([s.to_engine() for s in _state.get("axis_sets", [])])
    _state["axis_scene"] = scene
    return {
        "starts": scene.starts, "counts": scene.counts,
        "groups": scene.groups, "kinds": scene.kinds,
        "labels": [list(x) for x in scene.labels], "axisSets": scene.axis_sets,
    }


def axis_scene_bytes():
    return array.array("d", _state["axis_scene"].xyz).tobytes()


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


def _free_instance(base, taken):
    """`cube1`, `cube2` … 중 처음으로 비어 있는 것.

    번호를 **항상** 붙인다. 첫 번째만 `cube` 이고 두 번째부터 `cube2` 이면
    나중에 하나를 지웠을 때 이름이 들쭉날쭉해진다. 축 id 도 같은 번호를 쓰므로
    (`c1-0`) 집합과 축의 대응이 눈으로 보인다.
    """
    n = 1
    while f"{base}{n}" in taken:
        n += 1
    return n


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


def _default_id(factory):
    """프리셋이 정해 둔 집합 id. 표시용 텍스트다 ("Rhombic Dodecahedron")."""
    default = inspect.signature(_namespace()[factory]).parameters["id"].default
    return default if isinstance(default, str) else factory


def _names(default_id, n, taken):
    """`n` 번째 인스턴스의 (집합 id, 변수 이름).

    집합 id 는 슬라이더에 그대로 나오므로 띄어쓰기와 대문자를 쓴다. 변수는
    파이썬 식별자여야 하므로 **약자**를 쓴다 — 축 id 접두사와 같아서 `c1` 과
    `c1-0` 이 눈으로 묶인다 (§2.5).
    """
    from cutpattern.solids import abbrev

    set_id = "%s %d" % (default_id, n)
    return set_id, abbrev(set_id)


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
        raise ValueError("unknown axis set: %r" % factory)

    default_id = _default_id(factory)

    stripped = source.strip()
    if not stripped:
        n = _free_instance(default_id, set(ns))
        set_id, var = _names(default_id, n, set(ns))
        return SKELETON % {
            "call": '%s = %s("%s")' % (var, factory, set_id),
            "var": var, "id": set_id,
        }

    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(
            "cannot insert: the code has a syntax error (line %d). fix it first."
            % (exc.lineno or 0)
        ) from None

    blocks = [
        node for node in tree.body
        if isinstance(node, ast.With)
        and isinstance(node.items[0].context_expr, ast.Call)
        and getattr(node.items[0].context_expr.func, "id", None) == "puzzle"
    ]
    # 집합 id, 변수, **축 id 접두사**가 셋 다 비어 있는 번호를 고른다.
    #
    # 접두사가 집합 id 에서 유도된다는 것(§2.5)이 유일하다는 뜻은 아니다.
    # `abbrev("cube1")` 도 `abbrev("Cube 1")` 도 `c1` 이라, 손으로 `cube1` 이라
    # 쓴 정의에 메뉴가 `Cube 1` 을 얹으면 엔진이 거부한다 (§5):
    #
    #     axis id 'c1-0' appears in both 'cube1' and 'Cube 1'
    #
    # 손으로 지은 이름을 규칙에 맞추라고 할 수는 없으므로 메뉴가 비켜 간다.
    # §19.12 가 "안 쓰인 축을 기본값으로 고른다" 로 한 것과 같은 판단이다
    from cutpattern.solids import abbrev

    existing = _existing_ids(tree, ns)
    taken = _taken_names(tree, ns) | existing
    prefixes = {abbrev(x) for x in existing}
    n = 1
    while True:
        set_id, var = _names(default_id, n, taken)
        if set_id not in taken and var not in taken and var not in prefixes:
            break
        n += 1

    if not blocks:
        # puzzle 블록이 없다. 골격째 만든다
        return source.rstrip("\n") + "\n\n" + SKELETON % {
            "call": '%s = %s("%s")' % (var, factory, set_id),
            "var": var, "id": set_id,
        }

    block = blocks[-1]              # 마지막 블록을 쓴다. load() 와 같은 규약
    call = block.items[0].context_expr
    if not call.args:
        raise ValueError("puzzle() has no name. it should look like puzzle(\"name\", axes)")

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
        (at(block.lineno, 0), '%s = %s("%s")' % (var, factory, set_id) + '\n\n'),
    ]
    out = source
    for pos, text in edits:
        out = out[:pos] + text + out[pos:]
    return out


def _names_the_set(value, set_id):
    """이 식 어딘가에 첫 인자가 `set_id` 인 호출이 있는가. 바깥부터 본다."""
    layer = [value]
    while layer:
        below = []
        for node in layer:
            if (isinstance(node, ast.Call) and node.args
                    and isinstance(node.args[0], ast.Constant)
                    and node.args[0].value == set_id):
                return True
            below += list(ast.iter_child_nodes(node))
        layer = below
    return False


def _binding_for(tree, set_id):
    """`set_id` 를 만드는 대입문과 변수 이름을 찾는다.

    id 를 들고 있는 호출은 **감싸여 있을 수 있다.** 편집 메뉴가 겹겹이 쌓기
    때문이다 (§19.12).

        c1 = mirror(rotate(octahedron("Octahedron 1"), axis=(0, 0, 1), angle=45))

    맨 바깥 호출의 첫 인자만 보면 두 번째 편집부터 못 찾는다 — 지우기까지
    같이 막힌다. 식 안을 훑는다.
    """
    for node in tree.body:
        if not (isinstance(node, ast.Assign)
                and len(node.targets) == 1
                and isinstance(node.targets[0], ast.Name)):
            continue
        if _names_the_set(node.value, set_id):
            return node, node.targets[0].id
    return None, None


def _mentions(node, names):
    return any(isinstance(n, ast.Name) and n.id in names for n in ast.walk(node))


def _is_puzzle_block(stmt):
    return (isinstance(stmt, ast.With)
            and isinstance(stmt.items[0].context_expr, ast.Call)
            and getattr(stmt.items[0].context_expr.func, "id", None) == "puzzle")


def _bound(node):
    """이 문장이 만드는 이름들."""
    out = []
    targets = []
    if isinstance(node, ast.Assign):
        targets = node.targets
    elif isinstance(node, (ast.AnnAssign, ast.AugAssign, ast.For)):
        targets = [node.target]
    elif isinstance(node, ast.With):
        targets = [i.optional_vars for i in node.items if i.optional_vars]
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return [node.name]
    for target in targets:
        out += [n.id for n in ast.walk(target) if isinstance(n, ast.Name)]
    return out


def _feeds(node):
    """이 문장이 만든 이름을 결정하는 표현식들 — 값 쪽."""
    if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)):
        return [node.value] if node.value is not None else []
    if isinstance(node, ast.For):
        return [node.iter]
    if isinstance(node, ast.With):
        return [i.context_expr for i in node.items]
    if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        return node.body
    return []


def _doomed(tree, var):
    """`var` 에서 **파생된 이름까지** 모은다.

    한 단계만 보면 모자란다. 실제로 이렇게 깨졌다.

        pair = lambda a: [a, at_angle(a, 180, o1)[0]]
        a, b = tuple(pair(nearest(t1["t1-0"], o1)))
        with turned(a, 15):                  # o1 을 직접 쓰지 않는다

    `with turned(a, 15)` 는 `o1` 이라는 글자가 없어서 살아남고, `a` 를 만들던
    줄은 사라진다. 남는 것은 `NameError` 다. 이름이 아니라 **값의 흐름**을
    따라가야 한다.

    변수가 다시 대입되는 경우는 보지 않는다 — 흐름에 둔감한 근사라 그럴 때는
    더 지운다. 짧은 정의 스크립트에서 이름을 재사용하는 일은 드물고, 덜 지워
    깨진 코드를 남기는 쪽이 더 나쁘다.
    """
    names = {var}
    while True:
        grown = False
        for node in ast.walk(tree):
            # `with puzzle(...)` 의 머리에 이름이 있는 것은 슬라이더 목록이라는
            # 뜻이다. `p` 가 축 집합에서 파생된 것이 아니다
            if _is_puzzle_block(node):
                continue
            if not any(_mentions(e, names) for e in _feeds(node)):
                continue
            for name in _bound(node):
                if name not in names:
                    names.add(name)
                    grown = True
        if not grown:
            return names


def _prune(body, names, drop):
    """`names` 를 쓰는 문장을 걷어낸 새 본문. 지운 문장은 `drop` 에 쌓는다.

    겹블록은 **머리**가 그 이름을 쓰면 통째로 지운다 — `for x in c1:` 의 본문만
    남기면 `x` 가 어디서 오는지 사라진다. 머리가 안 쓰면 본문만 훑고, 본문이
    비면 그 블록도 지운다. 빈 블록은 문법 오류다.
    """
    kept = []
    for stmt in body:
        if isinstance(stmt, (ast.For, ast.With, ast.While, ast.If)):
            # `with puzzle(...)` 의 머리는 예외다. 인자에서 빼는 것으로 따로
            # 다룬다. 머리만 보고 지우면 퍼즐이 통째로 사라진다
            header = [] if _is_puzzle_block(stmt) else _feeds(stmt)
            if any(_mentions(h, names) for h in header):
                drop.append(stmt)
                continue
            stmt.body = _prune(stmt.body, names, drop)
            stmt.orelse = _prune(getattr(stmt, "orelse", []), names, drop)
            # 빈 퍼즐 블록은 여기서 지우지 않는다. 축 집합이 남아 있으면
            # 자르지 않은 퍼즐로 살려 두는 것이 맞고, 그 판단은 인자를 보는
            # 쪽에 있다
            if not stmt.body and not _is_puzzle_block(stmt):
                drop.append(stmt)
                continue
            kept.append(stmt)
        elif _mentions(stmt, names):
            drop.append(stmt)
        else:
            kept.append(stmt)
    return kept


def _coalesce(cuts):
    """겹치는 구간을 합친다.

    한 블록이 통째로 지워지면 그 블록과 자식이 둘 다 목록에 오른다. 겹친 채로
    뒤에서부터 자르면 앞서 적용한 결과 위에 옛 위치로 다시 자르게 되어, 끼워
    넣은 글자가 조용히 지워진다. 실제로 `pass` 가 그렇게 사라졌다.
    """
    merged = []
    for start, end, insert in sorted(cuts):
        if merged and start <= merged[-1][1]:
            prev = merged.pop()
            merged.append((prev[0], max(prev[1], end), prev[2] + insert))
        else:
            merged.append((start, end, insert))
    return merged


def remove_axis_set(source, set_id):
    """축 집합 하나와 **그것에 딸린 모든 코드**를 지우고 새 소스를 돌려준다.

    변형을 여럿 만들어 보다가 하나를 통으로 버리는 것이 실제 흐름이다. 참조를
    남기면 `NameError` 만 남으므로 같이 걷어낸다. 어디까지 딸린 것인지는 축
    집합이 무슨 **역할**이었는지가 아니라 **값의 흐름**이 정한다 (`_doomed`).

    넣을 때와 대칭이다 (§19.9). `ast` 로 위치만 얻어 원본을 쪼갠다 — 주석과
    서식이 살아남는다. 지운 문장 안의 주석은 함께 간다. 그 위의 주석은 어느
    쪽 것인지 알 수 없으므로 남긴다. 남아서 지저분한 것이 지워서 잃는 것보다 낫다.
    """
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(
            "cannot remove: the code has a syntax error (line %d). fix it first."
            % (exc.lineno or 0)
        ) from None

    assign, var = _binding_for(tree, set_id)
    if assign is None:
        raise ValueError("no axis set named %r in this definition" % set_id)

    at = _offsets(source)
    line_starts = [0]
    for line in source.splitlines(True):
        line_starts.append(line_starts[-1] + len(line))

    def whole_lines(node):
        return line_starts[node.lineno - 1], line_starts[node.end_lineno]

    # 본문 구간은 **가지치기 전에** 재 둔다. 잘라낸 뒤에는 첫 문장이 없다
    block = next((n for n in tree.body if _is_puzzle_block(n)), None)
    body_span = indent = None
    if block is not None and block.body:
        body_span = (line_starts[block.body[0].lineno - 1],
                     line_starts[block.end_lineno])
        indent = " " * block.body[0].col_offset

    names = _doomed(tree, var)
    drop = []
    _prune(tree.body, names, drop)        # 대입문도 여기서 걸린다
    cuts = [whole_lines(node) + ("",) for node in drop]

    if block is not None:
        # puzzle(...) 인자에서 뺀다. 인자 목록이 곧 슬라이더 목록이다 (§19.9)
        call = block.items[0].context_expr
        args = call.args[1:]
        doomed_args = [a for a in args if isinstance(a, ast.Name) and a.id in names]
        if len(doomed_args) == len(args):
            # 축 집합이 하나도 안 남는다. 축 집합 없는 퍼즐은 없다
            cuts.append(whole_lines(block) + ("",))
        else:
            for i, arg in enumerate(args, start=1):
                if arg in doomed_args:
                    prev = call.args[i - 1]
                    cuts.append((at(prev.end_lineno, prev.end_col_offset),
                                 at(arg.end_lineno, arg.end_col_offset), ""))
            if not block.body and body_span is not None:
                # 자를 것이 하나도 안 남았다. 축 집합은 남았으므로 퍼즐은 산다 —
                # 자르지 않은 퍼즐로 두고 사용자가 이어 쓰게 한다. 여기서 자를
                # 것을 지어내는 쪽이 나쁘다
                cuts.append(body_span + (indent + "pass" + chr(10),))

    out = source
    for start, end, insert in reversed(_coalesce(cuts)):
        out = out[:start] + insert + out[end:]
    return out


# 축 집합을 고치는 연산 (§19.12). 이미 저작 계층에 있는데 아무도 몰랐다
_AXIS_OPS = ("rotate", "remove", "rename", "mirror", "invert", "merge")


def axis_op(source, set_id, op, other=None):
    """축 집합을 만드는 식을 `op(...)` 로 감싼 새 소스를 돌려준다.

        c1 = cube("Cube 1")
        c1 = rotate(cube("Cube 1"), axis=(0, 0, 1), angle=45)

    `merge` / `rotate` / `remove` / `rename` / `mirror` / `invert` 는 진작
    구현돼 있고 이름 공간에도 있었다. 없던 것은 **아무도 모른다**는 사실을
    고칠 길이었다. 메뉴가 부르는 대신 **호출을 써 준다** — 다음부터는 손으로
    쓸 수 있다 (§19.9).

    인자는 자리만 채운다. 실제 축 id 를 넣어 주므로 고칠 곳이 눈에 보인다.
    """
    if op not in _AXIS_OPS:
        raise ValueError("unknown axis operation %r" % op)
    try:
        tree = ast.parse(source)
    except SyntaxError as exc:
        raise ValueError(
            "cannot edit: the code has a syntax error (line %d). fix it first."
            % (exc.lineno or 0)
        ) from None

    assign, _var = _binding_for(tree, set_id)
    if assign is None:
        raise ValueError("no axis set named %r in this definition" % set_id)

    at = _offsets(source)
    value = assign.value
    start = at(value.lineno, value.col_offset)
    end = at(value.end_lineno, value.end_col_offset)
    inner = source[start:end]

    axes = next((s["axes"] for s in _state.get("sets", []) if s["id"] == set_id), [])
    # **소스에 안 쓰인 축**을 기본값으로 고른다. 첫 축을 그대로 쓰면 그것이
    # 마침 참조 중인 축일 때 메뉴를 누르는 순간 정의가 깨진다
    free = [a for a in axes if a not in source]
    first = (free or axes or ["axis id"])[0]
    prefix = first.rsplit("-", 1)[0] if "-" in first else first

    if op == "rotate":
        call = "rotate(%s, axis=(0, 0, 1), angle=45)" % inner
    elif op == "remove":
        call = "remove(%s, %s)" % (inner, json.dumps(first))
    elif op == "rename":
        call = "rename(%s, {%s: %s})" % (
            inner, json.dumps(first), json.dumps(prefix + "-U"))
    elif op == "mirror":
        # 평면을 드러낸다. 인자를 숨기면 어느 평면인지 코드에 안 보이고
        # 고칠 곳도 없다 — 기본값이 있다는 것과 안 보여도 된다는 것은 다르다
        call = "mirror(%s, normal=(0, 0, 1))" % inner
    elif op == "invert":
        # 원점 반전은 인자가 없다. 고를 것이 없다
        call = "invert(%s)" % inner
    else:
        if not other:
            raise ValueError("merge needs a second axis set")
        other_assign, other_var = _binding_for(tree, other)
        if other_assign is None:
            raise ValueError("no axis set named %r in this definition" % other)
        # 파이썬은 위에서 아래로 읽는다. 아직 없는 이름을 쓰면 NameError 다
        if other_assign.lineno > assign.lineno:
            raise ValueError(
                "%r is defined after %r. move it up first, or merge the other way."
                % (other, set_id)
            )
        # 축 id 는 그대로 물려받는다. 두 집합이 다 puzzle() 인자면 같은
        # id 가 두 곳에 생겨 엔진이 거부한다 (§5). 미리 말해 준다
        drawn = set()
        for node in tree.body:
            if _is_puzzle_block(node):
                drawn = {a.id for a in node.items[0].context_expr.args[1:]
                         if isinstance(a, ast.Name)}
        if other_var in drawn:
            raise ValueError(
                "%r is one of the puzzle's own axis sets, so merging would put its "
                "axis ids in two sets at once. remove it from puzzle(...) first."
                % other
            )
        call = "merge(%s, %s, %s)" % (
            json.dumps(set_id), inner, other_var)

    return source[:start] + call + source[end:]
