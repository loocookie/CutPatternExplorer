"""회전 짝 접합. 설계 문서 §7.10, §12.3-2.

`turned(a, θ)` 블록의 순효과는 `E ∪ Φ⁻¹(C)` 다. 회전을 실행하지 않고 새 절단만
끌어와도 결과가 같아야 한다. 이 파일의 본체는 그 등가성이다 — 접합을 끄고 켠
두 실행이 같은 기하를 내는지 각도를 쓸어 가며 확인한다.
"""

from __future__ import annotations

import importlib

import pytest

import cutpattern.engine.operations as OPS
from cutpattern import solids as S
from cutpattern.dsl import (
    outside,
    puzzle,
    region,
    split,
    turn,
    turned,
)
from cutpattern.engine.operations import Truncated, plan_conjugation
# 축 id 는 방향을 말해주지 않는다 (`c0`..`c5`). 방향을 박은 id 를 두면
# axisops.rotate 한 번에 거짓말이 되므로 (§2.2), 여기서 이름을 묶는다.
# 방향은 S.cube() 를 갓 만든 상태 기준이다.
R, L = "c2", "c4"   # +x, -x
U, D = "c3", "c1"   # +y, -y
F, B = "c0", "c5"   # +z, -z


EXAMPLES = (
    "quantum",
    "octododeca",
    "octocube_hide",
    "octocube_master",
    "mixup_plus",
    "jumbling_u45",
    "cube_faces",
)


def _no_conjugation(_family):
    return {}


def _run(p, angles):
    reg, log = p.evaluate(angles, on_illegal="truncate")
    return (
        round(reg.total_arc_length(), 9),
        len(reg.non_empty()),
        _planes(reg),
        tuple(r.op_index for r in log if isinstance(r, Truncated)),
    )


def _planes(reg):
    """평면 집합. (n, h) 와 (-n, -h) 는 같은 평면이므로 한쪽으로 접는다 (§4.3)."""
    out = set()
    for bc in reg.non_empty():
        n = tuple(round(v, 7) for v in bc.circle.n)
        h = round(bc.circle.h, 7)
        if n < tuple(-v for v in n):
            n, h = tuple(-v for v in n), -h
        out.add((n, h, round(bc.spans.total_length(), 7)))
    return out


@pytest.fixture
def conjugation_off(monkeypatch):
    """접합을 끈다. 폴백 경로(지금까지의 회전 실행)로 흐른다."""
    monkeypatch.setattr(OPS, "plan_conjugation", _no_conjugation)


@pytest.mark.parametrize("name", EXAMPLES)
def test_conjugation_matches_the_unconjugated_path(name, monkeypatch):
    """예제마다 각도를 쓸며 접합 켬/끔이 같은 결과를 내는가.

    호 길이, non-empty carrier 수, 평면 집합, 절단 지점을 모두 본다. 호 길이만
    보면 재료가 엉뚱한 평면으로 가도 통과한다.
    """
    module = importlib.import_module("examples." + name)
    inputs = module.build().family.cut_angle_inputs()

    for step in range(1, 18):
        theta = step * 10.0
        angles = {k: theta for k in inputs}

        monkeypatch.setattr(OPS, "plan_conjugation", _no_conjugation)
        plain = _run(module.build(), angles)
        monkeypatch.undo()
        conjugated = _run(module.build(), angles)

        assert conjugated == plain, f"{name} theta={theta}"


def test_plan_finds_every_turned_pair():
    """`turned()` 짝은 전부 접합 대상이어야 한다."""
    from cutpattern.engine.operations import Turn

    for name in ("octododeca", "octocube_hide", "octocube_master", "mixup_plus"):
        family = importlib.import_module("examples." + name).build().family
        turns = [i for i, op in enumerate(family.operations) if isinstance(op, Turn)]
        pairs = plan_conjugation(family)
        assert len(pairs) * 2 == len(turns), name


def test_rollback_closes_bare_turns():
    """맨 `turn()` 도 접합된다. 닫는 것은 정의 끝의 자동 RollbackTurns 다.

    이게 없으면 같은 기하를 내는 두 표기(`turned()` 블록 대 맨 `turn()`)가
    소스만 봐서는 안 보이는 성능 차이를 갖는다 (§7.10).
    """
    faces = S.cube("faces", turns=(45, -45))
    with puzzle("bare", faces) as p:
        split(faces)
        turn(faces[U], 45)
        split(faces[R])
    ops = p.family.operations
    rollback = len(ops) - 1
    assert plan_conjugation(p.family) == {6: rollback}


def test_plan_refuses_what_it_cannot_prove():
    """증명 못 하는 것은 넣지 않는다. 빠지면 폴백이라 결과는 같고 느릴 뿐이다."""
    # 짝 사이에서 여는 region 블록. 영역이 회전을 따라 변환되는 경로다
    f2 = S.cube("f2", turns=(45, -45))
    with puzzle("inner-region", f2) as q:
        split(f2)
        with turned(f2[U], 45):
            with region(outside(f2[R]), outside(f2[L])):
                split(f2[F])
    assert plan_conjugation(q.family) == {}

    # 실린 축. 블록 안 split 이 실린 축을 쓰면 법선이 달라진다 (§2.1)
    from cutpattern.dsl import carry

    f3 = S.cube("f3", turns=(45, -45))
    with puzzle("carried", f3) as r:
        carry(f3[U], f3[R])
        split(f3)
        with turned(f3[U], 45):
            split(f3[R])
    assert plan_conjugation(r.family) == {}


def test_mixed_fallback_and_conjugation_agree():
    """바깥은 폴백, 안쪽은 접합인 경우에도 결과가 같아야 한다.

    registry 는 바깥 회전이 실제로 적용된 좌표계를 들고 있고 안쪽 프레임은 그
    위에서 정의되므로 둘이 일관된다. RollbackTurns 는 실행된 적 없는 회전을
    되돌리지 않는다 — 접합된 회전은 pending_turns 에 들어가지 않기 때문이다.
    """
    from cutpattern.dsl import carry

    def build():
        f = S.cube("f", turns=(45, -45, 90, -90))
        with puzzle("mixed", f) as p:
            carry(f[U], f[F])        # U 는 실려 있어 접합 대상이 아니다
            split(f)
            with turned(f[U], 45):   # 폴백
                with turned(f[R], 45):  # 접합
                    split(f[F], f[B])
        return p

    plan = plan_conjugation(build().family)
    assert len(plan) == 1, plan  # R 짝만 접합된다

    for theta in (40.0, 54.7356, 63.0, 70.0):
        original = OPS.plan_conjugation
        OPS.plan_conjugation = _no_conjugation
        try:
            plain = _run(build(), {"f": theta})
        finally:
            OPS.plan_conjugation = original
        assert _run(build(), {"f": theta}) == plain, theta


def test_region_outside_the_pair_is_still_conjugated():
    """블록 **바깥의** 영역은 접합해도 된다.

    `Φ⁻¹(C ∩ Φ(R)) = Φ⁻¹(C) ∩ R` 이므로, 끌어온 뒤 변환되지 않은 원본 영역으로
    자르면 된다. OctoCube Hide 가 이 모양이다 (§6.3, §7.10).
    """
    from cutpattern.engine.operations import Turn

    family = importlib.import_module("examples.octocube_hide").build().family
    turns = [i for i, op in enumerate(family.operations) if isinstance(op, Turn)]
    assert len(plan_conjugation(family)) * 2 == len(turns)


def test_conjugation_removes_the_empty_carrier_leftovers():
    """왕복이 만들던 빈 carrier 가 안 생긴다 (§12.3-2).

    registry 가 부풀면 Turn 이 carrier 전체를 훑으므로 비용이 제곱으로 간다.
    그것이 접합의 이득이 상수가 아닌 이유다.
    """
    from examples.octocube_master import THETA_DEG, build

    reg, _log = build().evaluate({"faces": THETA_DEG})
    assert len(reg) == len(reg.non_empty())


def test_conjugated_split_keeps_the_split_provenance():
    """왕복하지 않으므로 기존 호가 회전 provenance 를 뒤집어쓰지 않는다 (§5).

    예전에는 나갔다 돌아온 호가 되돌리기 연산의 op_index 를 달고 kind="turn" 이
    되었다. 아무것도 그 호를 옮기지 않았으므로 split 출처가 맞다.
    """
    from examples.octocube_master import THETA_DEG, build

    reg, _log = build().evaluate({"faces": THETA_DEG})
    kinds = {s.provenance.kind for bc in reg.non_empty() for s in bc.spans}
    assert kinds == {"split"}
