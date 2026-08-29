"""Turn 테스트. 설계 문서 §7, §8, §17 시나리오."""

import math

import numpy as np
import pytest

from cutpattern.engine.axes import Axis, AxisSet, PuzzleFamily
from cutpattern.engine.operations import SplitByAxis, Turn, evaluate
from cutpattern.engine.turn import IllegalTurnError, is_turn_legal, turn
from cutpattern.geometry.angular_coverage import TAU, total_length

FACE_NORMALS = [
    ("U", (0, 1, 0)),
    ("D", (0, -1, 0)),
    ("R", (1, 0, 0)),
    ("L", (-1, 0, 0)),
    ("F", (0, 0, 1)),
    ("B", (0, 0, -1)),
]

ALL_FACE_SPLITS = tuple(SplitByAxis(i) for i in ("R", "L", "U", "D", "F", "B"))

# 3x3x3 면 절단의 각반경: 평면 x = 1/sqrt(3)
THETA_333 = math.degrees(math.acos(1.0 / math.sqrt(3.0)))

FACES = AxisSet(
    id="faces",
    cut_angle_input="faces",
    axes=tuple(Axis.make(i, n, (90.0, -90.0, 180.0)) for i, n in FACE_NORMALS),
)


def family(*ops) -> PuzzleFamily:
    return PuzzleFamily(axis_sets=(FACES,), operations=tuple(ops))


def run(*ops, theta=THETA_333):
    return evaluate(family(*ops), {"faces": theta})


# ---- §7.1 합법성 ------------------------------------------------------


def test_turn_legal_after_full_split():
    reg, _ = run(*ALL_FACE_SPLITS)
    for axis in FACES.axes:
        assert is_turn_legal(reg, axis, THETA_333)


def test_turn_illegal_when_boundary_circle_absent():
    reg, _ = run(SplitByAxis("U"))
    assert is_turn_legal(reg, FACES.axis("U"), THETA_333)
    assert not is_turn_legal(reg, FACES.axis("R"), THETA_333)
    with pytest.raises(IllegalTurnError):
        turn(reg, FACES.axis("R"), THETA_333, 90.0)


def test_illegal_turn_leaves_state_unchanged():
    """불법이면 아무것도 하지 않는다 (§7.1). 부분 변경도 없어야 한다."""
    reg, _ = run(*ALL_FACE_SPLITS, Turn("U", 45.0))
    before_carriers = len(reg)
    before_total = reg.total_arc_length()
    before_spans = [(bc.index, bc.spans.total_length()) for bc in reg]
    with pytest.raises(IllegalTurnError):
        turn(reg, FACES.axis("R"), THETA_333, 90.0)
    assert len(reg) == before_carriers
    assert reg.total_arc_length() == pytest.approx(before_total)
    assert [(bc.index, bc.spans.total_length()) for bc in reg] == pytest.approx(before_spans)


# ---- §8 시나리오 -------------------------------------------------------


def test_u45_then_r_split_scenario():
    """설계 문서 §8 을 그대로 재현한다."""
    theta = math.radians(THETA_333)
    d = math.cos(theta)
    r = math.sin(theta)
    # R 원이 U cap 안에 갖는 호 길이
    gap = 2.0 * math.acos(d / r)
    assert gap == pytest.approx(math.pi / 2)

    # 1. 전체 split
    reg, _ = run(*ALL_FACE_SPLITS)
    assert len(reg) == 6
    assert reg.total_arc_length() == pytest.approx(6 * TAU)

    # 2. U 45도 회전 -> 합법
    reg, log = run(*ALL_FACE_SPLITS, Turn("U", 45.0))
    tr = log[-1]
    assert tr.straddling_spans == 4  # R, L, F, B 가 U cap 경계를 가로지른다
    assert reg.total_arc_length() == pytest.approx(6 * TAU)  # 호 길이는 보존된다

    # 3. 이제 R 회전은 불법
    assert not is_turn_legal(reg, FACES.axis("R"), THETA_333)
    hit = reg.find(FACES.axis("R").normal, d)
    assert hit[0].spans.total_length() == pytest.approx(TAU - gap)

    # 4. R split 은 비어 있던 구간만 추가한다
    reg, log = run(*ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"))
    assert total_length(log[-1].added) == pytest.approx(gap)
    assert is_turn_legal(reg, FACES.axis("R"), THETA_333)

    # 5. 이후 R 회전은 합법
    reg, log = run(
        *ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"), Turn("R", 90.0)
    )
    assert not log[-1].no_op


def test_turn_conserves_total_arc_length():
    """Turn 은 재료를 옮길 뿐 만들거나 없애지 않는다 (§3)."""
    reg, _ = run(*ALL_FACE_SPLITS)
    before = reg.total_arc_length()
    turn(reg, FACES.axis("U"), THETA_333, 45.0)
    assert reg.total_arc_length() == pytest.approx(before)


def test_boundary_carrier_stays_fixed():
    """회전 경계원 자신은 통째로 고정 (§7.2 0단계)."""
    reg, _ = run(*ALL_FACE_SPLITS)
    d = math.cos(math.radians(THETA_333))
    bc = reg.find(FACES.axis("U").normal, d)[0]
    before = [s.as_tuple() for s in bc.spans]
    before_prov = [s.provenance for s in bc.spans]
    turn(reg, FACES.axis("U"), THETA_333, 45.0)
    assert [s.as_tuple() for s in bc.spans] == pytest.approx(before)
    assert [s.provenance for s in bc.spans] == before_prov


def test_coaxial_opposite_carrier_stays_fixed():
    """D 원은 U 축과 동축이고 cap 밖이므로 s~=0 분기로 고정된다 (§7.2 1단계)."""
    reg, _ = run(*ALL_FACE_SPLITS)
    d = math.cos(math.radians(THETA_333))
    bc = reg.find(FACES.axis("D").normal, d)[0]
    before = [s.as_tuple() for s in bc.spans]
    turn(reg, FACES.axis("U"), THETA_333, 45.0)
    assert [s.as_tuple() for s in bc.spans] == pytest.approx(before)


def test_full_turn_is_noop():
    reg, _ = run(*ALL_FACE_SPLITS)
    before = len(reg)
    result = turn(reg, FACES.axis("U"), THETA_333, 360.0)
    assert result.no_op
    assert len(reg) == before


def test_doctrinaire_turn_does_not_create_carriers():
    """90도 회전은 격자를 자기 자신으로 보내므로 새 carrier 가 생기지 않는다."""
    reg, _ = run(*ALL_FACE_SPLITS)
    before = len(reg)
    turn(reg, FACES.axis("U"), THETA_333, 90.0)
    assert len(reg) == before
    assert reg.total_arc_length() == pytest.approx(6 * TAU)


def test_repeated_doctrinaire_turns_do_not_drift():
    """스냅이 동작하면 90도 회전을 반복해도 carrier 가 늘지 않는다 (§7.4)."""
    reg, _ = run(*ALL_FACE_SPLITS)
    for i in range(40):
        axis = FACES.axes[i % 6]
        turn(reg, axis, THETA_333, 90.0)
    assert len(reg) == 6
    assert reg.total_arc_length() == pytest.approx(6 * TAU)
    for bc in reg:
        assert float(np.linalg.norm(bc.circle.n)) == pytest.approx(1.0, abs=1e-12)


def test_jumbling_turn_creates_new_carriers():
    """45도 회전은 기존 격자에 없는 자리로 호를 옮긴다. 이것이 jumbling 이다 (§3)."""
    reg, _ = run(*ALL_FACE_SPLITS)
    result = turn(reg, FACES.axis("U"), THETA_333, 45.0)
    assert result.carriers_after > result.carriers_before
    assert result.moved_spans > 0


def test_2x2x2_turn_with_merged_carriers():
    """theta=90 이면 carrier 3개. 병합된 상태에서도 회전이 합법이어야 한다 (§4.3)."""
    reg, _ = run(*ALL_FACE_SPLITS, theta=90.0)
    assert len(reg) == 3
    assert is_turn_legal(reg, FACES.axis("U"), 90.0)
    before = reg.total_arc_length()
    turn(reg, FACES.axis("U"), 90.0, 90.0)
    assert reg.total_arc_length() == pytest.approx(before)


def test_moved_arcs_stay_on_the_sphere():
    reg, _ = run(*ALL_FACE_SPLITS, Turn("U", 45.0), Turn("U", 45.0))
    for bc in reg.non_empty():
        for span in bc.spans:
            for t in np.linspace(span.t0, span.t1, 5):
                p = bc.circle.point(t)
                assert float(np.linalg.norm(p)) == pytest.approx(1.0, abs=1e-12)
                assert float(p @ bc.circle.n) == pytest.approx(bc.circle.h, abs=1e-12)


def test_turn_records_provenance():
    """이동한 호는 어느 turn 이 옮겼는지 남긴다 (§5, 단계 2)."""
    reg, _ = run(*ALL_FACE_SPLITS, Turn("U", 45.0))
    kinds = {s.provenance.kind for bc in reg.non_empty() for s in bc.spans}
    assert kinds == {"split", "turn"}
    turned = [s for bc in reg.non_empty() for s in bc.spans if s.provenance.kind == "turn"]
    assert turned
    assert all(s.provenance.axis_id == "U" for s in turned)
    assert all(s.provenance.op_index == 6 for s in turned)  # split 6개 뒤


# ---- §13.1 불법 Turn 절단 ----------------------------------------------


def test_truncate_policy_stops_at_first_illegal_turn():
    """slider 를 움직이는 동안 family Turn 이 불법이 될 수 있다 (§13.1)."""
    from cutpattern.engine.operations import Truncated

    fam = family(*ALL_FACE_SPLITS, Turn("U", 45.0), Turn("R", 90.0), SplitByAxis("F"))
    reg, log = evaluate(fam, {"faces": THETA_333}, on_illegal="truncate")
    trunc = [r for r in log if isinstance(r, Truncated)]
    assert len(trunc) == 1
    assert trunc[0].op_index == 7  # split 6개 + Turn U
    assert trunc[0].axis_id == "R"
    assert trunc[0].remaining == 2
    # 불법 직전 상태가 그대로 남아 있어야 한다
    assert reg.total_arc_length() == pytest.approx(6 * TAU)


def test_raise_policy_is_the_default():
    fam = family(*ALL_FACE_SPLITS, Turn("U", 45.0), Turn("R", 90.0))
    with pytest.raises(IllegalTurnError):
        evaluate(fam, {"faces": THETA_333})


def test_shallow_cut_turn_moves_nothing():
    """theta 가 작으면 다른 원이 cap 에 닿지 않아 아무것도 움직이지 않는다."""
    reg, log = run(*ALL_FACE_SPLITS, Turn("U", 45.0), theta=20.0)
    assert log[-1].moved_spans == 0
    assert log[-1].straddling_spans == 0
    assert len(reg) == 6
    assert reg.total_arc_length() == pytest.approx(6 * TAU)


def test_illegal_turn_becomes_legal_again_when_angle_returns():
    """각도를 되돌리면 다시 합법이 된다 (§13.1 복원 근거)."""
    from cutpattern.engine.operations import Truncated

    fam = family(*ALL_FACE_SPLITS, Turn("U", 45.0), Turn("R", 90.0))

    def truncated(theta):
        _reg, log = evaluate(fam, {"faces": theta}, on_illegal="truncate")
        return any(isinstance(r, Truncated) for r in log)

    assert truncated(THETA_333)
    assert not truncated(20.0)
    assert truncated(THETA_333)


# ---- RollbackTurns ------------------------------------------------------


def _normals_close(a, b):
    return np.allclose(a, b, atol=1e-9) or np.allclose(a, -np.asarray(b), atol=1e-9)


def test_rollback_restores_original_circles():
    """구성용 회전을 되돌리면 원래 축의 원이 전부 완전 복원된다."""
    from cutpattern.engine.operations import RollbackTurns

    reg, _ = run(
        *ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"), RollbackTurns()
    )
    for axis in FACES.axes:
        hit = reg.find(axis.normal, math.cos(math.radians(THETA_333)))
        assert hit is not None
        assert hit[0].is_complete, f"{axis.id} 원이 복원되지 않았다"


def test_rollback_leaves_exactly_the_new_boundary():
    """남는 것은 U45 가 만든 새 경계 하나뿐이어야 한다 (§8)."""
    from cutpattern.engine.operations import RollbackTurns

    reg, _ = run(
        *ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"), RollbackTurns()
    )
    originals = [a.normal for a in FACES.axes]
    extra = [
        bc
        for bc in reg.non_empty()
        if not any(_normals_close(bc.circle.n, o) for o in originals)
    ]
    assert len(extra) == 1
    assert extra[0].spans.total_length() == pytest.approx(math.pi / 2)
    # R 을 U 축으로 -45도 돌린 자리
    expected = np.array([math.cos(math.radians(45.0)), 0.0, math.cos(math.radians(45.0))])
    assert _normals_close(extra[0].circle.n, expected)


def test_rollback_conserves_arc_length():
    from cutpattern.engine.operations import RollbackTurns

    before, _ = run(*ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"))
    after, _ = run(
        *ALL_FACE_SPLITS, Turn("U", 45.0), SplitByAxis("R"), RollbackTurns()
    )
    assert after.total_arc_length() == pytest.approx(before.total_arc_length())


def test_rollback_without_split_returns_to_start():
    """중간 split 이 없으면 완전히 원상복구된다."""
    from cutpattern.engine.operations import RollbackTurns

    base, _ = run(*ALL_FACE_SPLITS)
    reg, _ = run(*ALL_FACE_SPLITS, Turn("U", 45.0), RollbackTurns())
    assert len(reg.non_empty()) == len(base.non_empty())
    assert reg.total_arc_length() == pytest.approx(base.total_arc_length())
    for bc in reg.non_empty():
        assert bc.is_complete


def test_rollback_undoes_multiple_turns_in_reverse_order():
    from cutpattern.engine.operations import RollbackTurns

    base, _ = run(*ALL_FACE_SPLITS)
    reg, _ = run(
        *ALL_FACE_SPLITS,
        Turn("U", 45.0),
        SplitByAxis("R"),
        Turn("R", 30.0),
        SplitByAxis("F"),
        RollbackTurns(),
    )
    for axis in FACES.axes:
        hit = reg.find(axis.normal, math.cos(math.radians(THETA_333)))
        assert hit is not None and hit[0].is_complete
    assert reg.total_arc_length() > base.total_arc_length()


def test_rollback_with_no_turns_is_harmless():
    from cutpattern.engine.operations import RollbackTurns

    base, _ = run(*ALL_FACE_SPLITS)
    reg, _ = run(*ALL_FACE_SPLITS, RollbackTurns())
    assert len(reg.non_empty()) == len(base.non_empty())
    assert reg.total_arc_length() == pytest.approx(base.total_arc_length())
