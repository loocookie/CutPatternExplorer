"""엔진이 numpy 없이 도는지. 설계 문서 §12.2, §15, §19.

numpy 는 hot path 에서 걷어냈다. 되돌아오면 §12.2 의 4~6배가 조용히 사라지고
브라우저 배포의 전제(§19)도 무너진다. 사람이 알아채기 어려운 종류의 회귀라
테스트로 막는다.

테스트 코드 자체는 numpy 를 비교 보조로 쓴다. 그래서 같은 프로세스에서
`sys.modules` 를 건드릴 수 없고, 별도 프로세스를 띄워 확인한다.
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

PACKAGE = pathlib.Path(__file__).resolve().parents[1] / "cutpattern"
ROOT = PACKAGE.parent

# 개발용 뷰어만 예외다. vpython 이 numpy 를 끌고 오므로 판정에서 뺀다 (§15)
_ALLOWED = {"vpython_view.py"}


def test_no_numpy_import_in_package_source():
    """`import numpy` 가 들어간 파일이 없는가."""
    offenders = []
    for path in PACKAGE.rglob("*.py"):
        if path.name in _ALLOWED:
            continue
        text = path.read_text(encoding="utf-8")
        for lineno, line in enumerate(text.splitlines(), 1):
            stripped = line.strip()
            if stripped.startswith(("import numpy", "from numpy")):
                offenders.append(f"{path.relative_to(ROOT)}:{lineno}")
    assert not offenders, f"numpy import 발견: {offenders}"


# numpy import 를 막아 놓고 정의 하나를 끝까지 평가한다.
# 주석이 아니라 실제 실행 경로에 numpy 가 없다는 것을 확인하는 쪽이다.
_PROBE = """
import builtins, math, sys
_real = builtins.__import__
def guard(name, *a, **k):
    if name == "numpy" or name.startswith("numpy."):
        raise AssertionError("numpy import 시도: " + name)
    return _real(name, *a, **k)
builtins.__import__ = guard

from cutpattern import solids as S
from cutpattern.dsl import at_angle, outside, puzzle, region, split, turned
from cutpattern.render.arcs import build_arcs
from cutpattern import solids as S
from cutpattern.axisops import merge, mirror
from cutpattern.engine.operations import Truncated, UncutBoundaryError

THETA = math.degrees(math.acos(0.45))

# 1. split + turn + 렌더
faces = S.cube(turns=(45, -45, 90, -90, 180))
with puzzle("probe", faces) as p:
    split(faces)
    for x in faces:
        with turned(x, 45):
            split(*at_angle(x, 90, faces))
reg, log = p.evaluate({"cube": THETA}, on_illegal="truncate")
arcs = build_arcs(reg, max_step=0.05)
assert len(reg) == 18, len(reg)
assert len(arcs) == 30, len(arcs)
assert abs(reg.total_arc_length() - 87.747970730) < 1e-9, reg.total_arc_length()

# 2. region 블록. EnterRegion 의 경계 사전 판정이 covers_within 을 타므로
#    region.py 의 clip / classify 경로가 여기서만 지나간다 (§6.3)
from examples.octocube_hide import build as build_hide
reg2, log2 = build_hide().evaluate({"cube": THETA}, on_illegal="truncate")
assert not [r for r in log2 if isinstance(r, Truncated)], "예상 못한 절단"
assert len(reg2) == 18, len(reg2)

# 3. 경계 미절단을 실제로 잡는가. 판정 경로까지 numpy 없이 돈다
f2 = S.cube("second", turns=(45, -45, 90, -90, 180))
with puzzle("uncut", f2) as q:
    split(f2["s-0"], f2["s-5"])
    with region(outside(f2["s-2"]), outside(f2["s-4"])):
        split(f2["s-3"], f2["s-1"])
try:
    q.evaluate({"second": THETA}, on_illegal="raise")
    raise AssertionError("UncutBoundaryError 가 나왔어야 한다")
except UncutBoundaryError:
    pass

# 4. 축 집합 생성 (대칭군, 궤도)
S.rhombic_triacontahedron()
S.pentagonal_hexecontahedron()
print("OK")
"""


def test_engine_runs_with_numpy_import_blocked():
    """실행 경로에 numpy 가 없는가.

    split, turn, region 블록(경계 사전 판정 포함), 축 집합 생성, 렌더까지 판다.
    region 을 빼면 `geometry/region.py` 의 clip 과 covers_within 이 통째로
    검사에서 새어 나간다 — `EnterRegion` 이 유일한 진입점이기 때문이다.
    """
    proc = subprocess.run(
        [sys.executable, "-c", _PROBE],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    assert proc.returncode == 0, proc.stderr
    assert "OK" in proc.stdout
