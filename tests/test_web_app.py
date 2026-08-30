"""브라우저에서 도는 파이썬. 설계 문서 §19.

`web/worker.js` 안의 BOOT 코드와 `web/index.html` 의 기본 정의는 Pyodide 에서만
실행된다. 그래서 오타 하나가 브라우저를 열기 전까지 안 잡힌다.

여기서는 그 두 문자열을 **파일에서 꺼내** CPython 으로 돌린다. Pyodide 는
CPython 의 WASM 빌드이므로 (§19.1) 파이썬 계층의 계약은 그대로다. 확인 못 하는
것은 Pyodide 부팅과 파일 시스템 쓰기뿐이고, 그건 JS 쪽 일이다.
"""

from __future__ import annotations

import json
import pathlib
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
WORKER = (ROOT / "web" / "worker.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _between(text: str, marker: str) -> str:
    """``const NAME = `...`;`` 형태의 템플릿 리터럴을 꺼낸다."""
    start = text.index(marker) + len(marker)
    end = text.index("`;", start)
    return text[start:end]


BOOT = _between(WORKER, "const BOOT = `")
DEFAULT_SOURCE = _between(PAGE, "const DEFAULT_SOURCE = `")


@pytest.fixture
def browser_globals():
    """BOOT 를 실행한 namespace. worker 가 보는 것과 같다."""
    ns: dict = {"__name__": "__browser__"}
    # sys.path.insert 는 Pyodide 파일 시스템용이라 여기선 무해하다
    exec(compile(BOOT, "<worker.js BOOT>", "exec"), ns)
    return ns


def test_boot_defines_the_contract(browser_globals):
    for name in ("load", "prepare", "evaluate"):
        assert callable(browser_globals[name]), name


def test_default_definition_runs_and_reports_its_inputs(browser_globals):
    """페이지가 처음 띄우는 정의가 실제로 도는가."""
    info = browser_globals["prepare"](DEFAULT_SOURCE)
    assert info["name"] == "OctoCube Master"
    assert info["inputs"] == ["faces"]
    assert info["axisSets"] == ["faces"]
    assert info["ops"] > 0


def test_evaluate_returns_a_scene_the_renderer_can_draw(browser_globals):
    """render.js 가 읽는 필드가 전부 있고 길이가 맞는가.

    좌표는 여기 없다. JSON 을 태우면 평탄화로 아낀 것을 문자열 파싱으로 도로
    쓰므로 `scene_bytes` 로 따로 간다 (§11.1).
    """
    browser_globals["prepare"](DEFAULT_SOURCE)
    out = browser_globals["evaluate"](json.dumps({"faces": 63.25}), 0.03)

    assert set(out) == {
        "starts", "counts", "groups", "kinds", "labels", "axisSets",
        "carriers", "length", "note",
    }
    n = len(out["starts"])
    assert len(out["counts"]) == n == len(out["groups"]) == len(out["kinds"])
    assert all(0 <= g < len(out["axisSets"]) for g in out["groups"])
    assert out["carriers"] > 0 and out["length"] > 0
    assert out["note"] == ""   # 이 각도에서는 잘리지 않는다


def test_coordinates_come_over_as_float64_bytes(browser_globals):
    """바이트열이 좌표와 정확히 같은가.

    JS 는 이 버퍼를 그대로 Float64Array 로 감싼다. 길이나 자릿수가 어긋나면
    호가 통째로 엉뚱한 자리에 그려지는데, 파싱 단계가 없어 오류도 안 난다.
    """
    import array

    browser_globals["prepare"](DEFAULT_SOURCE)
    out = browser_globals["evaluate"](json.dumps({"faces": 63.25}), 0.03)
    raw = browser_globals["scene_bytes"]()

    assert isinstance(raw, bytes)
    assert len(raw) % 8 == 0
    values = array.array("d")
    values.frombytes(raw)
    assert len(values) == 3 * sum(out["counts"])

    # float64 라 왕복해도 값이 그대로다. 자릿수를 줄이지 않는다
    scene = browser_globals["_state"]["scene"]
    assert list(values) == scene.xyz


def test_illegal_turn_is_reported_not_raised(browser_globals):
    """슬라이더를 밀다 불법이 되어도 예외로 죽지 않는다 (§13.2)."""
    browser_globals["prepare"](DEFAULT_SOURCE)
    notes = []
    for theta in (5.0, 20.0, 44.0, 63.25, 80.0, 120.0, 170.0):
        out = browser_globals["evaluate"](json.dumps({"faces": theta}), 0.12)
        notes.append(out["note"])
    assert any(n == "" for n in notes), "전 각도가 잘리면 정의가 잘못된 것이다"


def test_a_definition_without_a_puzzle_block_is_rejected_clearly(browser_globals):
    with pytest.raises(ValueError, match="puzzle 블록이 없다"):
        browser_globals["load"]("x = 1\n")


def test_the_last_puzzle_wins(browser_globals):
    """여러 블록을 쓰면 마지막 것을 본다. 예제를 이어 붙여 실험할 때 쓴다."""
    source = DEFAULT_SOURCE + """
edges = S.rhombic_dodecahedron("edges")
with puzzle("두 번째", edges) as q:
    split(edges)
"""
    info = browser_globals["prepare"](source)
    assert info["name"] == "두 번째"
    assert info["axisSets"] == ["edges"]


def test_page_scripts_are_loaded_in_dependency_order():
    """render.js 는 app.js 보다 먼저 와야 하고, engine.js 가 제일 앞이다."""
    order = [m.group(1) for m in re.finditer(r'<script src="([^"]+)"', PAGE)]
    # engine.js 는 worker 만 읽는다. 메인 스레드가 135KB 를 파싱할 이유가 없다
    assert order == ["vocab.js", "render.js", "editor.js", "share.js", "app.js"]
    assert "engine.js" in WORKER


# ---- 링크 공유 (§19.4) --------------------------------------------------


def _function_body(text: str, header: str) -> str:
    """중괄호를 세어 함수 본문을 잘라낸다."""
    start = text.index(header) + len(header)
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start : i + 1]
    raise AssertionError(f"{header!r} 의 끝을 못 찾았다")


def test_shared_code_is_never_run_automatically():
    """**이 파일에서 제일 중요한 검사다.**

    링크를 여는 것이 곧 임의 코드 실행이 되면 안 된다. 받은 정의는 편집창에
    채워만 넣고 사람이 읽고 누른다. 브라우저 샌드박스는 파일 접근과 다른 출처
    요청은 막지만, 무한 루프로 탭을 멈추는 것이나 fetch 로 데이터를 보내는
    것은 막지 못한다.

    이 성질은 눈으로 확인하기 어렵다 — 링크를 열어 그림이 나오면 오히려
    '잘 된다'로 보인다. 그래서 구조로 못 박는다.
    """
    body = _function_body(PAGE, "async function start()")
    guard = "if (shared === null) {"
    assert guard in body, "받은 정의와 기본 정의를 가르는 분기가 없다"

    head, tail = body.split(guard, 1)
    branch, rest = tail.split("}", 1)

    assert "run()" not in head, "부팅 직후 무조건 실행하고 있다"
    assert "run()" in branch, "기본 정의는 자동 실행해야 한다"
    assert "run()" not in rest, "받은 정의를 자동 실행하고 있다"
    assert "els.src.value = shared" in rest, "받은 정의를 편집창에 넣지 않는다"


def test_shared_code_shows_a_warning():
    """읽어 보라고 말해야 한다. 조용히 채워 넣으면 자기 코드로 착각한다."""
    body = _function_body(PAGE, "async function start()")
    assert "els.shared.style.display" in body
    for word in ("남이 쓴", "브라우저에서", "실행을 누른다"):
        assert word in body, word


def test_link_carries_code_only_in_the_fragment():
    """fragment 는 서버로 전송되지 않는다. 호스팅에 남의 정의가 안 남는다."""
    share = (ROOT / "web" / "share.js").read_text(encoding="utf-8")
    assert 'KEY = "code="' in share
    body = _function_body(share, "async function shareLink(text, baseUrl)")
    assert 'split("#")[0]' in body, "기존 fragment 를 떼지 않으면 겹쳐 쌓인다"
    assert '"#" + KEY' in body, "질의 문자열이 아니라 fragment 여야 한다"


def test_page_loads_share_before_app():
    order = [m.group(1) for m in re.finditer(r'<script src="([^"]+)"', PAGE)]
    assert order.index("share.js") < order.index("app.js")


# ---- worker 격리 (§19.5) ------------------------------------------------


def test_definitions_run_only_in_the_worker():
    """**받은 코드가 DOM 에 닿지 않는다는 근거다.**

    worker 에는 document 가 없으므로, 정의가 페이지를 바꿔치기하거나 다른 곳으로
    보낼 수 없다. 그 성질은 Pyodide 가 worker 안에서만 돌 때만 성립한다.
    메인 스레드에 파이썬 실행 경로가 하나라도 생기면 근거가 무너진다.
    """
    for name, text in (("app.js", APP), ("index.html", PAGE)):
        for forbidden in ("loadPyodide", "runPython", "pyodide.mjs", "ENGINE_SOURCES"):
            assert forbidden not in text, f"{name} 에 {forbidden!r} 이 있다"

    assert "loadPyodide" in WORKER
    assert "runPython" in WORKER


def test_worker_is_spawned_as_a_module_worker():
    """worker.js 가 engine.js 를 import 하므로 classic worker 로는 안 된다."""
    assert 'new Worker("worker.js", { type: "module" })' in APP


def test_engine_can_be_killed():
    """무한 루프는 terminate 말고 끊을 방법이 없다.

    메인 스레드에서 돌면 자기 루프를 자기가 끊을 수 없어 탭을 닫아야 한다.
    """
    assert "terminate()" in APP
    body = _function_body(APP, "stop()")
    assert "this.worker.terminate()" in body
    assert "this.worker = null" in body
    assert "slot.reject" in body, "대기 중인 요청을 그냥 두면 영원히 안 끝난다"

    assert 'id="stop"' in PAGE
    assert "engine.stop()" in PAGE
    assert "await engine.boot()" in PAGE, "죽인 뒤 다시 올리지 않으면 못 쓴다"


def test_coordinates_are_transferred_not_copied():
    """좌표 버퍼는 transferable 이다. worker 로 옮기면서 복사가 오히려 줄었다."""
    assert "buffer ? [buffer] : []" in WORKER
    assert "new Float64Array(msg.buffer)" in APP
    # WASM 메모리를 가리키는 view 를 그대로 넘기면 안 된다
    assert "view.slice().buffer" in WORKER


# ---- 편집창 (§19.6) -----------------------------------------------------


def test_tab_is_captured_for_indentation():
    """textarea 는 Tab 이 포커스 이동이다. 파이썬은 들여쓰기가 문법이라
    가로채지 않으면 정의를 쓸 수 없다."""
    assert 'Editor.attach(document.getElementById("src"))' in PAGE
    editor = (ROOT / "web" / "editor.js").read_text(encoding="utf-8")
    assert 'if (ev.key === "Tab"' in editor or '"Tab"' in editor
    assert "preventDefault()" in editor


def test_there_is_a_way_out_of_the_editor_by_keyboard():
    """Tab 을 가로채면 키보드로 빠져나갈 길이 막힌다. Esc 다음 Tab 이 탈출구다."""
    editor = (ROOT / "web" / "editor.js").read_text(encoding="utf-8")
    assert '"Escape"' in editor
    assert "escaped" in editor
    # 페이지가 그 규약을 알려야 한다. 모르면 갇힌 것과 같다
    assert "Esc" in PAGE and "포커스" in PAGE


def test_edits_are_minimal_so_undo_still_works():
    """전체 텍스트를 갈아치우면 되돌리기가 뭉텅이가 된다."""
    editor = (ROOT / "web" / "editor.js").read_text(encoding="utf-8")
    assert "setRangeText(edit.insert, edit.from, edit.to" in editor
    assert "textarea.value =" not in editor, "전체 대입은 되돌리기 기록을 지운다"


# ---- 암묵 import (§19.7) ------------------------------------------------


def test_authoring_names_are_preloaded(browser_globals):
    """정의마다 같은 import 두 줄을 쓰게 하면 정보가 0인 줄이 반복된다.

    GlowScript 가 vpython 에 하는 것과 같다.
    """
    import cutpattern.dsl as dsl
    from cutpattern import solids

    ns = browser_globals["_namespace"]()
    for name in list(dsl.__all__) + list(solids.__all__):
        assert name in ns, name
    assert ns["S"] is solids
    assert "math" in ns


def test_dsl_and_solids_do_not_share_names(browser_globals):
    """겹치면 어느 쪽이 이겼는지가 안 보인다. 겹치는 순간 알아야 한다."""
    import cutpattern.dsl as dsl
    from cutpattern import solids

    assert not (set(dsl.__all__) & set(solids.__all__))
    # 겹치게 만들면 거부하는가
    original = solids.__all__
    try:
        solids.__all__ = tuple(original) + ("puzzle",)
        with pytest.raises(RuntimeError, match="겹친다"):
            browser_globals["_namespace"]()
    finally:
        solids.__all__ = original


def test_default_definition_needs_no_imports(browser_globals):
    """기본 정의가 그 편의를 보여 준다."""
    assert "import" not in DEFAULT_SOURCE
    info = browser_globals["prepare"](DEFAULT_SOURCE)
    assert info["name"] == "OctoCube Master"


def test_explicit_imports_still_work(browser_globals):
    """예전에 만든 공유 링크와 예제가 살아 있어야 한다."""
    source = """from cutpattern import solids as S
from cutpattern.dsl import puzzle, split

faces = S.cube("faces")
with puzzle("명시적 import", faces) as p:
    split(faces)
"""
    info = browser_globals["prepare"](source)
    assert info["name"] == "명시적 import"


def test_the_preloaded_names_are_listed_for_the_reader():
    """이름이 마법처럼 존재하면 무엇을 쓸 수 있는지 알 길이 없다.

    목록은 **정적 데이터**다. worker 를 거쳐 가져오면 비동기, 메시지 왕복,
    Pyodide 의 타입 변환이 끼어드는데 그중 하나만 어긋나도 목록이 조용히 빈다.
    실제로 그렇게 비었다. 번들을 만들 때 같은 `__all__` 에서 뽑아 둔다.
    """
    import bundle_engine
    import cutpattern.dsl as dsl
    from cutpattern import solids

    groups = bundle_engine.vocabulary()
    listed = {n for items in groups.values() for n in items}
    for name in list(dsl.__all__) + list(solids.__all__):
        assert name in listed, name

    assert 'id="vocab"' in PAGE
    assert "globalThis.VOCAB" in PAGE
    assert "engine.names" not in PAGE, "worker 왕복이 남아 있다"


def test_vocab_file_matches_the_sources():
    """`vocab.js` 도 생성물이라 낡을 수 있다."""
    import json as _json

    import bundle_engine

    text = (ROOT / "web" / "vocab.js").read_text(encoding="utf-8")
    start, end = text.index("{"), text.rindex("}") + 1
    assert _json.loads(text[start:end]) == bundle_engine.vocabulary(), (
        "python web/bundle_engine.py 를 돌린다"
    )


def test_worker_results_are_plain_objects():
    """Pyodide 의 toJs 가 dict 를 Map 으로 주면 Object.entries 가 **조용히**
    빈 배열을 돌려준다. 화면만 비고 오류는 없어서 알아채기 어렵다.

    경계에서 한 번 눌러 평범한 객체로 만든다. prepare / evaluate / names 가
    전부 이 경로를 지난다.
    """
    assert "function toPlain" in WORKER
    assert "value instanceof Map" in WORKER
    assert "return toPlain(out)" in WORKER, "call() 이 눌러서 돌려주지 않는다"


def test_empty_vocabulary_says_so():
    """비면 조용히 넘어가지 말아야 한다. 빈 패널은 원인을 안 알려 준다."""
    assert "vocab.js 가 없다" in PAGE


def test_vocabulary_does_not_wait_for_pyodide():
    """정적 데이터를 Pyodide 뒤에 두면 부팅이 실패할 때 목록도 같이 사라진다."""
    body = _function_body(PAGE, "async function start()")
    assert "showVocabulary" not in body, "부팅 흐름과 묶여 있다"
    assert "showVocabulary();   // Pyodide 와 무관하다" in PAGE
