"""carrier registry 테스트. 설계 문서 §4.3, §7.4, §17."""

import math

import numpy as np
import pytest

from cutpattern.geometry.angular_coverage import TAU, full, is_full, total_length
from cutpattern.geometry.registry import BoundaryRegistry
from cutpattern.geometry.vector import rotation_matrix


def test_negated_normal_merges_to_one_carrier():
    """(n, h) 와 (-n, -h) 는 같은 원이므로 carrier 하나여야 한다 (§4.3)."""
    reg = BoundaryRegistry()
    reg.add_coverage((0, 1, 0), 0.5, full())
    reg.add_coverage((0, -1, 0), -0.5, full())
    assert len(reg) == 1


def test_2x2x2_six_axes_at_90_merge_into_three():
    """면 6축 theta=90 이면 마주보는 축이 같은 평면을 만든다 (§4.3).

    병합하지 않으면 coverage 가 쪼개져 Turn 합법성 판정이 오작동한다.
    """
    reg = BoundaryRegistry()
    h = math.cos(math.radians(90.0))
    normals = [(0, 1, 0), (0, -1, 0), (1, 0, 0), (-1, 0, 0), (0, 0, 1), (0, 0, -1)]
    added_lengths = []
    for n in normals:
        _bc, added = reg.add_coverage(n, h, full())
        added_lengths.append(total_length(added))
    assert len(reg) == 3
    # 짝의 두 번째 축은 아무것도 새로 추가하지 않는다
    assert added_lengths[0] == pytest.approx(TAU)
    assert added_lengths[1] == pytest.approx(0.0)
    assert all(bc.is_complete for bc in reg)


def test_distinct_planes_not_merged():
    reg = BoundaryRegistry()
    h = math.cos(math.radians(54.7356))
    reg.add_coverage((0, 1, 0), h, full())
    reg.add_coverage((0, -1, 0), h, full())
    assert len(reg) == 2


def test_rotation_noise_finds_existing_carrier():
    """R_u90 · (1,0,0) 은 (0,0,-1) 에서 1e-16 만큼 벗어난다 (§7.4)."""
    reg = BoundaryRegistry()
    h = math.cos(math.radians(60.0))
    reg.add_coverage((0, 0, -1), h, full())
    n_rot = rotation_matrix((0, 1, 0), math.pi / 2) @ np.array([1.0, 0.0, 0.0])
    assert not np.array_equal(n_rot, np.array([0.0, 0.0, -1.0]))
    hit = reg.find(n_rot, h)
    assert hit is not None
    assert len(reg) == 1


def test_repeated_rotation_does_not_grow_registry():
    """스냅이 동작하면 90도 회전을 반복해도 carrier 가 늘지 않는다 (§7.4)."""
    reg = BoundaryRegistry()
    h = math.cos(math.radians(60.0))
    for n in [(1, 0, 0), (0, 0, 1), (-1, 0, 0), (0, 0, -1)]:
        reg.add_coverage(n, h, full())
    assert len(reg) == 4

    R = rotation_matrix((0, 1, 0), math.pi / 2)
    n = np.array([1.0, 0.0, 0.0])
    for _ in range(200):
        n = R @ n
        bc, _added = reg.add_coverage(n, h, full())
        # 스냅: 계산된 값이 아니라 registry 에 저장된 값을 쓴다
        n = bc.circle.n if float(bc.circle.n @ n) > 0 else -bc.circle.n
    assert len(reg) == 4
    assert all(abs(float(np.linalg.norm(bc.circle.n)) - 1.0) < 1e-12 for bc in reg)


def test_is_fully_covered_reflects_coverage():
    """§7.1 Turn 합법성 판정의 본체."""
    reg = BoundaryRegistry()
    h = math.cos(math.radians(60.0))
    bc, _ = reg.add_coverage((0, 1, 0), h, full())
    assert reg.is_fully_covered((0, 1, 0), h)
    # 일부를 제거하면 더 이상 완전하지 않다
    bc.subtract([(1.0, 2.0)])
    assert not reg.is_fully_covered((0, 1, 0), h)
    # 반대 표현으로 물어도 같은 답이어야 한다
    assert not reg.is_fully_covered((0, -1, 0), -h)


def test_find_does_not_create():
    reg = BoundaryRegistry()
    assert reg.find((0, 1, 0), 0.5) is None
    assert len(reg) == 0


def test_partial_coverage_difference_only_adds_gap():
    """이미 덮인 부분은 중복 추가되지 않는다 (§3, §8)."""
    reg = BoundaryRegistry()
    h = math.cos(math.radians(60.0))
    bc, _ = reg.add_coverage((0, 1, 0), h, [(0.0, 4.0)])
    _bc, added = reg.add_coverage((0, 1, 0), h, full())
    assert total_length(added) == pytest.approx(TAU - 4.0)
    assert is_full(bc.coverage)
