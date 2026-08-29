"""Mixup Plus 시나리오. 설계 문서 §7 slice 합성, §17 시나리오."""

import math

import numpy as np
import pytest

from cutpattern.engine.axes import PuzzleFamily
from cutpattern.engine.operations import Turn, evaluate
from cutpattern.engine.turn import is_turn_legal
from examples.mixup_plus import THETA_333, THETA_MIXUP, build

SLICE_45 = (Turn("U", 45.0, True), Turn("D", 45.0, False))


@pytest.fixture(scope="module")
def plus():
    return build()


def _without_rollback(p, extra=()):
    """자동 rollback 을 떼고 뒤에 연산을 덧붙여 실행한다."""
    return PuzzleFamily(
        axis_sets=p.family.axis_sets,
        operations=p.family.operations[:-1] + tuple(extra),
    )


def _complete(reg, faces, theta):
    h = math.cos(math.radians(theta))
    return {a.id for a in faces if reg.find(a.normal, h)[0].is_complete}


def test_construction_restores_every_face_circle(plus):
    """블록마다 슬라이스를 되돌리므로 여섯 면 원이 전부 완전해야 한다."""
    reg, _ = plus.evaluate({"faces": THETA_MIXUP})
    faces = plus.axis_sets[0]
    assert _complete(reg, faces, THETA_MIXUP) == {a.id for a in faces}


def test_new_boundaries_are_twelve_edge_direction_planes(plus):
    """45도 자리의 절단은 면 법선을 수직축으로 45도 돌린 방향, 곧 모서리 방향이다."""
    reg, _ = plus.evaluate({"faces": THETA_MIXUP})
    faces = plus.axis_sets[0]
    face_normals = [a.normal for a in faces]
    new = [
        bc
        for bc in reg.non_empty()
        if not any(
            np.allclose(bc.circle.n, f, atol=1e-9) or np.allclose(bc.circle.n, -f, atol=1e-9)
            for f in face_normals
        )
    ]
    assert len(new) == 12
    root2 = 1 / math.sqrt(2)
    for bc in new:
        assert sorted(np.abs(np.round(bc.circle.n, 6))) == pytest.approx([0.0, root2, root2])


@pytest.mark.parametrize("theta", [THETA_333, 60.0, THETA_MIXUP, 75.0])
def test_45_slice_is_closed_after_the_plus_cuts(theta, plus):
    """Plus 절단을 넣으면 45도 슬라이스가 격자를 보존한다.

    0-계열 원이 45-계열로, 45-계열이 90(=0)-계열로 가서 집합이 닫힌다.
    그래서 45도 상태에서도 면 회전이 계속 합법이다.
    """
    faces = plus.axis_sets[0]
    before, _ = evaluate(_without_rollback(plus), {"faces": theta})
    after, _ = evaluate(_without_rollback(plus, SLICE_45), {"faces": theta})

    assert len(after) == len(before)  # carrier 가 늘지 않는다
    assert after.total_arc_length() == pytest.approx(before.total_arc_length())
    assert _complete(after, faces, theta) == {a.id for a in faces}
    for axis in faces:
        assert is_turn_legal(after, axis, theta)


def test_plain_cube_blocks_face_turns_after_a_45_slice():
    """대조군. Plus 절단이 없으면 45도 슬라이스 후 면 회전이 막힌다."""
    from cutpattern.dsl import cube_faces
    from cutpattern.engine.operations import SplitByAxis

    faces = cube_faces("faces")
    fam = PuzzleFamily(
        axis_sets=(faces.to_engine(),),
        operations=tuple([SplitByAxis(a.id) for a in faces]) + SLICE_45,
    )
    reg, _ = evaluate(fam, {"faces": THETA_333})
    assert is_turn_legal(reg, faces.U, THETA_333)
    assert not is_turn_legal(reg, faces.R, THETA_333)


def test_slice_composition_conserves_arc_length(plus):
    before, _ = evaluate(_without_rollback(plus), {"faces": THETA_MIXUP})
    after, _ = evaluate(_without_rollback(plus, SLICE_45 * 2), {"faces": THETA_MIXUP})
    assert after.total_arc_length() == pytest.approx(before.total_arc_length())


@pytest.mark.parametrize("theta", [50.0, 54.7356, 60.0, THETA_MIXUP, 80.0])
def test_slider_sweep_stays_legal_and_finite(theta, plus):
    reg, _ = plus.evaluate({"faces": theta})
    for bc in reg.non_empty():
        assert math.isfinite(bc.circle.h) and math.isfinite(bc.circle.r)
        assert all(math.isfinite(x) for s in bc.spans for x in s.as_tuple())


def test_equal_sectors_is_aesthetic_not_a_requirement(plus):
    """theta = 67.5 는 조각 크기가 같아지는 지점일 뿐 작동 조건이 아니다.

    45도 슬라이스가 닫히는지는 Plus 절단의 존재로 정해지고, theta 와 무관하다.
    """
    faces = plus.axis_sets[0]
    for theta in (THETA_333, THETA_MIXUP):
        after, _ = evaluate(_without_rollback(plus, SLICE_45), {"faces": theta})
        assert _complete(after, faces, theta) == {a.id for a in faces}
