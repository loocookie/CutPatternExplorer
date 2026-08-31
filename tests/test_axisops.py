"""축 집합 조작과 축 실림. 설계 문서 §2.1, §2.2."""

import math
from collections import Counter

import numpy as np
import pytest

from cutpattern import solids as S
from cutpattern.axisops import (
    invert,
    keep,
    merge,
    mirror,
    quaternion_matrix,
    remove,
    rename,
    rotate,
    rotation_from_pairs,
    same_directions,
)
from cutpattern.dsl import carry, puzzle, split, turn
from cutpattern.geometry.vector import rotation_matrix


def angle(a, b) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b)))))


def signature(aset) -> Counter:
    ns = [a.normal for a in aset]
    return Counter(round(angle(x, y), 6) for i, x in enumerate(ns) for y in ns[i + 1 :])


# ---- merge --------------------------------------------------------------


def test_merge_keeps_both_sources():
    m = merge("both", S.cube("cube"), S.octahedron("octahedron"))
    assert len(m) == 14
    assert [a.id for a in m][:2] == ["c-0", "c-1"]
    assert [a.id for a in m][-2:] == ["o-6", "o-7"]


def test_merge_dedupes_identical_directions():
    """같은 방향은 먼저 온 쪽만 남는다."""
    assert len(merge("dup", S.cube("cube"), S.cube("cube"))) == 6


def test_merge_of_cube_and_octahedron_is_a_cuboctahedron_axis_system():
    """아르키메데스 다면체 대부분은 방향집합이 플라톤의 합집합이다."""
    m = merge("cubocta", S.cube("cube"), S.octahedron("octahedron"))
    assert signature(m) == signature(merge("x", S.octahedron("octahedron"), S.cube("cube")))


def test_merge_with_a_rotated_copy():
    rotated = rotate(S.cube("cube"), axis=(1, 1, 1), angle=180)
    both = merge("pair", S.cube("cube"), rotated)
    assert len(both) == 12  # 180도 회전이 방향을 하나도 겹치지 않는다


def test_merge_disambiguates_colliding_ids():
    """축 id 는 집합 id 에서 나오므로 (§2.5) 보통은 안 겹친다. 같은 id 를 쓴
    두 집합을 합칠 때만 겹치고, 그때 merge 가 갈라 준다."""
    a = S.cube("a")
    b = rotate(S.cube("a"), axis=(0, 0, 1), angle=45)
    m = merge("m", a, b)
    ids = [x.id for x in m]
    assert len(ids) == len(set(ids))
    assert any(i.endswith("_1") for i in ids)


def test_merge_requires_at_least_one_set():
    with pytest.raises(ValueError):
        merge("empty")


# ---- rotate -------------------------------------------------------------


def test_rotate_by_axis_and_angle():
    r = rotate(S.cube("cube"), axis=(0, 0, 1), angle=90)
    assert np.allclose(r["c-2"].normal, (0, 1, 0), atol=1e-9)


def test_rotate_preserves_ids_and_shape():
    c = S.cube("cube")
    r = rotate(c, axis=(1, 2, 3), angle=37)
    assert [a.id for a in r] == [a.id for a in c]
    assert signature(r) == signature(c)


def test_rotate_by_quaternion_matches_axis_angle():
    half = math.radians(45.0)
    q = rotate(S.cube("cube"), quaternion=(math.cos(half), 0, 0, math.sin(half)))
    a = rotate(S.cube("cube"), axis=(0, 0, 1), angle=90)
    for x, y in zip(q, a):
        assert np.allclose(x.normal, y.normal, atol=1e-9)


def test_quaternion_matrix_is_a_rotation():
    m = quaternion_matrix((1, 2, 3, 4))
    assert np.allclose(m @ m.T, np.eye(3), atol=1e-12)
    assert float(np.linalg.det(m)) == pytest.approx(1.0)


def test_zero_quaternion_is_rejected():
    with pytest.raises(ValueError):
        quaternion_matrix((0, 0, 0, 0))


def test_rotate_from_two_pairs():
    c = S.cube("cube")
    a, b = c["c-0"].normal, c["c-2"].normal
    target_a = rotation_matrix((0, 0, 1), math.radians(90)) @ a
    target_b = rotation_matrix((0, 0, 1), math.radians(90)) @ b
    m = rotation_from_pairs([(a, target_a), (b, target_b)])
    assert np.allclose(m @ a, target_a, atol=1e-9)
    assert np.allclose(m @ b, target_b, atol=1e-9)


def test_pairs_reject_a_changed_included_angle():
    """사잇각이 보존되지 않으면 그런 회전은 없다. 조용히 근사하지 않는다."""
    c = S.cube("cube")
    with pytest.raises(ValueError, match="사잇각"):
        rotation_from_pairs(
            [(c["c-0"].normal, c["c-1"].normal), (c["c-1"].normal, c["c-1"].normal)]
        )


def test_pairs_reject_parallel_inputs():
    c = S.cube("cube")
    with pytest.raises(ValueError, match="평행"):
        rotation_from_pairs(
            [(c["c-0"].normal, c["c-1"].normal), (c["c-0"].normal, c["c-1"].normal)]
        )


def test_rotate_requires_exactly_one_form():
    c = S.cube("cube")
    with pytest.raises(ValueError):
        rotate(c)
    with pytest.raises(ValueError):
        rotate(c, axis=(0, 0, 1), angle=90, quaternion=(1, 0, 0, 0))
    with pytest.raises(ValueError):
        rotate(c, axis=(0, 0, 1))


# ---- remove / keep / rename ---------------------------------------------


def test_remove_and_keep_are_complementary():
    c = S.cube("cube")
    assert [a.id for a in remove(c, "c-0", "c-1")] == ["c-2", "c-3", "c-4", "c-5"]
    assert [a.id for a in keep(c, "c-0", "c-1")] == ["c-0", "c-1"]


def test_remove_accepts_axis_objects():
    c = S.cube("cube")
    assert len(remove(c, c["c-0"])) == 5


def test_remove_reports_unknown_axes():
    with pytest.raises(KeyError, match="없는 축"):
        remove(S.cube("cube"), "nope")


def test_rename_changes_only_the_given_ids():
    r = rename(S.cube("cube"), {"c-0": "U", "c-5": "D"})
    assert [a.id for a in r] == ["U", "c-1", "c-2", "c-3", "c-4", "D"]


def test_operations_do_not_mutate_the_source():
    c = S.cube("cube")
    before = [a.id for a in c]
    remove(c, "c-0")
    rotate(c, axis=(0, 0, 1), angle=90)
    rename(c, {"c-0": "X"})
    assert [a.id for a in c] == before


# ---- carry --------------------------------------------------------------


def _carry_family(declare: bool, angle_deg: float = 90.0):
    # 두 집합의 축 id 가 겹치면 안 된다 (§5). 약자는 집합 id 에서 나오므로
    # 서로 다른 id 를 주면 자동으로 갈린다
    outer = S.cube("outer")     # o-0 .. o-5
    inner = S.cube("inner")     # i-0 .. i-5
    with puzzle("carry", outer, inner) as p:
        if declare:
            carry(outer["o-0"], inner["i-2"])  # o-0 = (0,0,1),  i-2 = (1,0,0)
        split(outer["o-0"])
        turn(outer["o-0"], angle_deg)
        split(inner["i-2"])
    return p


def _inner_normals(p, inner_theta=20.0):
    reg, _ = p.evaluate({"outer": 80.0, "inner": inner_theta})
    h = math.cos(math.radians(inner_theta))
    return [bc.circle.n for bc in reg.non_empty() if abs(bc.circle.h - h) < 1e-9]


def test_axes_stay_put_without_a_carry_declaration():
    """기본값은 아무것도 실리지 않음이다. pCubes 도 같다."""
    got = _inner_normals(_carry_family(False))
    assert any(np.allclose(n, (1, 0, 0), atol=1e-9) for n in got)
    assert not any(np.allclose(n, (0, 1, 0), atol=1e-9) for n in got)


def test_declared_axis_rides_with_the_turn():
    got = _inner_normals(_carry_family(True))
    assert any(np.allclose(n, (0, 1, 0), atol=1e-9) for n in got)


@pytest.mark.parametrize("deg", [30.0, 45.0, 120.0])
def test_carried_axis_rotates_by_the_turn_angle(deg):
    got = _inner_normals(_carry_family(True, deg))
    expected = rotation_matrix((0, 0, 1), math.radians(deg)) @ np.array([1.0, 0.0, 0.0])
    assert any(np.allclose(n, expected, atol=1e-9) for n in got)


def test_carry_is_recorded_on_the_family():
    p = _carry_family(True)
    assert p.family.carries == (("o-0", ("i-2",)),)
    assert p.family.carried_by("o-0") == ("i-2",)
    assert p.family.carried_by("c-1") == ()


def test_carry_accepts_a_whole_axis_set():
    outer = S.cube("outer")
    inner = S.cube("inner")
    with puzzle("t", outer, inner) as p:
        carry(outer["o-0"], inner)
        split(outer)
    assert p.family.carries == (("o-0", tuple(a.id for a in inner)),)


def test_carry_rejects_self_reference():
    c = S.cube("cube")
    with puzzle("t", c):
        with pytest.raises(ValueError, match="자기 자신"):
            carry(c["c-0"], c["c-0"])


def test_carry_rejects_wrong_types():
    c = S.cube("cube")
    with puzzle("t", c):
        with pytest.raises(TypeError):
            carry("c-0", c["c-1"])
        with pytest.raises(TypeError):
            carry(c["c-0"], "c-1")


def test_carry_outside_a_puzzle_block_is_rejected():
    c = S.cube("cube")
    with pytest.raises(RuntimeError, match="with puzzle"):
        carry(c["c-0"], c["c-1"])


# ---- mirror / invert ----------------------------------------------------
#
# 반사는 det = -1 이라 회전이 아니다. rotate 로는 만들 수 없다.


def test_mirror_is_an_improper_isometry():
    m = mirror(S.cube("cube"), (0, 0, 1))
    assert len(m) == len(S.cube("cube"))
    assert all(float(np.linalg.norm(a.normal)) == pytest.approx(1.0) for a in m)
    # 사잇각은 보존된다. 반사는 등거리사상이다
    assert signature(m) == signature(S.cube("cube"))


def test_mirror_twice_is_identity():
    once = mirror(S.icosahedron("icosahedron"), (1, 2, 3))
    twice = mirror(once, (1, 2, 3))
    assert same_directions(twice, S.icosahedron("icosahedron"))


def test_mirror_of_an_achiral_solid_gives_the_same_directions_here():
    """정육면체는 z=0 평면 반사가 방향집합을 그대로 둔다."""
    assert same_directions(mirror(S.cube("cube"), (0, 0, 1)), S.cube("cube"))


@pytest.mark.parametrize(
    "key,rotation_group_name,full_group_name,size",
    [
        ("pentagonal_icositetrahedron", "O", "Oh", 24),
        ("pentagonal_hexecontahedron", "I", "Ih", 60),
    ],
)
def test_the_two_chiral_catalans_double_under_the_full_group(
    key, rotation_group_name, full_group_name, size
):
    """손대칭이면 반사를 넣은 궤도가 두 배가 된다. 이것이 손대칭의 증거다."""
    from cutpattern.geometry.symmetry import orbit

    seed = S._CATALAN_SEEDS[key][0]
    assert len(orbit(seed, rotation_group_name)) == size
    assert len(orbit(seed, full_group_name)) == 2 * size


@pytest.mark.parametrize(
    "key,full_group_name",
    [
        ("pentagonal_icositetrahedron", "Oh"),
        ("pentagonal_hexecontahedron", "Ih"),
    ],
)
def test_both_hands_merge_into_the_full_group_orbit(key, full_group_name):
    """한 손 + 거울상 = 전체군 궤도."""
    from cutpattern.axisops import same_directions
    from cutpattern.geometry.symmetry import orbit

    left = S.CATALAN[key]()
    right = mirror(left, (0, 0, 1), id=f"{key}_mirror")
    both = merge("both", left, right)
    full = S.from_normals(
        "full", orbit(S._CATALAN_SEEDS[key][0], full_group_name), "f"
    )
    assert len(both) == 2 * len(left)
    assert same_directions(both, full)


@pytest.mark.parametrize("key", ["cube", "octahedron", "rhombic_dodecahedron"])
def test_centrally_symmetric_solids_survive_inversion(key):
    aset = getattr(S, key)()
    assert same_directions(invert(aset), aset)


def test_tetrahedron_is_not_centrally_symmetric():
    """정사면체는 중심대칭이 아니다. 반전하면 쌍대 정사면체가 된다.

    손대칭이라는 뜻은 아니다. 정사면체는 거울면을 가지며, 거울상을 되돌리는
    회전이 T 밖(정팔면체 회전군 O)에 있을 뿐이다.
    """
    assert not same_directions(invert(S.tetrahedron("tetrahedron")), S.tetrahedron("tetrahedron"))
    # 반전한 것과 합치면 정육면체의 꼭짓점 방향 8개가 된다
    both = merge("both", S.tetrahedron("tetrahedron"), invert(S.tetrahedron("tetrahedron")))
    assert len(both) == 8
    assert signature(both) == signature(S.octahedron("octahedron"))


def test_invert_preserves_pairwise_angles():
    assert signature(invert(S.icosahedron("icosahedron"))) == signature(S.icosahedron("icosahedron"))


def test_same_directions_ignores_order_and_names():
    a = S.cube("cube")
    b = rename(remove(S.cube("cube"), "c-0"), {"c-1": "z"})
    assert same_directions(a, a)
    assert not same_directions(a, b)


def test_mirror_and_invert_do_not_mutate_the_source():
    before = [a.id for a in S.cube("cube")]
    c = S.cube("cube")
    mirror(c, (0, 0, 1))
    invert(c)
    assert [a.id for a in c] == before
