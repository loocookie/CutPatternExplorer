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
from cutpattern.dsl import AxisSet, attach, puzzle, split, turn
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
    with pytest.raises(ValueError, match="angle between"):
        rotation_from_pairs(
            [(c["c-0"].normal, c["c-1"].normal), (c["c-1"].normal, c["c-1"].normal)]
        )


def test_pairs_reject_parallel_inputs():
    c = S.cube("cube")
    with pytest.raises(ValueError, match="parallel"):
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
    with pytest.raises(KeyError, match="no such axes"):
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


# ---- attach (§2.4) -------------------------------------------------------
#
# 무엇에 얹혀 있는지는 선언하고, 어느 회전이 나를 움직이는지는 기하가 정한다.
#   코어에 얹힘(기본) -> 코어가 움직일 때. 코어는 늘 바깥쪽이므로 outer 회전만
#   집합에 얹힘        -> 그 집합의 회전 영역 안에 있을 때. 안쪽이든 바깥쪽이든


def _two_sets(attached: bool, angle_deg=90.0, outer_turn=False, outer_theta=100.0):
    """`outer_theta` 가 100 이면 inner 축(90도 떨어져 있다)이 cap 안에 들어온다."""
    outer = S.cube("outer")     # o-0 = (0,0,1)
    inner = S.cube("inner")     # i-2 = (1,0,0)
    if attached:
        inner = attach(inner, to=outer)
    with puzzle("t", outer, inner) as p:
        split(outer["o-0"])
        turn(outer["o-0"], angle_deg, outer=outer_turn)
        split(inner["i-2"])
    return p, outer_theta


def _inner_normals(built, inner_theta=20.0):
    p, outer_theta = built
    reg, _ = p.evaluate({"outer": outer_theta, "inner": inner_theta})
    h = math.cos(math.radians(inner_theta))
    return [bc.circle.n for bc in reg.non_empty() if abs(bc.circle.h - h) < 1e-9]


def _has(normals, target):
    return any(np.allclose(n, target, atol=1e-9) for n in normals)


def test_core_mounted_axes_ignore_a_cap_turn():
    """기본값은 코어다. cap 회전에서는 코어가 안 움직이므로 가만히 있는다."""
    got = _inner_normals(_two_sets(attached=False, outer_theta=80.0))
    assert _has(got, (1, 0, 0))
    assert not _has(got, (0, 1, 0))


def test_core_mounted_axes_ride_an_outer_turn():
    """**theta < 90 이면 outer 회전이 코어를 움직인다.**

    절단면이 축 쪽(`d = cos theta > 0`)에 있으므로 코어는 바깥쪽에 있다.
    """
    got = _inner_normals(_two_sets(attached=False, outer_turn=True, outer_theta=80.0))
    assert _has(got, (0, 1, 0))


def test_nobody_carries_the_core_past_ninety_degrees():
    """theta > 90 이면 코어를 아무도 안 데려간다 (§2.4).

    마주 보는 두 cap 이 겹치고 그 교집합이 가운데 층이다. 코어는 거기 들어가
    있지만 실리지 않는다 — 그런 퍼즐은 코어를 구형으로 만든다. 믹스업 계열이
    이 구간이라, 여기서 코어를 실으면 그 퍼즐이 통째로 틀어진다.
    """
    for outer_turn in (False, True):
        got = _inner_normals(
            _two_sets(attached=False, outer_turn=outer_turn, outer_theta=100.0)
        )
        assert _has(got, (1, 0, 0)), outer_turn
        assert not _has(got, (0, 1, 0)), outer_turn


def test_an_attached_axis_inside_the_region_rides_along():
    """호스트 집합의 회전 영역 안이면 함께 돈다. 코어 규칙과 무관하다."""
    got = _inner_normals(_two_sets(attached=True, outer_theta=100.0))
    assert _has(got, (0, 1, 0))


@pytest.mark.parametrize("deg", [30.0, 45.0, 120.0])
def test_a_carried_axis_rotates_by_the_turn_angle(deg):
    got = _inner_normals(_two_sets(attached=True, angle_deg=deg, outer_theta=100.0))
    expected = rotation_matrix((0, 0, 1), math.radians(deg)) @ np.array([1.0, 0.0, 0.0])
    assert _has(got, expected)


def test_carrying_is_decided_per_axis_not_per_set():
    """같은 attach 로 묶인 두 축이 한 회전에서 갈릴 수 있다 (§2.4).

    `is_carried` 는 축 하나하나의 위치를 본다 — 집합째 묻지 않는다. 여기서는
    host 축 `h` 에서 30도 떨어진 축은 60도 cap 회전에 실리고, 80도 떨어진
    축은 그 자리에 남는다. 두 축이 같은 `rider` 에 얹혀 있는데도 그렇다.
    """
    host = AxisSet("host", axes={"h": (0.0, 0.0, 1.0)})
    rider = attach(AxisSet("rider", axes={
        "close": (math.sin(math.radians(30)), 0.0, math.cos(math.radians(30))),
        "far": (math.sin(math.radians(80)), 0.0, math.cos(math.radians(80))),
    }), to=host)
    with puzzle("t", host, rider) as p:
        split(host["h"])
        turn(host["h"], 45.0)
        split(rider["close"])
        split(rider["far"])
    reg, _ = p.evaluate({"host": 60.0, "rider": 45.0})

    h_target = math.cos(math.radians(45.0))
    got = [bc.circle.n for bc in reg.non_empty() if abs(bc.circle.h - h_target) < 1e-9]

    rotated_close = rotation_matrix((0, 0, 1), math.radians(45.0)) @ np.array(
        [math.sin(math.radians(30)), 0.0, math.cos(math.radians(30))]
    )
    unrotated_far = np.array([math.sin(math.radians(80)), 0.0, math.cos(math.radians(80))])
    assert _has(got, rotated_close), "30도 떨어진 축은 실려야 한다"
    assert _has(got, unrotated_far), "80도 떨어진 축은 그대로여야 한다"


def test_the_rule_table():
    """`is_carried` 를 규칙 그대로 짚는다."""
    shell = S.cube("shell")
    rider = attach(S.cube("rider"), to=shell)
    with puzzle("t", shell, rider) as p:
        split(shell)
    fam = p.family

    # 코어에 얹힘: 위치와 무관하게 코어가 움직이느냐만 본다
    for in_region in (True, False):
        for outer in (False, True):
            assert not fam.is_carried(
                "shell", "shell", outer=outer, in_region=in_region,
                core_in_region=False)
            assert fam.is_carried(
                "shell", "shell", outer=outer, in_region=in_region,
                core_in_region=True)

    # 집합에 얹힘: 그 집합의 회전이면 내 위치가 정한다
    for outer in (False, True):
        assert fam.is_carried("rider", "shell", outer=outer, in_region=True,
                              core_in_region=False)
        assert not fam.is_carried("rider", "shell", outer=outer, in_region=False,
                                  core_in_region=True)


def test_a_chain_follows_its_host():
    """A 가 B 에, B 가 코어에 얹혀 있으면 A 는 B 를 따라간다."""
    base = S.cube("base")
    mid = attach(S.octahedron("mid"), to=base)
    top = attach(S.tetrahedron("top"), to=mid)
    with puzzle("t", base, mid, top) as p:
        split(base)
    fam = p.family

    # base 를 도는 회전: mid 는 영역이 정하고, top 은 mid 를 따라 같은 답
    assert fam.is_carried("mid", "base", outer=False, in_region=True,
                          core_in_region=False)
    assert fam.is_carried("top", "base", outer=False, in_region=True,
                          core_in_region=False)
    assert not fam.is_carried("top", "base", outer=False, in_region=False,
                              core_in_region=False)

    # 아무 집합도 아닌 회전이면 사슬 끝의 코어 규칙으로 떨어진다
    assert fam.is_carried("top", "elsewhere", outer=True, in_region=False,
                          core_in_region=True)
    assert not fam.is_carried("top", "elsewhere", outer=True, in_region=True,
                              core_in_region=False)


def test_attach_rejects_self_and_wrong_types():
    c = S.cube("cube")
    with pytest.raises(ValueError, match="attached to itself"):
        attach(c, to=c)
    with pytest.raises(TypeError, match="needs an axis set"):
        attach(c, to="cube")


def test_attach_survives_the_other_axis_ops():
    """rotate/mirror 로 방향을 바꿔도 무엇에 물려 있는지는 그대로다."""
    shell = S.cube("shell")
    rider = attach(S.cube("rider"), to=shell)
    assert rotate(rider, axis=(0, 0, 1), angle=30).attached is shell
    assert mirror(rider, normal=(0, 0, 1)).attached is shell


def test_attaching_to_a_set_outside_the_puzzle_is_rejected():
    shell = S.cube("shell")
    rider = attach(S.cube("rider"), to=shell)
    with pytest.raises(ValueError, match="not one of this puzzle"):
        with puzzle("t", rider) as p:
            split(rider)


# ---- mirror / invert ----------------------------------------------------
#
# 반사는 det = -1 이라 회전이 아니다. rotate 로는 만들 수 없다.


def test_mirror_is_an_improper_isometry():
    m = mirror(S.cube("cube"), normal=(0, 0, 1))
    assert len(m) == len(S.cube("cube"))
    assert all(float(np.linalg.norm(a.normal)) == pytest.approx(1.0) for a in m)
    # 사잇각은 보존된다. 반사는 등거리사상이다
    assert signature(m) == signature(S.cube("cube"))


def test_mirror_twice_is_identity():
    once = mirror(S.icosahedron("icosahedron"), normal=(1, 2, 3))
    twice = mirror(once, normal=(1, 2, 3))
    assert same_directions(twice, S.icosahedron("icosahedron"))


def test_mirror_of_an_achiral_solid_gives_the_same_directions_here():
    """정육면체는 z=0 평면 반사가 방향집합을 그대로 둔다."""
    assert same_directions(mirror(S.cube("cube"), normal=(0, 0, 1)), S.cube("cube"))


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
    right = mirror(left, normal=(0, 0, 1), id=f"{key}_mirror")
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
    mirror(c, normal=(0, 0, 1))
    invert(c)
    assert [a.id for a in c] == before
