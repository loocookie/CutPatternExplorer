"""회전군과 궤도. 설계 문서 §2.1 축 집합 생성의 기반."""

import math

import numpy as np
import pytest

from cutpattern.geometry.symmetry import (
    GROUP_ORDERS,
    cyclic_group,
    dedupe_directions,
    dihedral_group,
    orbit,
    rotation_group,
)

PHI = (1.0 + math.sqrt(5.0)) / 2.0


@pytest.mark.parametrize("name,order", sorted(GROUP_ORDERS.items()))
def test_group_has_expected_order(name, order):
    assert len(rotation_group(name)) == order


ROTATION_GROUPS = ["T", "O", "I"]
FULL_GROUPS = ["Td", "Oh", "Ih"]


@pytest.mark.parametrize("name", ROTATION_GROUPS)
def test_rotation_group_elements_are_proper(name):
    """회전군은 반사를 포함하지 않는다."""
    for m in rotation_group(name):
        assert np.allclose(m @ m.T, np.eye(3), atol=1e-9)
        assert float(np.linalg.det(m)) == pytest.approx(1.0)


@pytest.mark.parametrize("name", sorted(GROUP_ORDERS))
def test_group_is_closed_under_multiplication(name):
    group = rotation_group(name)
    keys = {tuple(np.round(m, 7).ravel()) for m in group}
    for a in group[:6]:
        for b in group[:6]:
            assert tuple(np.round(a @ b, 7).ravel()) in keys


def test_unknown_group_is_rejected():
    with pytest.raises(KeyError):
        rotation_group("Q")


# ---- 궤도 = 면추이 다면체의 면 법선 -------------------------------------

# (이름, 씨앗, 군, 면 개수)
FACE_ORBITS = [
    ("정사면체", (1, 1, 1), "T", 4),
    ("정육면체", (1, 0, 0), "O", 6),
    ("정팔면체", (1, 1, 1), "O", 8),
    ("마름모십이면체", (1, 1, 0), "O", 12),
    ("정십이면체", (0, 1, PHI), "I", 12),
    ("정이십면체", (1, 1, 1), "I", 20),
    ("마름모삼십면체", (1, 0, 0), "I", 30),
]


@pytest.mark.parametrize("label,seed,group,count", FACE_ORBITS)
def test_orbit_size_matches_face_count(label, seed, group, count):
    """궤도 크기가 면 개수와 같은지로 씨앗이 맞는지 자동 검증된다."""
    dirs = orbit(seed, group, expected=count)
    assert len(dirs) == count
    for v in dirs:
        assert float(np.linalg.norm(v)) == pytest.approx(1.0)


@pytest.mark.parametrize("label,seed,group,count", FACE_ORBITS)
def test_orbit_is_closed_under_its_group(label, seed, group, count):
    dirs = orbit(seed, group)
    for m in rotation_group(group):
        for v in dirs:
            w = m @ v
            assert any(float(np.linalg.norm(w - u)) < 1e-9 for u in dirs)


@pytest.mark.parametrize("label,seed,group,count", FACE_ORBITS)
def test_orbit_directions_are_distinct(label, seed, group, count):
    dirs = orbit(seed, group)
    for i, v in enumerate(dirs):
        for w in dirs[i + 1 :]:
            assert float(np.linalg.norm(v - w)) > 1e-6


def test_orbit_size_check_catches_a_wrong_seed():
    """정육면체 면축을 (1,1,1) 로 만들려 하면 8개가 나와 바로 잡힌다."""
    with pytest.raises(ValueError, match="orbit size"):
        orbit((1, 1, 1), "O", expected=6)


def test_orbit_is_deterministic():
    a = orbit((1, 1, 0), "O")
    b = orbit((1, 1, 0), "O")
    assert [tuple(np.round(v, 12)) for v in a] == [tuple(np.round(v, 12)) for v in b]


def test_zero_seed_is_rejected():
    with pytest.raises(ValueError):
        orbit((0, 0, 0), "O")


# ---- 각기둥 계열 군 ------------------------------------------------------


@pytest.mark.parametrize("n", [3, 4, 5, 6, 8])
def test_cyclic_group_size(n):
    assert len(cyclic_group(n)) == n


@pytest.mark.parametrize("n", [3, 4, 5, 6])
def test_dihedral_group_size(n):
    assert len(dihedral_group(n)) == 2 * n


def test_prism_side_normals_from_cyclic_group():
    """n각기둥 옆면 법선 n개는 순환군 궤도다."""
    sides = orbit((1, 0, 0), cyclic_group(5), expected=5)
    assert len(sides) == 5
    for v in sides:
        assert float(v[2]) == pytest.approx(0.0, abs=1e-12)


# ---- 방향 중복 제거 ------------------------------------------------------


def test_dedupe_keeps_antipodes_apart():
    """반대 방향은 다른 축이다 (§2.2)."""
    out = dedupe_directions([(1, 0, 0), (-1, 0, 0), (1, 0, 0)])
    assert len(out) == 2


def test_dedupe_normalizes():
    out = dedupe_directions([(3, 0, 0)])
    assert float(np.linalg.norm(out[0])) == pytest.approx(1.0)


# ---- 반사를 포함한 전체군 -----------------------------------------------


@pytest.mark.parametrize("name,order", [("Td", 24), ("Oh", 48), ("Ih", 120)])
def test_full_group_order(name, order):
    assert len(rotation_group(name)) == order


@pytest.mark.parametrize("name", FULL_GROUPS)
def test_full_group_elements_are_orthogonal(name):
    dets = set()
    for m in rotation_group(name):
        assert np.allclose(m @ m.T, np.eye(3), atol=1e-9)
        dets.add(round(float(np.linalg.det(m)), 6))
    assert dets == {1.0, -1.0}  # 반사가 섞여 있다


@pytest.mark.parametrize("name,has_inversion", [("Td", False), ("Oh", True), ("Ih", True)])
def test_inversion_membership(name, has_inversion):
    """Oh = O x {I, -I}, Ih = I x {I, -I} 이지만 Td 는 반전을 포함하지 않는다."""
    group = rotation_group(name)
    found = any(np.allclose(m, -np.eye(3), atol=1e-9) for m in group)
    assert found is has_inversion


@pytest.mark.parametrize("full,rot", [("Td", "T"), ("Oh", "O"), ("Ih", "I")])
def test_rotation_group_is_a_subgroup_of_the_full_group(full, rot):
    keys = {tuple(np.round(m, 7).ravel()) for m in rotation_group(full)}
    for m in rotation_group(rot):
        assert tuple(np.round(m, 7).ravel()) in keys


def test_group_name_is_case_insensitive():
    assert len(rotation_group("oh")) == 48
    assert len(rotation_group("ih")) == 120


def test_rotation_groups_contain_no_reflections():
    """T / O / I 는 순수 회전군이다. det = +1 만 있어야 한다 (§2.5).

    생성원에 반사가 섞이면 궤도에 반대 손 방향이 딸려 들어오는데, 크기만 보면
    기대값과 맞아떨어져 통과할 수 있다. 손대칭 입체에서 조용히 틀린 축 집합이
    나오므로 닫을 때 걸러야 한다.
    """
    for name in ("T", "O", "I"):
        for m in rotation_group(name):
            assert float(np.linalg.det(np.asarray(m))) == pytest.approx(1.0)


def test_full_groups_do_contain_reflections():
    """Td / Oh / Ih 는 반사를 포함한다. 위 검사가 이쪽을 막으면 안 된다."""
    for name in ("Td", "Oh", "Ih"):
        dets = {round(float(np.linalg.det(np.asarray(m))), 6) for m in rotation_group(name)}
        assert dets == {1.0, -1.0}


def test_closing_a_rotation_group_rejects_a_reflected_generator():
    """생성원에 반사를 섞으면 닫는 단계에서 거부한다."""
    from cutpattern.geometry.symmetry import _axis_rotation, _close_group
    from cutpattern.geometry.vector import Mat3

    mirror = Mat3(((-1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)))
    with pytest.raises(RuntimeError, match="reflections"):
        _close_group([_axis_rotation((0, 0, 1), math.pi / 2), mirror])

    # allow_improper 를 주면 통과한다. Td / Oh / Ih 가 그 경로다
    assert _close_group(
        [_axis_rotation((0, 0, 1), math.pi / 2), mirror], allow_improper=True
    )


def test_pyritohedral_group_is_available():
    """황철석 십이면체(pyritohedron)의 대칭은 Th 다 (§2.5).

    회전 대칭이야 for 문으로 되지만 정다면체 대칭은 손으로 쓰기 어렵다.
    씨앗과 군 이름만으로 축을 복제할 수 있어야 한다.
    """
    assert GROUP_ORDERS["Th"] == 24
    group = rotation_group("Th")
    assert len(group) == 24
    dets = {round(float(np.linalg.det(np.asarray(m))), 6) for m in group}
    assert dets == {1.0, -1.0}, "Th = T x {I, -I} 이므로 반전을 포함한다"


def test_th_is_not_td():
    """크기는 같지만 다른 군이다. 원소가 같으면 하나는 필요 없다."""
    th = {tuple(round(v, 9) for row in m for v in row) for m in rotation_group("Th")}
    td = {tuple(round(v, 9) for row in m for v in row) for m in rotation_group("Td")}
    assert len(th) == len(td) == 24
    assert th != td


def test_a_generic_seed_gives_twelve_faces_under_th():
    """(1, h, 0) 이 pyritohedron 의 씨앗이다. h 를 바꾸면 면이 기울어진다."""
    for h in (0.2, 0.5, 0.8):
        assert len(orbit((1, h, 0), "Th")) == 12
        # 정육면체 대칭이면 24개가 되어 다른 입체가 된다
        assert len(orbit((1, h, 0), "O")) == 24


def test_group_names_are_case_insensitive():
    assert len(rotation_group("th")) == len(rotation_group("Th"))
