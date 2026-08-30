"""브라우저에서 도는 파이썬. 설계 문서 §19.

`web/app.js` 안의 BOOT 코드와 `web/index.html` 의 기본 정의는 Pyodide 에서만
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
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _between(text: str, marker: str) -> str:
    """``const NAME = `...`;`` 형태의 템플릿 리터럴을 꺼낸다."""
    start = text.index(marker) + len(marker)
    end = text.index("`;", start)
    return text[start:end]


BOOT = _between(APP, "const BOOT = `")
DEFAULT_SOURCE = _between(PAGE, "const DEFAULT_SOURCE = `")


@pytest.fixture
def browser_globals():
    """BOOT 를 실행한 namespace. 브라우저가 보는 것과 같다."""
    ns: dict = {"__name__": "__browser__"}
    # sys.path.insert 는 Pyodide 파일 시스템용이라 여기선 무해하다
    exec(compile(BOOT, "<app.js BOOT>", "exec"), ns)
    return ns


def test_boot_defines_the_contract(browser_globals):
    for name in ("load", "prepare", "evaluate"):
        assert callable(browser_globals[name]), name


def test_default_definition_runs_and_reports_its_inputs(browser_globals):
    """페이지가 처음 띄우는 정의가 실제로 도는가."""
    info = json.loads(browser_globals["prepare"](DEFAULT_SOURCE))
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
    info = json.loads(browser_globals["prepare"](source))
    assert info["name"] == "두 번째"
    assert info["axisSets"] == ["edges"]


def test_page_scripts_are_loaded_in_dependency_order():
    """render.js 는 app.js 보다 먼저 와야 하고, engine.js 가 제일 앞이다."""
    order = [m.group(1) for m in re.finditer(r'<script src="([^"]+)"', PAGE)]
    assert order == ["engine.js", "render.js", "app.js"]
