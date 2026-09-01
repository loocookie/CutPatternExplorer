"""절단원 바깥쪽 회전과 slice 합성. 설계 문서 §7."""

import math

import numpy as np
import pytest

from cutpattern.dsl import AxisSet, puzzle, split, turn, turned
from cutpattern.engine.axes import PuzzleFamily
from cutpattern.engine.operations import SplitByAxis, Turn, evaluate
from cutpattern.engine.turn import IllegalTurnError, is_turn_legal
from cutpattern.geometry.angular_coverage import TAU

THETA_333 = math.degrees(math.acos(1.0 / math.sqrt(3.0)))

# 축 id 는 이 테스트가 정한다. `Turn("U", 45, outer=True)` 처럼 방향이 읽혀야
# 하는 단정이 많아서, `solids` 의 `c0..c5` 보다 여기서 이름을 붙이는 쪽이 맞다.
# 축 집합을 회전시키지 않으므로 id 가 거짓말할 여지도 없다 (§2.2).
FACES = AxisSet(
    id="faces",
    axes={
        "U": (0, 1, 0),
        "D": (0, -1, 0),
        "R": (1, 0, 0),
        "L": (-1, 0, 0),
        "F": (0, 0, 1),
        "B": (0, 0, -1),
    },
    turns=(45, -45, 90, -90, 180),
    name="면축",
)


def raw(*ops, theta=THETA_333):
    """자동 rollback 없이 연산을 그대로 실행한다."""
    fam = PuzzleFamily(
        axis_sets=(FACES.to_engine(),),
        operations=tuple([SplitByAxis(a.id) for a in FACES] + list(ops)),
    )
    return evaluate(fam, {"faces": theta})


def complete_faces(reg, theta=THETA_333):
    h = math.cos(math.radians(theta))
    return {a.id for a in FACES if reg.find(a.normal, h)[0].is_complete}


# ---- 바깥쪽 회전 --------------------------------------------------------


def test_outer_turn_uses_the_same_legality_rule():
    """경계원이 같으므로 합법성 판정도 같다 (§7.1)."""
    reg, _ = raw()
    assert is_turn_legal(reg, FACES.U, THETA_333)
    # 경계원이 없으면 안쪽이든 바깥쪽이든 불법
    empty, _ = evaluate(
        PuzzleFamily(axis_sets=(FACES.to_engine(),), operations=(SplitByAxis("U"),)),
        {"faces": THETA_333},
    )
    from cutpattern.engine.turn import turn as do_turn

    with pytest.raises(IllegalTurnError):
        do_turn(empty, FACES.R, THETA_333, 45.0, outer=True)


def test_outer_turn_conserves_arc_length():
    reg, _ = raw(Turn("U", 45.0, True))
    assert reg.total_arc_length() == pytest.approx(6 * TAU)


def test_outer_and_inner_move_complementary_material():
    """같은 원의 두 쪽. 합치면 전체 회전이므로 carrier 구성이 같아야 한다."""
    inner, _ = raw(Turn("U", 45.0, False))
    outer, _ = raw(Turn("U", 45.0, True))
    assert inner.total_arc_length() == pytest.approx(outer.total_arc_length())
    assert len(inner.non_empty()) == len(outer.non_empty())


def test_outer_turn_leaves_the_cap_untouched():
    """바깥쪽 회전은 cap 안의 호를 건드리지 않는다."""
    before, _ = raw()
    after, _ = raw(Turn("U", 45.0, True))
    h = math.cos(math.radians(THETA_333))
    # U 원 자신은 경계라 양쪽 모두 고정
    b = before.find(FACES.U.normal, h)[0]
    a = after.find(FACES.U.normal, h)[0]
    assert [s.as_tuple() for s in a.spans] == pytest.approx([s.as_tuple() for s in b.spans])


def test_full_outer_turn_is_noop():
    reg, log = raw(Turn("U", 360.0, True))
    assert log[-1].no_op
    assert len(reg) == 6


# ---- slice 합성 ---------------------------------------------------------


def test_slice_is_outer_plus_opposite_cap():
    """M 슬라이스 = turn(U, a, outer) + turn(D, a). 별도 원시 연산이 필요 없다."""
    reg, _ = raw(Turn("U", 45.0, True), Turn("D", 45.0, False))
    # 띠만 움직였으므로 띠 경계인 U, D 원만 온전하다
    assert complete_faces(reg) == {"U", "D"}
    assert reg.total_arc_length() == pytest.approx(6 * TAU)
    # 옆면 네 개의 띠 구간이 45도 자리로 옮겨가 carrier 가 넷 늘어난다
    assert len(reg.non_empty()) == 10


def test_face_turns_are_blocked_after_a_45_slice():
    """실물 Mixup 이 45도 상태에서 면을 못 돌리는 것과 같다."""
    reg, _ = raw(Turn("U", 45.0, True), Turn("D", 45.0, False))
    assert is_turn_legal(reg, FACES.U, THETA_333)
    assert not is_turn_legal(reg, FACES.R, THETA_333)
    assert not is_turn_legal(reg, FACES.F, THETA_333)


def test_90_slice_realigns_and_creates_nothing():
    """45도를 두 번 하면 격자로 복귀한다."""
    reg, _ = raw(*([Turn("U", 45.0, True), Turn("D", 45.0, False)] * 2))
    assert complete_faces(reg) == {"R", "L", "U", "D", "F", "B"}
    assert len(reg.non_empty()) == 6
    assert reg.total_arc_length() == pytest.approx(6 * TAU)


def test_slice_moved_arcs_land_on_edge_directions():
    reg, _ = raw(Turn("U", 45.0, True), Turn("D", 45.0, False))
    face_normals = [a.normal for a in FACES]
    new = [
        bc
        for bc in reg.non_empty()
        if not any(
            np.allclose(bc.circle.n, f, atol=1e-9) or np.allclose(bc.circle.n, -f, atol=1e-9)
            for f in face_normals
        )
    ]
    assert len(new) == 4
    for bc in new:
        assert sorted(np.abs(np.round(bc.circle.n, 6))) == pytest.approx(
            [0.0, 1 / math.sqrt(2), 1 / math.sqrt(2)]
        )


def test_dsl_turned_supports_outer():
    with puzzle("t", FACES) as p:
        with turned(FACES.U, 45, outer=True):
            split(FACES.R)
    assert p.operations == (
        Turn("U", 45.0, True),
        SplitByAxis("R"),
        Turn("U", -45.0, True),
    )


def test_rollback_cancels_matching_outer_turns_only():
    """상쇄 판정은 축과 각뿐 아니라 어느 쪽인지도 봐야 한다."""
    with puzzle("cancel", FACES) as same_side:
        split(FACES)
        turn(FACES.U, 45, outer=True)
        turn(FACES.U, -45, outer=True)

    with puzzle("no cancel", FACES) as other_side:
        split(FACES)
        turn(FACES.U, 45, outer=True)
        turn(FACES.U, -45, outer=False)

    # 상쇄 판정은 접합 계획에 그대로 드러난다 (§7.10). TurnResult 개수로 세지
    # 않는다 — 접합하면 되돌리기가 실행되지 않아 로그에 안 남는다.
    #
    # 연산 배치는 둘 다 [0..5]=split, 6=Turn, 7=Turn, 8=RollbackTurns 다.
    from cutpattern.engine.operations import plan_conjugation

    # theta > 90 을 준다. outer 회전이 코어를 안 데려가는 구간이라 접합이
    # 그대로 살아 있고, 상쇄 판정만 남는다 (§2.4)
    angles = {k: 120.0 for k in same_side.family.cut_angle_inputs()}

    # 같은 쪽이면 짝이 맞아 두 번째 Turn 이 첫 번째를 닫는다
    assert plan_conjugation(same_side.family) == {6: 7}
    # 다른 쪽이면 서로 다른 영역이라 상쇄되지 않고 둘 다 rollback 이 닫는다
    assert plan_conjugation(other_side.family) == {6: 8, 7: 8}

    # 짝이 맞으므로 순효과가 없다. 그냥 split 한 것과 같은 상태여야 한다
    with puzzle("plain", FACES) as plain:
        split(FACES)
    same_reg, _ = evaluate(same_side.family, {"faces": THETA_333})
    plain_reg, _ = evaluate(plain.family, {"faces": THETA_333})
    assert same_reg.total_arc_length() == pytest.approx(plain_reg.total_arc_length())
    assert len(same_reg.non_empty()) == len(plain_reg.non_empty())


# ---- M 띠의 구간 구조 ---------------------------------------------------


@pytest.mark.parametrize("theta", [50.0, 54.7356, 60.0, 67.5, 75.0])
def test_side_circle_crosses_equator_at_azimuth_theta(theta):
    """R 원(x = cos theta)이 적도를 지나는 방위각은 정확히 +-theta 다.

    이것이 M 띠 구간 폭이 (2*theta - 90) 과 (180 - 2*theta) 인 이유다.
    """
    h = math.cos(math.radians(theta))
    z = math.sqrt(1.0 - h * h)
    azimuth = math.degrees(math.atan2(z, h))
    assert azimuth == pytest.approx(theta)


def test_equal_band_sectors_at_67_5_degrees():
    """8구간이 45도씩 등분되는 곳이 theta = 67.5 도다."""

    def gaps(theta):
        cross = sorted({(base + s * theta) % 360 for base in (0, 90, 180, 270) for s in (1, -1)})
        return [round((b - a) % 360, 6) for a, b in zip(cross, cross[1:] + [cross[0] + 360])]

    assert gaps(67.5) == [45.0] * 8
    wide = 180 - 2 * THETA_333
    narrow = 2 * THETA_333 - 90
    assert gaps(THETA_333) == pytest.approx([narrow, wide] * 4, abs=1e-4)
