"""브라우저에서 도는 파이썬. 설계 문서 §19.

`web/boot.py` 와 `web/index.html` 의 기본 정의는 Pyodide 에서만 실행된다.
그래서 오타 하나가 브라우저를 열기 전까지 안 잡힌다.

`boot.py` 는 **파일**이다. 전에는 worker.js 의 백틱 템플릿 리터럴 안에 있었는데,
파이썬 docstring 이 백틱을 쓰는 순간 리터럴이 거기서 끊겨 worker.js 전체가
문법 오류가 됐다. 브라우저는 빈 메시지의 로드 실패만 알려 주므로 원인을 찾기
어렵다.

여기서는 그 두 문자열을 **파일에서 꺼내** CPython 으로 돌린다. Pyodide 는
CPython 의 WASM 빌드이므로 (§19.1) 파이썬 계층의 계약은 그대로다. 확인 못 하는
것은 Pyodide 부팅과 파일 시스템 쓰기뿐이고, 그건 JS 쪽 일이다.
"""

from __future__ import annotations

import json
import pathlib
import sys
import re

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "web"))   # bundle_engine 을 그대로 부른다
WORKER = (ROOT / "web" / "worker.js").read_text(encoding="utf-8")
APP = (ROOT / "web" / "app.js").read_text(encoding="utf-8")
PAGE = (ROOT / "web" / "index.html").read_text(encoding="utf-8")


def _between(text: str, marker: str) -> str:
    """``const NAME = `...`;`` 형태의 템플릿 리터럴을 꺼낸다."""
    start = text.index(marker) + len(marker)
    end = text.index("`;", start)
    return text[start:end]


BOOT = (ROOT / "web" / "boot.py").read_text(encoding="utf-8")
DEFAULT_SOURCE = _between(PAGE, "const DEFAULT_SOURCE = `")


@pytest.fixture
def browser_globals():
    """BOOT 를 실행한 namespace. worker 가 보는 것과 같다."""
    ns: dict = {"__name__": "__browser__"}
    # sys.path.insert 는 Pyodide 파일 시스템용이라 여기선 무해하다
    exec(compile(BOOT, "<web/boot.py>", "exec"), ns)
    return ns


def test_boot_defines_the_contract(browser_globals):
    for name in ("load", "prepare", "evaluate"):
        assert callable(browser_globals[name]), name


def test_default_definition_runs_and_reports_its_inputs(browser_globals):
    """페이지가 처음 띄우는 정의가 실제로 도는가."""
    info = browser_globals["prepare"](DEFAULT_SOURCE)
    assert info["name"] == "OctoCube Master"
    assert info["inputs"] == ["cube1"]
    assert info["axisSets"] == ["cube1"]
    assert info["ops"] > 0


def test_evaluate_returns_a_scene_the_renderer_can_draw(browser_globals):
    """render.js 가 읽는 필드가 전부 있고 길이가 맞는가.

    좌표는 여기 없다. JSON 을 태우면 평탄화로 아낀 것을 문자열 파싱으로 도로
    쓰므로 `scene_bytes` 로 따로 간다 (§11.1).
    """
    browser_globals["prepare"](DEFAULT_SOURCE)
    out = browser_globals["evaluate"](json.dumps({"cube1": 63.25}), 0.03)

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
    out = browser_globals["evaluate"](json.dumps({"cube1": 63.25}), 0.03)
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
        out = browser_globals["evaluate"](json.dumps({"cube1": theta}), 0.12)
        notes.append(out["note"])
    assert any(n == "" for n in notes), "전 각도가 잘리면 정의가 잘못된 것이다"


def test_a_definition_without_a_puzzle_block_is_rejected_clearly(browser_globals):
    with pytest.raises(ValueError, match="no puzzle block"):
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
    order = [name.split("?")[0] for name in order]
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
    assert "els.src.value = shared" in body, "받은 정의를 편집창에 넣지 않는다"

    # 실행은 단 한 곳, 기본 정의일 때만이다
    runs = [line.strip() for line in body.splitlines() if "run()" in line]
    assert runs == ["if (shared === null) run();"], runs


def test_shared_code_shows_a_warning():
    """읽어 보라고 말해야 한다. 조용히 채워 넣으면 자기 코드로 착각한다."""
    body = _function_body(PAGE, "async function start()")
    assert "els.shared.style.display" in body
    for word in ("someone", "browser", "press Run"):
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
    order = [name.split("?")[0] for name in order]
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
    assert "boot.py" in WORKER, "정의 실행 층을 파일로 받아야 한다"


def test_worker_is_spawned_as_a_module_worker():
    """worker.js 가 engine.js 를 import 하므로 classic worker 로는 안 된다."""
    assert re.search(r'new Worker\(this\.blobUrl, \{ type: "module" \}\)', APP)


def test_worker_is_spawned_from_a_blob_so_it_inherits_the_policy():
    """**worker 는 문서의 CSP 를 물려받지 않는다** (§19.14).

    worker 전역의 정책은 worker 스크립트의 응답 헤더에서 오는데, GitHub Pages
    는 헤더를 줄 수 없다. 그래서 meta 로 박은 CSP 는 `fetch` 가 실제로 도는
    worker 안에 안 닿는다. 스크립트의 출처가 `blob:` 같은 로컬 스킴일 때만
    만든 쪽의 정책을 물려받는다.

    **본문을 blob 에 넣으면 안 된다.** blob URL 에는 디렉터리가 없어서
    worker.js 안의 상대 경로가 다 깨진다. import 한 줄만 넣으면 worker.js 는
    제 https 주소에서 받아지고 상대 지정자는 그 base URL 로 풀린다.
    """
    body = _function_body(APP, "function workerBlobUrl()")
    assert "createObjectURL" in body
    assert '"import "' in body, "blob 에는 import 한 줄만 넣는다"
    # 표식이 붙은 진짜 파일을 가리켜야 한다. 캐시 손잡이가 여기서 끊기면
    # 옛 worker 가 새 engine 을 부르는 어긋남이 돌아온다 (§19.11)
    assert re.search(r'new URL\("worker\.js\?v=[0-9a-f]+", location\.href\)', APP)
    assert "ENGINE_SOURCES" not in APP, "본문을 옮겨 담으면 상대 경로가 깨진다"


def test_boot_has_a_watchdog():
    """부팅이 조용히 멎는 것을 눈에 보이게 한다.

    CSP 차단이나 worker 로드 실패는 화면에 아무것도 남기지 않는다. 워치독이
    없으면 "Starting…" 하나로 기다림과 고장이 같아 보인다.

    **죽이지 않는다.** 런타임을 자체 호스팅하므로 (§19.13) 느린 연결에서는
    이 시간이 정상적으로 넘어간다. terminate 는 _die 에만 있어야 한다.
    """
    body = _function_body(APP, "async boot()")
    assert "BOOT_SILENCE_MS" in body
    assert "clearTimeout" in body, "부팅이 끝나면 워치독을 거둬야 한다"
    assert "terminate" not in body, "워치독이 오는 중인 부팅을 끊으면 안 된다"


def test_network_paths_are_closed_before_definitions_run():
    """정의가 밖으로 내보낼 통로를 끊는다 (§19.5).

    worker 에 document 가 없다는 것은 페이지 바꿔치기와 리다이렉트만 막는다.
    `fetch` 는 worker 에서도 되고, `mode: "no-cors"` 면 CORS 도 안 걸린다 —
    읽지는 못해도 **보내는 것은 막지 못한다**.

    순서가 성질이다. Pyodide 자신이 wasm 과 stdlib 을 fetch 로 받으므로
    부팅보다 먼저 끊으면 부팅이 안 되고, 정의보다 늦게 끊으면 소용이 없다.

    끊는 것만으로 다 막히지는 않는다. 동적 `import()` 는 함수가 아니라 문법이라
    지울 수 없고, 그건 CSP `script-src` 쪽에서 잡는다 (§19.14).
    """
    body = _function_body(WORKER, "async function boot()")
    assert "revokeNetwork()" in body
    assert body.index("runPython") < body.index("revokeNetwork()"),         "Pyodide 가 다 뜨기 전에 끊으면 부팅이 안 된다"

    # 중첩 worker 는 손대지 않은 전역을 새로 받는다. 남겨 두면 전부 되돌아온다
    for name in ("fetch", "XMLHttpRequest", "WebSocket", "EventSource", "Worker"):
        assert '"%s"' % name in WORKER, name

    # 반쯤 끊긴 채로 도는 것이 제일 나쁘다 — 화면은 멀쩡하고 구멍만 남는다
    assert "throw new Error" in _function_body(WORKER, "function revokeNetwork()")


def test_the_runtime_comes_from_the_same_origin():
    """CDN 에서 받으면 connect-src 에 그 출처를 열어 두어야 한다 (§19.14).

    열어 두면 정의도 그리로 보낼 수 있으므로 잠그는 뜻이 없어진다. 폴백도
    두지 않는다 — 폴백이 있으면 구멍이 그대로 남고, 로컬에만 파일이 없는
    상태를 아무도 못 알아챈다.
    """
    assert "cdn.jsdelivr.net" not in WORKER, "런타임을 CDN 에서 받고 있다"
    assert "loadPyodide(PYODIDE_OPTIONS)" in WORKER

    # indexURL 을 안 넘기면 Pyodide 가 일부러 예외를 던져 스택 트레이스에서
    # 제 파일 이름을 뽑아 쓴다. 위치를 아는데 그 추론에 기댈 이유가 없다
    assert "indexURL" in WORKER


def test_the_runtime_manifest_is_the_only_place_the_version_lives():
    """받는 것과 같은지는 파일이 아니라 해시가 보증한다 (§19.14).

    12MB 를 커밋하면 git 이 보증하지만 판올림마다 히스토리에 쌓인다. 해시는
    300바이트로 같은 것을 보증하고, 오히려 더 강하다 — 커밋은 최초 1회를
    눈감고 받지만 이것은 매번 검증한다.
    """
    text = (ROOT / "web" / "pyodide.sha256").read_text(encoding="utf-8")
    version = ""
    files = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("version "):
            version = line.split(None, 1)[1]
            continue
        digest, name = line.split()
        assert len(digest) == 64, name
        files[name] = digest

    assert version
    assert set(files) == {
        "pyodide.mjs", "pyodide.asm.js", "pyodide.asm.wasm",
        "python_stdlib.zip", "pyodide-lock.json",
    }, sorted(files)

    # 버전이 두 곳에 적히면 어긋난다. worker.js 는 경로만 안다
    assert version not in WORKER, f"worker.js 에 버전 {version} 이 박혀 있다"


def test_the_page_carries_a_policy():
    """CSP 는 능력 제거가 못 막는 것을 막는다 (§19.14).

    동적 `import()` 는 함수가 아니라 문법이라 전역에서 지울 수 없고,
    `connect-src` 가 아니라 `script-src` 소관이다. 반대로 CSP 만으로는 상속이
    안 먹는 브라우저에서 전부가 걸린다. 서로의 구멍을 메우는 관계다.
    """
    head = PAGE[:PAGE.index("<style>")]
    assert 'http-equiv="Content-Security-Policy"' in head, "meta 는 head 에 있어야 한다"

    start = head.index('http-equiv="Content-Security-Policy"')
    policy = head[head.index('content="', start) + len('content="'):]
    policy = policy[:policy.index('"')]
    rules = {}
    for part in policy.split(";"):
        part = part.split()
        if part:
            rules[part[0]] = part[1:]

    assert rules["default-src"] == ["'none'"]
    # 내보내는 길. 이것 하나가 이 절의 목표다
    assert rules["connect-src"] == ["'self'"]
    # 지울 수 없는 동적 import() 가 여기 걸린다
    assert "'self'" in rules["script-src"]
    assert not any(s.startswith("http") for s in rules["script-src"]),         "출처를 열면 정의가 그리로 보낼 수 있다"
    # blob worker 라야 정책이 정의가 도는 곳까지 간다. 'self' 가 함께 있는 것은
    # blob 이 import 하는 worker.js 때문이다 — Chrome 은 모듈 worker 의 모듈
    # 그래프 전체를 "worker 만들기" 로 봐서 script-src 가 아니라 worker-src 로
    # 잰다. blob: 만 열면 shim 은 뜨는데 본문이 막힌다
    assert set(rules["worker-src"]) == {"blob:", "'self'"}
    assert not any(s.startswith("http") for s in rules["worker-src"])
    # script-src 에 blob: 이 있으면 정의가 제 blob 을 만들어 import 한다
    assert "blob:" not in rules["script-src"]


def test_the_editor_does_not_wrap_long_lines():
    """접으면 한 줄이 두 줄로 보인다 (§19.6).

    파이썬은 들여쓰기 열이 문법이라, 어디가 진짜 줄머리인지 눈으로 세는 것이
    편집창에서 제일 자주 하는 일이다. 접힌 줄은 그걸 못 하게 한다.
    """
    assert 'id="src"' in PAGE
    tag = PAGE[PAGE.index('<textarea id="src"'):]
    assert 'wrap="off"' in tag[:tag.index(">")]


# ---- 실행 모드와 편집 모드 (§19.15) ------------------------------------


def test_the_two_modes_split_the_sidebar():
    """편집 모드에서는 편집밖에 못 한다 (§19.15).

    실행 모드는 축 집합을 켜고 끄고 각도를 미는 자리다. "간단 모드" 가 아니다 —
    간단한 것은 축을 더하는 일이지 실행 모드 자체가 아니다.
    """
    assert 'id="mode"' in PAGE

    def marked(tag_id):
        i = PAGE.index(tag_id)
        line = PAGE[PAGE.rindex("<", 0, i):PAGE.index(">", i) + 1]
        return "editonly" in line

    # 코드에 딸린 것은 편집 모드 것이다
    for tag_id in ('id="src"', 'id="shared"', 'id="vocab"'):
        assert marked(tag_id), tag_id + " 가 편집 모드 것이어야 한다"

    # 오류와 축 집합 목록은 두 모드에 다 있다. 실행 모드에서 슬라이더를 밀다
    # 죽을 수 있고, 갈 곳 없는 오류는 없는 오류보다 나쁘다.
    #
    # 공유도 그렇다. 그것은 **보내는 쪽** 일이고, §19.4 의 성질은 받는 사람이
    # 코드를 읽는 것이지 보내는 사람이 편집창을 거치는 게 아니다
    for tag_id in ('id="err"', 'id="sets"', 'id="share"', 'id="stop"'):
        assert not marked(tag_id), tag_id + " 는 두 모드에 다 있어야 한다"


def test_hiding_actually_hides():
    """UA 의 `[hidden]{display:none}` 은 **작성자 규칙에 진다.**

    `.bar` 가 `display: flex` 라 `hidden` 을 걸어도 그대로 보인다. 모드 전환이
    조용히 안 먹는 자리라, 규칙 하나가 빠지면 두 모드가 겹쳐 나온다.
    """
    css = PAGE[PAGE.index("<style>"):PAGE.index("</style>")]
    assert "[hidden]" in css and "display: none !important" in css


def test_editing_an_axis_set_belongs_to_the_edit_mode():
    """`rotate`/`mirror`/`invert` 는 **결과를 봐야** 뜻이 있다 (§19.15).

    텍스트 메뉴에서는 축이 어디로 갔는지 안 보이므로 편집 모드 것이다.
    지우기는 다르다 — 넣기와 대칭이라 (§19.9) 두 모드에 다 있어야 한다.
    `Add axis set` 이 실행 모드에 있는데 지우기가 없으면 한쪽만 되는 짝이다.
    """
    body = _function_body(PAGE, "function buildAxisSets()")
    assert 'if (mode === "edit") row.append(pick)' in body

    # × 는 조건 없이 붙어야 한다
    tail = body[body.index("const del = document.createElement"):]
    head = tail[:tail.index("row.append(del);")]
    assert "row.append(del);" in tail
    assert "mode" not in head, "× 가 모드에 걸려 있다"


def test_a_menu_edit_can_be_undone_once():
    """`×` 는 축 집합만이 아니라 **그것을 쓰는 문장을 전부** 데려간다 (§19.9).

    편집 모드에서는 편집창의 브라우저 되돌리기가 탈출구인데 (§19.6) 실행
    모드에는 편집창이 없다. 코드를 안 보는 사람이 무엇이 사라졌는지 모른 채
    되돌릴 수도 없게 된다.
    """
    assert 'id="undo"' in PAGE
    # 메뉴가 소스를 고치기 **전에** 직전 것을 기억해야 한다
    for call in ("addAxisSet", "removeAxisSet", "axisOp"):
        i = PAGE.index("rewrite(await engine." + call + "(")
        assert "remember(els.src.value);" in PAGE[i - 120:i], call
    # 손으로 고치면 그 칸은 버린다. 두 되돌리기가 겹치면 어느 쪽이 이겼는지
    # 안 보인다
    i = PAGE.index("els.src.oninput")
    assert "forgetUndo()" in PAGE[i:PAGE.index("};", i)]


def test_a_shared_link_opens_the_editor():
    """**§19.4 의 안전 근거는 "사람이 읽고 누른다" 하나다.**

    링크로 받은 정의를 실행 모드에서 열면 읽어야 할 코드가 접혀 있다. 경고만
    뜨고 정작 읽을 것이 안 보이므로, 자동 실행을 막아 둔 것과 짝이 안 맞는다 —
    모드를 나누기 전보다 나빠진다.

    이 검사가 `test_shared_code_is_never_run_automatically` 옆에 있는 이유는
    둘이 같은 성질의 두 반쪽이기 때문이다. UI 를 만지다 한쪽만 깨지면 남은
    한쪽이 성질을 지키는 것처럼 보인다.
    """
    assert 'let mode = "run"' in PAGE, "기본은 실행 모드다"

    body = _function_body(PAGE, "async function start()")
    # 링크가 있는 가지 안에서 편집 모드로 바꿔야 한다
    branch = body[body.index("els.src.value = shared;"):]
    assert 'setMode("edit")' in branch
    # 그리고 그 가지는 여전히 자동 실행하지 않는다
    assert "run()" not in branch[:branch.index("await engine.boot()")]


def test_the_menu_avoids_colliding_axis_id_prefixes(browser_globals):
    """접두사가 집합 id 에서 **유도된다는 것이 유일하다는 뜻은 아니다** (§2.5).

    `abbrev("cube1")` 도 `abbrev("Cube 1")` 도 `c1` 이다. 그래서 손으로
    `cube1` 이라 쓴 정의 — 화면이 처음 띄우는 바로 그 정의다 — 에 메뉴가
    `Cube 1` 을 얹으면 엔진이 거부한다 (§5):

        axis id 'c1-0' appears in both 'cube1' and 'Cube 1'

    `abbrev` 를 고치는 것은 답이 아니다. 축 id 는 공유 링크와 예제에 박혀
    있어서 바꾸면 다 깨진다. 손으로 지은 이름을 규칙에 맞추라고 할 수도 없다.
    메뉴가 비켜 간다.
    """
    out = browser_globals["add_axis_set"](DEFAULT_SOURCE, "cube")
    # 여기서 ValueError 가 났었다
    info = browser_globals["prepare"](out)
    assert info["axisSets"] == ["cube1", "Cube 2"], info["axisSets"]

    # 번호가 1 을 건너뛴 것은 `cube1` 이 이미 `c1` 을 쓰고 있어서다.
    # 들쭉날쭉해 보여도 그것이 사실이다
    assert 'cube("Cube 2")' in out

    # 한 번 더 얹어도 겹치지 않는다
    again = browser_globals["prepare"](browser_globals["add_axis_set"](out, "cube"))
    assert again["axisSets"] == ["cube1", "Cube 2", "Cube 3"], again["axisSets"]


def test_stop_appears_only_when_an_evaluation_drags_on():
    """늘 두면 화면만 먹고, 없으면 멎었을 때 탈출구가 없다 (§19.15).

    몸통 정의는 밀리초대다 (§12.3). 그러나 손으로 쓴 무거운 정의를 실행
    모드에서 슬라이더로 밀다 멎으면, 거기엔 편집창도 Run 도 없다.

    떠도 강제하는 것은 없다 — 더 기다리고 싶으면 그냥 두면 된다.
    """
    assert "const SLOW_MS = 5000" in PAGE

    # 평소엔 숨어 있어야 한다
    tag = PAGE[PAGE.index('<button id="stop"'):]
    assert "hidden" in tag[:tag.index(">")]

    body = _function_body(PAGE, "function watchSlow(on)")
    assert "SLOW_MS" in body and "els.stop.hidden = false" in body
    # 평가마다 감싸야 한다. 슬라이더도 평가다
    assert "watchSlow(true)" in _function_body(PAGE, "async function refresh(maxStep)")


def test_running_binds_you_to_the_editor():
    """평가 도중에 화면이 바뀌면 무엇이 그려지는 중인지 안 보인다 (§19.15).

    멎었을 때 어느 정의가 멎은 것인지도 흐려진다. 실행 모드로 나가는 것은
    결과를 본 뒤다.
    """
    body = _function_body(PAGE, "async function run()")
    assert "bind(true)" in body
    assert "bind(false)" in body[body.index("finally"):], "끝나면 반드시 풀어야 한다"

    bound = _function_body(PAGE, "function bind(on)")
    assert "els.mode.disabled = on" in bound
    assert "Rendering" in bound


def test_the_edit_mode_stage_shows_markers(browser_globals):
    """편집 모드가 곧 축 집합 패널이다 (§19.15).

    여닫는 창이 아니라 **모드가 무대를 정한다** — 실행 모드는 절단 패턴,
    편집 모드는 축 마커. 둘을 같이 띄우지 않는다.
    """
    source = "\n".join([
        'ref = tetrahedron("Reference 1")',
        'c1 = cube("Cube 1")',
        '',
        'with puzzle("demo", c1) as p:',
        '    split(c1)',
        '',
    ])
    # 퍼즐 블록 없이도 돌아야 한다. 편집 중에는 아직 안 쓴 상태가 있다
    out = browser_globals["axis_scene"](source)

    # `puzzle()` 인자가 아닌 집합도 나온다 (§19.12). 그것을 고치려면 어디
    # 있는지 보여야 하고, build_scene 은 퍼즐에서 얻으므로 닿을 길이 없다
    assert out["axisSets"] == ["Reference 1", "Cube 1"]
    assert len(out["starts"]) == 4 + 6
    assert set(out["kinds"]) == {1}, "절단이 섞여 있다"

    # 목록도 같은 실행에서 나온다. 따로 가져오면 어긋날 수 있다
    assert [s["id"] for s in out["sets"]] == ["Reference 1", "Cube 1"]

    # 좌표는 따로 간다 (§11.1). float64 이므로 점 하나가 24바이트
    assert len(browser_globals["axis_scene_bytes"]()) % 24 == 0


def test_the_marker_stage_does_not_need_a_puzzle_block(browser_globals):
    """편집 중에는 아직 `with puzzle(...)` 을 안 쓴 상태가 있다 (§19.15).

    그때도 축이 어디 있는지는 보여야 한다. `prepare` 는 퍼즐을 요구하므로
    이 길이 따로 있어야 한다.
    """
    out = browser_globals["axis_scene"]('c1 = cube("Cube 1")')
    assert out["axisSets"] == ["Cube 1"]
    assert len(out["starts"]) == 6


def test_the_stage_is_decided_by_the_mode():
    """무대를 그리는 곳이 하나여야 모드와 어긋나지 않는다 (§19.15)."""
    body = _function_body(PAGE, "async function drawStage()")
    assert 'mode === "edit"' in body and "engine.axisScene(els.src.value)" in body
    assert "lastCutScene" in body

    # 평가는 절단 장면을 **들고만** 있는다. 무대에 올릴지는 모드가 정한다
    refresh = _function_body(PAGE, "async function refresh(maxStep)")
    assert "lastCutScene = out.scene" in refresh
    assert "drawStage()" in refresh
    assert "view.setScene" not in refresh, "무대를 두 곳에서 그리면 어긋난다"


def test_the_run_button_leaves_for_the_result():
    """`Run` 은 결과를 보러 나가는 버튼이다 (§19.15).

    메뉴가 부르는 `run()` 은 편집 모드에 남아야 한다 — 축을 하나 고칠 때마다
    화면이 튀면 못 쓴다.
    """
    i = PAGE.index("els.run.onclick")
    handler = PAGE[i:PAGE.index("};", i)]
    assert 'setMode("run")' in handler

    # 메뉴 쪽에는 없어야 한다
    body = _function_body(PAGE, "function buildAxisSets()")
    assert "setMode" not in body


def test_typing_moves_the_markers():
    """편집창을 고치면 마커가 따라 움직인다 (§19.15).

    `Run` 이 재 둔 것을 쓰면 눌러야만 갱신되는데, `rotate`/`mirror` 는 결과를
    봐야 뜻이 있는 연산이라 그래서는 패널이 값을 못 한다.
    """
    i = PAGE.index("els.src.oninput")
    handler = PAGE[i:PAGE.index("};", i)]
    # 글자마다 실행하지 않는다. 멎으면 그린다
    assert "clearTimeout(typeTimer)" in handler and "drawStage()" in handler
    assert "const TYPE_MS = 400" in PAGE


def test_typing_does_not_flash_errors():
    """**타이핑 중에는 늘 깨져 있다** (§19.9).

    실패하면 직전 마커를 그대로 두고 넘어간다. 글자를 칠 때마다 빨간 칸이
    깜빡이면 못 쓴다 — 오류는 `Run` 을 눌렀을 때 뜬다.
    """
    body = _function_body(PAGE, "async function drawStage()")
    catch = body[body.index("catch"):]
    assert "fail(" not in catch, "타이핑 중 오류를 띄우고 있다"


def test_received_code_does_not_run_until_you_press_run():
    """**타이핑에 반응한다는 것은 곧 실행한다는 뜻이다.**

    링크로 받은 코드가 글자 하나 쳤다고 도는 것은 §19.4 의 "사람이 읽고
    누른다" 를 뒤에서 무너뜨린다. 자동 실행을 막아 놓고 옆문을 내는 셈이다.

    첫 `Run` 이 동의다. 우리가 쓴 기본 정의는 처음에 자동 실행되므로 바로
    켜진다.
    """
    assert "let live = false" in PAGE

    body = _function_body(PAGE, "async function drawStage()")
    assert "!live" in body, "동의 전에도 소스를 실행하고 있다"

    # 그 문은 성공한 평가 뒤에만 열린다
    run_body = _function_body(PAGE, "async function run()")
    i = run_body.index("live = true")
    assert run_body.index("await refresh(FINAL_STEP)") < i
    assert i < run_body.index("catch")


def test_the_cut_angle_belongs_to_the_run_mode():
    """편집 모드 무대에는 절단이 없다 (§19.15).

    그러니 거기서 슬라이더를 밀거나 "그릴까" 를 꺼도 **보이는 것이 하나도 안
    바뀐다.** 조용히 바뀌는 상태만 남는다 — 이 프로젝트가 제일 싫어하는
    종류다. 마커는 축 방향만 쓰므로 절단 각도와 무관하다 (§11.4).

    체크박스 자리는 마커 보임이 차지한다. 두 보임은 서로 다른 것이다.
    """
    body = _function_body(PAGE, "function buildAxisSets()")
    assert 'if (mode === "run" && info.inputs.includes(set.id))' in body


def test_one_checkbox_two_stages():
    """체크박스 하나가 **지금 보고 있는 무대**에서 감출지를 정한다 (§19.15).

    실행 모드면 절단, 편집 모드면 마커다. 기억은 무대마다 따로다 — 하나로
    합치면 편집 모드에서 어수선해서 마커를 껐는데 `Run` 했더니 절단까지
    사라져 있는 일이 생기고, 그건 버그로 보인다.

    **인덱스가 아니라 id 로 든다.** 두 무대의 축 집합 목록이 다르고 (절단은
    그려지는 것만, 마커는 전부), 인덱스로 들면 목록을 다시 그릴 때마다 어느
    것이 꺼져 있었는지가 사라진다.
    """
    assert "const hiddenIn = { run: new Set(), edit: new Set() }" in PAGE

    body = _function_body(PAGE, "function buildAxisSets()")
    assert "hiddenIn[mode]" in body
    assert "view.hidden.clear()" not in body, "목록을 다시 그릴 때 풀리면 안 된다"

    # 렌더러는 인덱스로 본다. 옮기는 곳은 무대에 올리는 자리 하나다
    apply = _function_body(PAGE, "function applyHidden(scene)")
    assert "scene.axisSets.forEach" in apply and "hiddenIn[mode]" in apply
    stage = _function_body(PAGE, "async function drawStage()")
    assert stage.count("applyHidden(") == 2, "두 무대 다 적용해야 한다"


def test_every_cut_input_gets_an_angle():
    """평가는 **모든** 절단 입력에 각도를 요구한다 (§13).

        KeyError: no cut angle given for: ['Tetrahedron 1']

    슬라이더를 만들 때 채우면 슬라이더가 없는 자리에서 비어 있게 된다 —
    편집 모드에는 슬라이더가 없으므로 (§19.15) 거기서 축을 얹으면 그대로
    죽는다. 화면이 아니라 정의가 정하는 것이므로 정의를 읽은 자리에서 채운다.
    """
    body = _function_body(PAGE, "async function run()")
    i = body.index("engine.prepare(els.src.value)")
    seed = body[i:body.index("await refresh(FINAL_STEP)")]
    assert "for (const id of info.inputs)" in seed
    assert "DEFAULT_ANGLE" in seed

    # 슬라이더 줄은 이제 기본값을 안 채운다. 두 곳에 있으면 어긋난다
    assert "= 60" not in _function_body(PAGE, "function angleRow(id)")


def test_engine_can_be_killed():
    """무한 루프는 terminate 말고 끊을 방법이 없다.

    메인 스레드에서 돌면 자기 루프를 자기가 끊을 수 없어 탭을 닫아야 한다.
    """
    assert "terminate()" in APP
    body = _function_body(APP, "_die(err)")
    assert "this.worker.terminate()" in body
    assert "this.worker = null" in body
    assert "slot.reject" in body, "대기 중인 요청을 그냥 두면 영원히 안 끝난다"
    assert "_die(new Error" in _function_body(APP, "stop()")

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
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "Esc" in readme


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
        with pytest.raises(RuntimeError, match="collide"):
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

faces = S.cube("cube")
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

    import re

    text = (ROOT / "web" / "vocab.js").read_text(encoding="utf-8")
    got = {
        name: _json.loads(body)
        for name, body in re.findall(r"globalThis\.(\w+) = (.*);", text)
    }
    assert got["VOCAB"] == bundle_engine.vocabulary(), "python web/bundle_engine.py 를 돌린다"
    assert got["MENU"] == bundle_engine.menu(), "python web/bundle_engine.py 를 돌린다"


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
    assert "vocab.js is missing" in PAGE


def test_vocabulary_does_not_wait_for_pyodide():
    """정적 데이터를 Pyodide 뒤에 두면 부팅이 실패할 때 목록도 같이 사라진다."""
    body = _function_body(PAGE, "async function start()")
    assert "showVocabulary" not in body, "부팅 흐름과 묶여 있다"
    assert "showVocabulary();   // Pyodide 와 무관하다" in PAGE


# ---- 흔한 실수의 메시지 (§19.7) ----------------------------------------


def test_top_level_return_is_explained(browser_globals):
    """편집창의 정의는 함수가 아니라 스크립트다.

    examples/ 가 전부 `def build(): ... return p` 모양이라 `return p` 로 끝내기
    쉽다. 파이썬 기본 메시지("'return' outside function")는 우리 규약을 설명해
    주지 않는다.
    """
    source = """axes = dodecahedron("dodecahedron")

with puzzle("test", axes) as p:
    split(axes)

return p
"""
    with pytest.raises(SyntaxError) as got:
        browser_globals["load"](source)
    text = str(got.value)
    assert "return p" in text and "drop" in text
    assert "line 6" in text, text

    # 그 줄만 빼면 통과한다
    info = browser_globals["prepare"](source.replace("\nreturn p\n", "\n"))
    assert info["name"] == "test"
    assert info["inputs"] == ["dodecahedron"]


def test_a_definition_trapped_in_a_function_is_explained(browser_globals):
    """예제 파일을 통째로 붙여 넣으면 아무도 build() 를 부르지 않는다."""
    source = """def build():
    faces = cube("faces")
    with puzzle("갇힘", faces) as p:
        split(faces)
    return p
"""
    with pytest.raises(ValueError, match="inside build"):
        browser_globals["load"](source)


def test_syntax_errors_name_the_line(browser_globals):
    with pytest.raises(SyntaxError, match="line 1"):
        browser_globals["load"]("with puzzle(" + chr(34) + "t" + chr(10))


def test_two_axis_sets_give_two_sliders(browser_globals):
    """축 집합마다 절단 각도 입력이 따로 붙는다 (§2.2)."""
    source = """axes1 = dodecahedron("dodecahedron")
axes2 = icosahedron("icosahedron")

with puzzle("test", axes1, axes2) as p:
    split(axes1)
    split(axes2)
"""
    info = browser_globals["prepare"](source)
    assert info["inputs"] == ["dodecahedron", "icosahedron"]
    assert info["axisSets"] == ["dodecahedron", "icosahedron"]


def test_the_script_contract_is_documented():
    """편집창에서 뺐다. 화면은 좁고, 규약은 한 번 읽으면 되는 것이다.

    오류 메시지가 그 자리에서 가르치므로 (§19.7) 화면에 상주할 이유가 없다.
    """
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert "A definition is a script" in readme
    assert "with puzzle(...)" in readme
    assert "Each axis set gets its own cut-angle slider" in readme
    # 편집창 조작법도 여기 있다
    for key in ("Tab", "Shift+Tab", "Esc", "Ctrl+Enter"):
        assert key in readme, key


def test_the_panel_keeps_only_what_goes_stale_on_paper():
    """이름 목록은 생성물이라 문서에 박으면 낡는다. 패널에 남긴다."""
    assert 'id="vocab"' in PAGE
    assert "globalThis.VOCAB" in PAGE
    assert 'class="note"' not in PAGE, "설명 문단이 남아 있다"


def test_browser_javascript_actually_parses():
    """**이걸 안 봐서 오래 헤맸다.**

    worker.js 안에 파이썬을 백틱 템플릿 리터럴로 박아 뒀는데, 파이썬 docstring
    이 백틱을 쓰는 순간 리터럴이 거기서 끊겨 파일 전체가 문법 오류가 됐다.
    브라우저는 빈 메시지의 로드 실패만 알려 주므로 원인이 안 보인다.

    파이썬 테스트는 전부 통과하고 있었다 — 문자열을 오려내는 방식이라 JS 문법과
    무관했기 때문이다. node 로 실제 파싱을 확인한다.
    """
    import shutil
    import subprocess

    if shutil.which("node") is None:
        pytest.skip("node 가 없다")
    proc = subprocess.run(
        ["node", str(ROOT / "web" / "syntax.test.js")],
        capture_output=True, text=True, encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr


def test_a_dead_worker_fails_fast():
    """죽은 worker 에 보내면 답이 영영 안 온다.

    부팅이 실패했는데 worker 객체가 남아 있으면, 실행을 눌러도 아무 일도 안
    일어나고 오류도 안 뜬다. 무슨 일인지 알 방법이 없다.
    """
    boot = _function_body(APP, "async boot()")
    assert "this._die(e)" in boot, "실패한 부팅이 worker 를 남겨 둔다"

    send = _function_body(APP, "_send(payload, transfer)")
    assert "if (!this.worker)" in send
    assert "this.failure" in send, "왜 죽었는지를 알려야 한다"

    assert "if (!engine.ready)" in PAGE, "실행 버튼이 죽은 엔진을 확인하지 않는다"


def test_a_failed_reboot_is_reported():
    """재부팅이 실패하면 '중지했다' 가 그대로 남아 원인을 가린다."""
    assert "Could not restart the engine" in PAGE


def test_the_editor_is_filled_before_booting():
    """부팅이 실패해도 코드는 보여야 하고, 링크로 받은 정의가 사라지면 안 된다."""
    body = _function_body(PAGE, "async function start()")
    assert body.index("els.src.value") < body.index("await engine.boot()")


# ---- 절단 각도 범위 (§14) ----------------------------------------------


def test_degenerate_angles_do_not_break(browser_globals):
    """0 과 180 은 퇴화원(r = 0)이다. 회피하지 않고 처리한다.

    RADIUS_EPS 판정이 split 과 build_arcs 에서 걸러 내므로 터지지 않고
    "자를 것이 없는 상태" 로 나온다. 그래서 슬라이더를 0~180 으로 연다.
    """
    browser_globals["prepare"](DEFAULT_SOURCE)
    for theta in (0.0, 180.0):
        out = browser_globals["evaluate"](json.dumps({"cube1": theta}), 0.03)
        assert out["carriers"] == 0
        assert out["length"] == pytest.approx(0.0)
        assert out["note"] == "", "불법 회전으로 잘리면 안 된다"

    # 바로 옆은 정상이다
    out = browser_globals["evaluate"](json.dumps({"cube1": 0.05}), 0.03)
    assert out["carriers"] > 0 and out["length"] > 0


def test_sliders_span_the_whole_range():
    assert "range.min = 0; range.max = 180;" in PAGE
    assert "0.01" not in PAGE or "179.99" not in PAGE


def test_an_empty_cut_says_so():
    """carrier 0 인데 폴리라인이 남으면(축 마커) 고장난 것처럼 읽힌다."""
    assert "no cuts" in PAGE
    assert "out.carriers === 0" in PAGE


# ---- 각도 직접 입력 (§19.8) --------------------------------------------


def test_the_angle_can_be_typed_exactly():
    """슬라이더 스텝은 0.05 라 정다면체의 특징적인 각에 닿을 수 없다.

    정육면체 꼭짓점각이 54.7356°, 면과 꼭짓점 사이가 63.4349° 다. 슬라이더로는
    영원히 못 맞춘다.
    """
    import math

    for angle in (54.7356, 63.4349):
        assert round(angle / 0.05) * 0.05 != pytest.approx(angle, abs=1e-4), (
            f"{angle} 가 슬라이더 격자에 걸린다"
        )

    assert 'val.onclick' in PAGE, "숫자를 눌러 고칠 수 없다"
    assert 'box.step = "any"' in PAGE, "입력이 슬라이더 격자에 묶여 있다"


def test_typed_angles_stay_in_range():
    """0~180 밖은 잘라 낸다. 음수 각은 cos 이 같은 값을 주어 조용히 헷갈린다."""
    assert "Math.min(180, Math.max(0, Number(value)))" in PAGE
    assert "Number.isFinite(next)" in PAGE, "빈 칸이나 글자가 들어오면 NaN 이다"


def test_escape_cancels_the_edit():
    """되돌릴 길이 없으면 잘못 누른 것이 그대로 반영된다."""
    body = PAGE[PAGE.index("val.onclick") : PAGE.index("row.append(name, range)")]
    assert '"Escape"' in body and "finish(false)" in body
    assert '"Enter"' in body and "finish(true)" in body
    assert "box.onblur" in body, "딴 데를 눌러도 값이 살아야 한다"


def test_the_displayed_angle_shows_enough_digits():
    """두 자리로 보여 주면 정확히 넣은 값이 반올림되어 보인다."""
    assert "toFixed(4)" in PAGE


# ---- 축 집합 추가 메뉴 (§19.9) -----------------------------------------


DEF3 = """faces = cube("cube", turns=(45, -45))

with puzzle("OctoCube", faces) as p:
    split(faces)
    for x in faces:
        with turned(x, 45):
            split(*at_angle(x, 90, faces))
"""


def test_insertion_goes_to_all_three_places(browser_globals):
    """맨 뒤에 붙일 수 없다. 넣을 자리가 셋이다.

    (1) with 블록 앞  (2) puzzle() 인자 = 슬라이더 목록  (3) 블록 직속 본문 끝
    """
    out = browser_globals["add_axis_set"](DEF3, "rhombic_dodecahedron")
    lines = out.splitlines()

    var = "rd1"
    assign = next(i for i, l in enumerate(lines) if l.startswith(var + " ="))
    with_at = next(i for i, l in enumerate(lines) if l.startswith("with puzzle("))
    assert assign < with_at, "(1) with 블록 앞에 있어야 한다"
    assert ", " + var + ")" in lines[with_at], "(2) 인자 목록에 없다. 슬라이더가 안 생긴다"
    assert lines[-1] == "    split(" + var + ")", "(3) 블록 직속 본문 끝이 아니다"

    info = browser_globals["prepare"](out)
    assert info["inputs"] == ["cube", "Rhombic Dodecahedron 1"]


def test_split_does_not_land_inside_a_turned_block(browser_globals):
    """중첩 블록 안에 들어가면 회전된 상태에서 자르게 되어 다른 퍼즐이 된다."""
    out = browser_globals["add_axis_set"](DEF3, "icosahedron")
    for line in out.splitlines():
        if "split(i1)" in line:
            assert line == "    split(i1)", "들여쓰기가 깊다 = 중첩 블록 안이다"


def test_generated_names_carry_the_instance_number(browser_globals):
    """번호를 항상 붙인다. 첫 번째만 `cube` 이고 두 번째부터 `cube2` 이면
    하나를 지웠을 때 이름이 들쭉날쭉해진다.

    축 id 도 같은 번호를 쓰므로 집합과 축의 대응이 눈으로 보인다.
    """
    out = browser_globals["add_axis_set"]("", "cube")
    assert out.startswith('c1 = cube("Cube 1")'), out

    out = browser_globals["add_axis_set"](out, "icosahedron")
    assert 'i1 = icosahedron("Icosahedron 1")' in out


def test_axis_ids_are_qualified_by_their_set(browser_globals):
    """축 id 를 집합으로 한정한다. 같은 입체를 두 번 넣어도 안 겹친다.

    축 id 는 전 집합에서 유일해야 하는데 (§5) 접두사가 입체마다 고정이면
    `c0` 이 두 집합에 생긴다. 도형 이름과 축 번호가 눈으로 갈라지는 것은 덤이다.
    """
    out = browser_globals["add_axis_set"]("", "cube")
    out = browser_globals["add_axis_set"](out, "cube")
    info = browser_globals["prepare"](out)
    assert info["axisSets"] == ["Cube 1", "Cube 2"]

    puzzle_obj = browser_globals["_state"]["puzzle"]
    first, second = puzzle_obj.axis_sets
    assert [a.id for a in first][:2] == ["c1-0", "c1-1"]
    assert [a.id for a in second][:2] == ["c2-0", "c2-1"]


def test_presets_keep_their_short_ids():
    """구분자를 접두사 문자열에 담으므로 프리셋 기본값은 안 바뀐다."""
    from cutpattern import solids

    assert [a.id for a in solids.cube()][:2] == ["c-0", "c-1"]
    assert [a.id for a in solids.rhombic_dodecahedron()][:2] == ["rd-0", "rd-1"]


def test_names_are_found_by_parsing_not_by_searching(browser_globals):
    """주석 안의 단어를 세면 멀쩡한 이름을 피해 간다."""
    source = '# cube1 은 여기서 이름이 아니라 주석이다\n'
    out = browser_globals["add_axis_set"](source, "cube")
    assert 'c1 = cube(' in out, out


def test_an_empty_editor_gets_a_whole_skeleton(browser_globals):
    out = browser_globals["add_axis_set"]("", "icosahedron")
    info = browser_globals["prepare"](out)
    assert info["axisSets"] == ["Icosahedron 1"]
    assert info["ops"] > 0


def test_code_without_a_puzzle_block_gets_one(browser_globals):
    out = browser_globals["add_axis_set"]("x = 1\n", "cube")
    assert "x = 1" in out, "쓰던 코드를 지우면 안 된다"
    assert browser_globals["prepare"](out)["axisSets"] == ["Cube 1"]


def test_broken_code_is_refused_not_mangled(browser_globals):
    """타이핑 중에는 늘 문법이 깨져 있다. 억지로 끼우면 남의 코드를 망친다."""
    with pytest.raises(ValueError, match="syntax error"):
        browser_globals["add_axis_set"]("with puzzle(\n", "cube")


def test_comments_and_formatting_survive(browser_globals):
    """ast.unparse 로 재생성하면 주석과 서식이 다 날아간다."""
    source = """# 이 주석은 살아야 한다
faces = cube("faces")


with puzzle("t", faces) as p:      # 여기 주석도
    split(faces)
"""
    out = browser_globals["add_axis_set"](source, "octahedron")
    assert "# 이 주석은 살아야 한다" in out
    assert "# 여기 주석도" in out


def test_the_menu_lists_only_zero_argument_presets():
    """각기둥 계열은 n 이 필요해서 뺐다. 목록은 카탈로그에서 뽑는다 (§2.5)."""
    import bundle_engine
    from cutpattern import solids

    menu = bundle_engine.menu()
    assert {k for k, _ in menu["Platonic"]} == set(solids.PLATONIC)
    assert {k for k, _ in menu["Catalan"]} == set(solids.CATALAN)
    assert "prism" not in {k for items in menu.values() for k, _ in items}


def test_the_menu_writes_code():
    """숨은 상태를 들면 메뉴로 시작해 손으로 이어 쓰는 길이 막힌다."""
    assert "engine.addAxisSet(els.src.value" in PAGE
    assert "rewrite(await engine.addAxisSet" in PAGE, "고른 결과가 편집창 글자로 나와야 한다"
    assert 'id="addPick"' in PAGE and "globalThis.MENU" in PAGE


# ---- 언어 (§19.10) ------------------------------------------------------


def test_nothing_the_user_sees_is_in_korean():
    """타겟이 한국어권이 아니다. 주석과 설계 문서는 한국어로 둔다 (§19.10).

    엔진 예외 메시지까지 포함한다. 정의를 쓰다 틀리면 그것이 화면에 뜨므로,
    거기까지 안 옮기면 반만 영어가 되어 둘 다보다 나쁘다.
    """
    import re

    korean = re.compile(r"[가-힣]")

    QUOTES = (chr(34), chr(39), "`")

    def code_only(line):
        """줄 끝 주석을 떼어 낸다. 따옴표 안의 // 는 건드리지 않는다."""
        quote = None
        for i, ch in enumerate(line):
            if quote:
                if ch == quote and line[i - 1] != "\\":
                    quote = None
            elif ch in QUOTES:
                quote = ch
            elif ch == "/" and line[i : i + 2] == "//":
                return line[:i]
        return line

    def strip_html_comments(text):
        """<!-- --> 를 지운다. 줄 수는 그대로 둬야 줄 번호가 안 어긋난다."""
        out = []
        rest = text
        while True:
            i = rest.find("<!--")
            if i == -1:
                out.append(rest)
                break
            j = rest.find("-->", i)
            if j == -1:
                out.append(rest[:i])
                break
            out.append(rest[:i])
            # 지운 자리의 줄바꿈만 남긴다
            out.append(chr(10) * rest.count(chr(10), i, j))
            rest = rest[j + 3:]
        return "".join(out)

    def visible(path):
        """줄 끝 주석과 /* */, <!-- --> 주석을 뺀 나머지에서 한글을 찾는다."""
        out = []
        text = strip_html_comments(path.read_text(encoding="utf-8"))
        inside = False
        for i, line in enumerate(text.splitlines(), 1):
            body = code_only(line)
            if inside:
                if "*/" in body:
                    body = body.split("*/", 1)[1]
                    inside = False
                else:
                    continue
            while "/*" in body:
                head, rest = body.split("/*", 1)
                if "*/" in rest:
                    body = head + rest.split("*/", 1)[1]
                else:
                    body, inside = head, True
                    break
            stripped = body.strip()
            if stripped.startswith(("//", "#", "*")):
                continue
            if not korean.search(stripped):
                continue
            out.append(f"{path.name}:{i}: {stripped[:60]}")
        return out

    offenders = []
    for name in ("index.html", "app.js", "worker.js", "share.js", "editor.js",
                 "render.js", "vocab.js"):
        offenders += visible(ROOT / "web" / name)
    assert not offenders, offenders


def test_engine_error_messages_are_in_english():
    """정의를 쓰다 틀리면 엔진 예외가 그대로 화면에 뜬다."""
    import re

    korean = re.compile(r"[가-힣]")
    offenders = []
    for path in (ROOT / "cutpattern").rglob("*.py"):
        source = path.read_text(encoding="utf-8")
        for match in re.finditer(r"raise \w+\(\s*\n?\s*(f?[\"'][^\n]*)", source):
            if korean.search(match.group(1)):
                offenders.append(f"{path.name}: {match.group(1)[:50]}")
    assert not offenders, offenders


def test_readme_is_in_english():
    """사용자가 제일 먼저 보는 글이다."""
    import re

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    assert not re.search(r"[가-힣]", readme.replace("(Korean)", ""))


# --- 축 집합 지우기 (§19.9) -------------------------------------------------

DEF_TWO = """c1 = cube("Cube 1")

# 이 주석은 남는다
rd1 = rhombic_dodecahedron("Rhombic Dodecahedron 1")

with puzzle("Demo", c1, rd1) as p:
    split(c1)
    split(rd1)
    for x in c1:
        with turned(x, 45):
            split(rd1)
"""


def test_removal_takes_the_references_with_it(browser_globals):
    """참조를 남기면 `NameError` 만 남는다. 같이 걷어낸다.

    사용자가 정한 바다 — 변형을 여럿 만들어 보다 하나를 통으로 버리는 흐름.
    """
    out = browser_globals["remove_axis_set"](DEF_TWO, "Cube 1")

    assert "c1" not in out, "이름이 어딘가 남았다"
    assert "for x in" not in out, "머리가 지워진 이름을 쓰는 블록은 통째로 가야 한다"
    assert 'rd1 = rhombic_dodecahedron("Rhombic Dodecahedron 1")' in out
    assert "    split(rd1)" in out, "관계없는 문장까지 지웠다"

    info = browser_globals["prepare"](out)
    assert info["axisSets"] == ["Rhombic Dodecahedron 1"]


def test_removal_drops_the_slider_argument(browser_globals):
    """`puzzle()` 인자 목록이 곧 슬라이더 목록이다. 거기서도 빠져야 한다."""
    out = browser_globals["remove_axis_set"](DEF_TWO, "Cube 1")
    assert 'with puzzle("Demo", rd1) as p:' in out


def test_removal_keeps_the_comment_above(browser_globals):
    """지운 문장 위의 주석은 어느 쪽 것인지 알 수 없다. 남긴다."""
    assert "# 이 주석은 남는다" in browser_globals["remove_axis_set"](DEF_TWO, "Cube 1")


def test_removing_the_last_axis_set_removes_the_puzzle(browser_globals):
    """축 집합 없는 퍼즐은 없다. 빈 인자의 `puzzle()` 을 남기면 실행이 깨진다."""
    src = 'c1 = cube("Cube 1")\n\nwith puzzle("D", c1) as p:\n    split(c1)\n'
    out = browser_globals["remove_axis_set"](src, "Cube 1")
    assert "puzzle" not in out and "cube" not in out


def test_removal_names_what_it_cannot_find(browser_globals):
    with pytest.raises(ValueError, match="no axis set"):
        browser_globals["remove_axis_set"](DEF_TWO, "Icosahedron 1")


def test_removal_refuses_broken_source(browser_globals):
    """문법이 깨진 코드는 `ast` 로 못 읽는다. 자르지 말고 말한다."""
    with pytest.raises(ValueError, match="syntax error"):
        browser_globals["remove_axis_set"]("with puzzle(\n", "Cube 1")


def test_removal_is_wired_from_the_page_to_the_worker():
    """UI → app.js → worker.js → boot.py 가 이어져 있어야 실제로 지워진다."""
    assert "removeAxisSet" in PAGE, "슬라이더 옆 삭제 버튼이 없다"
    assert "async removeAxisSet(" in APP
    assert "removeAxisSet:" in WORKER and "remove_axis_set" in WORKER


def test_menu_edits_survive_undo():
    """잘못 지웠을 때 되돌릴 길이 있어야 한다.

    `.value =` 로 통째 대입하면 되돌리기 기록이 날아간다. 편집창이 쓰는 것과
    같은 `setRangeText` 를 써야 한다 (§19.6).
    """
    assert "setRangeText(text, 0, els.src.value.length" in PAGE
    for call in ("engine.removeAxisSet(", "engine.addAxisSet("):
        assert "rewrite(await " + call in PAGE, call + " 가 되돌리기를 죽인다"


# ---- 캐시 (§19.11) --------------------------------------------------------


def test_every_subresource_carries_a_cache_stamp():
    """문서만 새것이고 스크립트가 옛것인 상태가 실제로 났다.

    `python -m http.server` 는 `Cache-Control` 을 안 붙이므로 브라우저가 임의로
    캐시한다. 문서는 늘 재검증하지만 하위 리소스는 아니다 — 새 UI 가 옛
    `app.js` 를 불러 `engine.removeAxisSet is not a function` 이 났다.
    """
    import bundle_engine

    for asset in bundle_engine.ASSETS:
        for text in (PAGE, APP, WORKER):
            for quote in ('"', "'"):
                for ref in (asset, "./" + asset):
                    assert quote + ref + quote not in text, ref + " 에 표식이 없다"

    assert re.search(r'src="app\.js\?v=[0-9a-f]+"', PAGE)
    # worker 는 blob 으로 띄우지만 (§19.14) 그 blob 이 가리키는 진짜 파일에는
    # 표식이 붙어야 한다. 여기서 끊기면 옛 worker 가 새 engine 을 부른다
    assert re.search(r'new URL\("worker\.js\?v=[0-9a-f]+"', APP)


def test_the_stamp_is_one_value_everywhere():
    """파일마다 제 해시를 쓰면 `engine.js` 만 바뀔 때 캐시된 옛 `worker.js` 가
    옛 `engine.js` 를 계속 가리킨다. 하나로 묶으면 그 구멍이 없다."""
    stamps = set(re.findall(r"\?v=([0-9a-f]+)", PAGE + APP + WORKER))
    assert len(stamps) == 1, stamps


def test_the_stamp_is_idempotent():
    """번들을 두 번 돌려도 같아야 한다. 표식이 제 해시에 섞이면 안 멎는다."""
    import bundle_engine

    assert bundle_engine.stamp() == bundle_engine.stamp()


DEF_DERIVED = '''o1 = octahedron("Octahedron 1", turns=(15, 120, 135, -120, -105))
rd1 = rhombic_dodecahedron("Rhombic Dodecahedron 1")
t1 = tetrahedron("Tetrahedron 1")

with puzzle("Octahedron 1", o1, rd1) as p:
    split(o1)
    pair = lambda a: [a, at_angle(a, 180, o1)[0]]
    for i in range(4):
        a, b = tuple(pair(nearest(t1[f"t1-{i}"], o1)))
        with turned(a, 15):
            with turned(b, 15):
                split(at_angle(a, 90, rd1, start=t1[f"t1-{(i + 1) % 4}"])[1::2])
'''


@pytest.mark.parametrize("target", ["Octahedron 1", "Rhombic Dodecahedron 1",
                                    "Tetrahedron 1"])
def test_removal_leaves_runnable_code(browser_globals, target):
    """지우고 나서 도는 코드가 남아야 한다. 이것이 유일한 합격선이다."""
    out = browser_globals["remove_axis_set"](DEF_DERIVED, target)
    browser_globals["prepare"](out)          # 문법도 이름도 성해야 통과한다


def test_removal_follows_derived_names(browser_globals):
    """한 단계만 보면 모자란다.

    `with turned(a, 15)` 는 `o1` 이라는 글자가 없지만 `a` 가 `o1` 에서 나온다.
    이름이 아니라 값의 흐름을 따라가야 한다 — 실제로 이렇게 깨졌다.
    """
    out = browser_globals["remove_axis_set"](DEF_DERIVED, "Octahedron 1")
    assert "turned(a" not in out, "파생된 이름을 쓰는 문장이 남았다"
    assert "pair" not in out


def test_removal_keeps_the_puzzle_alive_when_a_set_remains(browser_globals):
    """자를 것이 다 날아가도 축 집합이 남으면 퍼즐은 산다.

    빈 `with` 는 문법 오류다. 여기서 자를 것을 지어내는 쪽이 더 나쁘므로
    `pass` 를 넣고 사용자가 이어 쓰게 둔다.
    """
    out = browser_globals["remove_axis_set"](DEF_DERIVED, "Octahedron 1")
    assert 'with puzzle("Octahedron 1", rd1) as p:' in out
    assert out.rstrip().endswith("pass")
    assert browser_globals["prepare"](out)["axisSets"] == ["Rhombic Dodecahedron 1"]


def test_removal_does_not_wipe_the_inserted_pass(browser_globals):
    """블록과 그 자식이 둘 다 지울 목록에 오른다. 겹친 채로 뒤에서부터 자르면
    끼워 넣은 글자가 조용히 사라진다. 구간을 합쳐야 한다."""
    assert "pass" in browser_globals["remove_axis_set"](DEF_DERIVED, "Octahedron 1")


# ---- 축 집합 편집 (§19.12) ------------------------------------------------

DEF_SETS = '''c1 = cube("Cube 1")
t1 = tetrahedron("Tetrahedron 1")
rd1 = rhombic_dodecahedron("Rhombic Dodecahedron 1")

with puzzle("Demo", c1, rd1) as p:
    split(c1)
    split(at_angle(c1["c1-0"], 90, rd1, start=t1["t1-0"]))
'''


@pytest.fixture
def ready(browser_globals):
    """편집 메뉴는 실행 뒤에만 뜬다. 실제 축 id 를 그때 알기 때문이다."""
    browser_globals["prepare"](DEF_SETS)
    return browser_globals


def test_prepare_reports_sets_that_are_not_drawn(ready):
    """`puzzle()` 인자만이 축 집합의 전부가 아니다.

    `t1` 은 기준으로만 쓰여 그려지지 않는다. 그래도 고치고 지울 수 있어야 한다.
    """
    info = ready["prepare"](DEF_SETS)
    assert info["axisSets"] == ["Cube 1", "Rhombic Dodecahedron 1"]
    assert [s["id"] for s in info["sets"]] == [
        "Cube 1", "Tetrahedron 1", "Rhombic Dodecahedron 1"]
    assert info["sets"][0]["axes"][:2] == ["c1-0", "c1-1"]


@pytest.mark.parametrize("op", ["rotate", "remove", "rename", "mirror", "invert"])
def test_axis_op_writes_a_call_that_runs(ready, op):
    """메뉴가 **호출을 써 준다.** 쓴 것이 그대로 돌아야 한다."""
    out = ready["axis_op"](DEF_SETS, "Cube 1", op)
    assert out.startswith("c1 = " + op + "(cube(\"Cube 1\")")
    ready["prepare"](out)


def test_axis_op_defaults_to_an_axis_nobody_uses(ready):
    """첫 축을 그대로 쓰면 그것이 마침 참조 중인 축일 때 메뉴를 누르는 순간
    정의가 깨진다. `c1-0` 은 `at_angle` 이 쓰고 있다."""
    for op in ("remove", "rename"):
        written = ready["axis_op"](DEF_SETS, "Cube 1", op).splitlines()[0]
        assert '"c1-0"' not in written, written


def test_axis_op_keeps_the_id_prefix_when_renaming(ready):
    """축 id 접두사는 집합에서 나온다 (§2.5). 제안하는 이름도 그 규칙을 따른다."""
    assert '"c1-U"' in ready["axis_op"](DEF_SETS, "Cube 1", "rename")


def test_merge_folds_in_a_set_that_is_not_drawn(ready):
    out = ready["axis_op"](DEF_SETS, "Rhombic Dodecahedron 1", "merge", "Tetrahedron 1")
    assert 'merge("Rhombic Dodecahedron 1", rhombic_dodecahedron(' in out
    assert out.rstrip().splitlines()[2].endswith(", t1)")
    ready["prepare"](out)


def test_merge_refuses_two_drawn_sets(ready):
    """축 id 를 그대로 물려받으므로 같은 id 가 두 집합에 생긴다 (§5)."""
    with pytest.raises(ValueError, match="two sets at once"):
        ready["axis_op"](DEF_SETS, "Rhombic Dodecahedron 1", "merge", "Cube 1")


def test_merge_refuses_a_set_defined_later(ready):
    """파이썬은 위에서 아래로 읽는다. 아직 없는 이름을 쓰면 NameError 다."""
    with pytest.raises(ValueError, match="defined after"):
        ready["axis_op"](DEF_SETS, "Cube 1", "merge", "Tetrahedron 1")


def test_axis_op_refuses_what_it_does_not_know(ready):
    with pytest.raises(ValueError, match="unknown axis operation"):
        ready["axis_op"](DEF_SETS, "Cube 1", "explode")
    with pytest.raises(ValueError, match="no axis set"):
        ready["axis_op"](DEF_SETS, "Icosahedron 1", "rotate")
    with pytest.raises(ValueError, match="syntax error"):
        ready["axis_op"]("with puzzle(\n", "Cube 1", "rotate")


def test_the_names_were_already_in_scope():
    """C 가 고치는 것은 기능이 아니라 **아무도 모른다**는 사실이다."""
    import cutpattern.axisops as axisops
    import cutpattern.dsl as dsl

    for name in ("merge", "rotate", "remove", "rename", "mirror", "invert"):
        assert name in axisops.__all__ and name in dsl.__all__


def test_axis_editing_is_wired_from_the_page_to_the_worker():
    assert "engine.axisOp(els.src.value" in PAGE and "AXIS_OPS" in PAGE
    assert "async axisOp(" in APP
    assert "axisOp:" in WORKER and "axis_op" in WORKER


def test_one_row_per_axis_set():
    """목록 둘을 하나로 합친다 (§19.15).

    나뉘어 있던 이유는 **각도가 없는 축 집합이 있어서**였다 (기준으로만 쓰는
    것, §19.12). 그건 슬라이더 칸을 비우면 될 일이지 목록을 둘로 만들 이유가
    아니었다 — 실제로 나뉜 이유는 `×` 를 어디 둘지였고 그건 정해졌다.
    """
    assert 'id="sliders"' not in PAGE, "Cut angle 목록은 없어졌다"

    body = _function_body(PAGE, "function buildAxisSets()")
    # 각도가 있는 집합에만 슬라이더가 붙는다. 나머지는 줄만 남는다
    assert "info.inputs.includes(set.id)" in body

    # 슬라이더 줄은 각도만 다룬다
    angle = _function_body(PAGE, "function angleRow(id)")
    assert "removeAxisSet" not in angle and "axisOp" not in angle


def test_mirror_shows_the_plane(ready):
    """`mirror` 는 평면의 법선을 받는다. 기본값이 있다는 것과 안 보여도 된다는
    것은 다르다 — 안 쓰면 어느 평면인지 코드에 없고 고칠 곳도 없다."""
    assert ready["axis_op"](DEF_SETS, "Cube 1", "mirror").startswith(
        'c1 = mirror(cube("Cube 1"), normal=(0, 0, 1))')


def test_invert_takes_nothing(ready):
    """원점 반전은 고를 것이 없다. 없는 인자를 지어내지 않는다."""
    assert ready["axis_op"](DEF_SETS, "Cube 1", "invert").startswith(
        'c1 = invert(cube("Cube 1"))')


def test_edits_stack(ready):
    """메뉴는 겹겹이 쌓는 것을 전제한다. 두 번째부터 못 찾으면 안 된다.

    id 를 든 호출이 감싸이기 때문에 맨 바깥 첫 인자만 보면 `mirror` 한 것을
    다시 `mirror` 할 수 없었다. 지우기까지 같이 막혀 있었다.
    """
    out = ready["axis_op"](DEF_SETS, "Cube 1", "mirror")
    out = ready["axis_op"](out, "Cube 1", "rotate")
    out = ready["axis_op"](out, "Cube 1", "mirror")
    assert out.startswith('c1 = mirror(rotate(mirror(cube("Cube 1"), ')
    ready["prepare"](out)


def test_a_wrapped_set_can_still_be_deleted(ready):
    """`remove_axis_set` 도 같은 기계로 대입문을 찾는다."""
    out = ready["axis_op"](DEF_SETS, "Cube 1", "mirror")
    gone = ready["remove_axis_set"](out, "Cube 1")
    assert "cube(" not in gone and "mirror(" not in gone
    ready["prepare"](gone)


# ---- 배포 (§19.13) --------------------------------------------------------

WORKFLOW = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")


def _shipped():
    """워크플로가 걷어낸 뒤 사이트에 남는 파일들."""
    import fnmatch

    strip = re.search(r"run: rm -rf (.+)", WORKFLOW).group(1).split()
    out = []
    for path in sorted((ROOT / "web").iterdir()):
        rel = "web/" + path.name
        if not any(fnmatch.fnmatch(rel, pat) for pat in strip):
            out.append(path.name)
    return out


def test_the_site_is_only_web():
    """`tests/` 와 `examples/` 는 우리 것이다. 사이트에 갈 이유가 없다."""
    assert re.search(r"upload-pages-artifact.*\n\s*with:\n\s*path: web\s*$",
                     WORKFLOW, re.M)


def test_stripping_does_not_break_the_page():
    """지울 것을 세는 방식이라 새 런타임 파일을 잊어도 안 깨진다. 그래도
    지금 참조하는 것이 다 남는지는 봐야 한다 — 여기서만 확인할 수 있다."""
    shipped = set(_shipped())
    for text in (PAGE, APP, WORKER):
        for ref in re.findall(r'["\'](?:\./)?([\w.-]+\.(?:js|css|html))(?:\?v=[0-9a-f]+)?["\']',
                              text):
            assert ref in shipped, ref + " 를 걷어냈는데 아직 참조한다"


def test_dev_files_do_not_ship():
    """파이썬은 전부 engine.js 안에 실려 있다 (§19.2). 파일로는 안 쓰인다."""
    shipped = _shipped()
    assert "index.html" in shipped and "engine.js" in shipped
    for name in shipped:
        assert not name.endswith((".py", ".test.js")), name


def test_the_workflow_does_not_try_to_enable_pages():
    """기본 GITHUB_TOKEN 에 Pages 를 켤 권한이 없다. 시도하면 배포가 죽는다 —
    사람이 Settings 에서 한 번 켜 주는 것이 맞다."""
    assert "enablement" not in WORKFLOW


def test_the_workflow_checks_the_bundle_before_deploying():
    """커밋된 생성물의 위험은 낡는 것이다. 그때 배포만 조용히 어긋난다."""
    assert "python web/bundle_engine.py" in WORKFLOW
    assert "git diff --exit-code -- web/" in WORKFLOW
    for js in ("syntax", "editor", "render", "share"):
        assert "node web/%s.test.js" % js in WORKFLOW
