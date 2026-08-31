"""OctoCube Master 구성을 정십이면체에 적용한 것. 설계 문서 §17 시나리오."""

import math

import numpy as np
import pytest

from cutpattern.geometry.symmetry import rotation_group
from examples.octododeca import (
    ADJACENT_DEG,
    MAX_THETA_DEG,
    MIN_THETA_DEG,
    THETA_DEG,
    TURN_ANGLE,
    build,
)
from tests.test_region import _final_dangling, _on_some_cut


@pytest.fixture(scope="module")
def dodeca():
    p = build()
    reg, _log = p.evaluate({"dodecahedron": THETA_DEG})
    return p, reg


def _faces(p):
    return list(p.family.axis_sets[0].axes)


def _is_face(n, faces) -> bool:
    return any(
        np.allclose(n, a.normal, atol=1e-9) or np.allclose(n, -a.normal, atol=1e-9)
        for a in faces
    )


def test_construction_mirrors_the_cube_version():
    """면마다 회전 한 번 + 인접면 split. 정육면체는 45도/4면, 정십이면체는 36도/5면."""
    p = build()
    faces = _faces(p)
    assert len(faces) == 12
    assert TURN_ANGLE == pytest.approx(36.0)
    assert ADJACENT_DEG == pytest.approx(math.degrees(math.acos(1 / math.sqrt(5))))
    from cutpattern.query import at_angle

    for x in faces:
        assert len(at_angle(x, ADJACENT_DEG, faces)) == 5


def test_face_circles_survive(dodeca):
    p, reg = dodeca
    offset = math.cos(math.radians(THETA_DEG))
    for axis in _faces(p):
        bc, _orient = reg.find(axis.normal, offset)
        assert bc.is_complete


def test_new_boundaries_are_one_orbit_of_sixty(dodeca):
    p, reg = dodeca
    faces = _faces(p)
    new = [b for b in reg.non_empty() if not _is_face(b.circle.n, faces)]
    assert len(new) == 60
    lengths = {round(b.spans.total_length(), 9) for b in new}
    assert len(lengths) == 1


def test_no_dangling_cut(dodeca):
    _p, reg = dodeca
    assert not _final_dangling(reg)


def test_pattern_is_full_icosahedral(dodeca):
    """정십이면체 자체의 대칭을 그대로 갖는다.

    정육면체판이 T 까지만 가는 것과 다르다. 그쪽은 pCubes 가 매크로 3개만
    쓰기 때문이고, 이쪽은 모든 면에 같은 구성을 적용하기 때문이다.
    """
    _p, reg = dodeca
    points = [
        bc.circle.point(t0 + (t1 - t0) * k / 4)
        for bc in reg.non_empty()
        for t0, t1 in bc.coverage
        for k in (1, 3)
    ]
    assert all(_on_some_cut(reg, g @ q) for g in rotation_group("Ih") for q in points)


@pytest.mark.parametrize("theta", [24.0, 30.0])
def test_shallow_cuts_produce_nothing(theta):
    """인접면 원이 X 의 cap 을 못 건드리면 회전해도 새 절단이 없다.

    경계는 인접 사잇각의 절반이다. 정육면체의 45도(=90/2)에 대응한다.
    """
    assert theta < MIN_THETA_DEG
    reg, _log = build().evaluate({"dodecahedron": theta})
    assert len(reg.non_empty()) == 12


@pytest.mark.parametrize("theta", [32.0, 40.0, THETA_DEG, 55.0, 63.0])
def test_slider_range_stays_clean(theta):
    assert MIN_THETA_DEG < theta < MAX_THETA_DEG
    reg, _log = build().evaluate({"dodecahedron": theta})
    assert len(reg.non_empty()) == 72
    assert not _final_dangling(reg)
    total = sum(b.spans.total_length() for b in reg.circles)
    covered = sum(t1 - t0 for b in reg.circles for t0, t1 in b.coverage)
    assert total == pytest.approx(covered, abs=1e-9)
