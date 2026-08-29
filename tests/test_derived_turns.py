"""회전각 유도. 설계 문서 §7.

회전각은 정적 값이 아니라 현재 절단 각도의 함수다.
"""


import pytest

from cutpattern import solids as S
from cutpattern.dsl import AxisSet
from cutpattern.engine.axes import PuzzleFamily
from cutpattern.engine.turns import available_turns, derived_turns, rings_around


def family_of(*axis_sets) -> PuzzleFamily:
    return PuzzleFamily(axis_sets=tuple(s.to_engine() for s in axis_sets))


def turns(aset, theta, axis_id=None, **kw):
    fam = family_of(aset)
    axis = aset[axis_id] if axis_id else list(aset)[0]
    return [round(v, 4) for v in derived_turns(fam, axis, {aset.cut: theta}, **kw)]


# ---- 정다면체 -----------------------------------------------------------


@pytest.mark.parametrize(
    "factory,theta,expected",
    [
        (S.tetrahedron, 80.0, [120.0, 240.0]),
        (S.cube, 60.0, [90.0, 180.0, 270.0]),
        (S.octahedron, 70.0, [120.0, 240.0]),
        (S.dodecahedron, 50.0, [72.0, 144.0, 216.0, 288.0]),
    ],
)
def test_derived_turns_match_face_symmetry(factory, theta, expected):
    assert turns(factory(), theta) == pytest.approx(expected)


def test_icosahedron_needs_more_than_face_symmetry():
    """면 대칭 차수만 보면 (120, 240) 이지만 그건 첫 고리뿐이다.

    두 번째 고리는 축이 6개다. C3 궤도 두 개가 75.522 도 어긋나 겹쳐 있어서
    쌍차에 44.478 과 75.522 가 나온다. 이것이 jumbling 정렬각이다.
    """
    got = turns(S.icosahedron(), 45.0)
    assert 120.0 in got and 240.0 in got
    assert got != pytest.approx([120.0, 240.0])
    assert min(got) == pytest.approx(44.4775, abs=1e-3)
    assert got == pytest.approx(
        [44.4775, 75.5225, 120.0, 164.4775, 195.5225, 240.0, 284.4775, 315.5225],
        abs=1e-3,
    )


def test_icosahedron_first_ring_alone_gives_only_face_symmetry():
    """첫 고리만 침범하는 얕은 절단에서는 (120, 240) 이 맞다."""
    icosa = S.icosahedron()
    fam = family_of(icosa)
    axis = list(icosa)[0]
    shallow = 25.0  # 41.81 도 고리만 걸리는 깊이
    rings = rings_around(fam, axis, {icosa.cut: shallow})
    assert len(rings) == 1
    assert turns(icosa, shallow) == pytest.approx([120.0, 240.0])


# ---- 축마다 다른 각 -----------------------------------------------------


@pytest.mark.parametrize("theta", [50.0, 70.0, 85.0])
def test_prism_side_and_cap_differ(theta):
    """n각기둥은 옆면과 밑면의 회전각이 다르다. 정적 필드로는 표현이 안 된다."""
    p5 = S.prism(5)
    assert turns(p5, theta, "p0") == pytest.approx([180.0])
    assert turns(p5, theta, "p5") == pytest.approx([72.0, 144.0, 216.0, 288.0])


def test_bipyramid_axes_are_uniform():
    """면추이적이면 모든 축이 같은 목록을 준다."""
    bp = S.bipyramid(5)
    first = turns(bp, 70.0, "b0")
    assert first
    for axis in bp:
        assert turns(bp, 70.0, axis.id) == pytest.approx(first)


# ---- 절단 각도 의존성 ---------------------------------------------------


def test_engagement_threshold_matches_the_inequality():
    """cube 는 |90 - theta| < theta, 곧 theta > 45 에서 고리가 침범한다."""
    cube = S.cube()
    assert turns(cube, 30.0) == []
    assert turns(cube, 44.0) == []
    assert turns(cube, 46.0) == pytest.approx([90.0, 180.0, 270.0])
    assert turns(cube, 80.0) == pytest.approx([90.0, 180.0, 270.0])


def test_shallow_cut_engages_nothing():
    """cap 안에 다른 절단원이 없으면 어떤 각도 유도되지 않는다."""
    cube = S.cube()
    fam = family_of(cube)
    assert rings_around(fam, list(cube)[0], {cube.cut: 20.0}) == {}


def test_rings_are_grouped_by_polar_angle_and_cut_depth():
    """회전은 극각을 보존하고, 원이 겹치려면 반지름도 같아야 한다."""
    icosa = S.icosahedron()
    fam = family_of(icosa)
    rings = rings_around(fam, list(icosa)[0], {icosa.cut: 80.0})
    sizes = sorted(len(m) for m in rings.values())
    assert sizes == [3, 3, 6, 6]
    for (_polar, theta2), members in rings.items():
        assert theta2 == pytest.approx(80.0)


def test_axis_on_the_rotation_axis_adds_no_constraint():
    """극각 0 이나 180 은 방위각이 없다. 회전에 불변이므로 제약이 아니다."""
    cube = S.cube()
    fam = family_of(cube)
    rings = rings_around(fam, list(cube)[0], {cube.cut: 80.0})
    for polar, _theta2 in rings:
        assert 1e-6 < polar < 180.0 - 1e-6


# ---- 여러 축 집합 -------------------------------------------------------


def test_second_axis_set_contributes_its_own_rings():
    cube = S.cube("cube")
    octa = S.octahedron("octa")
    fam = family_of(cube, octa)
    axis = list(cube)[0]
    angles = {"cube": 60.0, "octa": 60.0}
    rings = rings_around(fam, axis, angles)
    assert {theta2 for _polar, theta2 in rings} == {60.0}
    alone = derived_turns(family_of(cube), axis, {"cube": 60.0})
    both = derived_turns(fam, axis, angles)
    assert set(round(v, 6) for v in alone) <= set(round(v, 6) for v in both)


def test_carried_axes_are_excluded():
    """함께 실려 도는 축은 정렬을 따질 게 없으므로 제외한다 (§2.1)."""
    cube = S.cube()
    fam = family_of(cube)
    axis = list(cube)[0]
    ring_axes = [
        a.id
        for members in rings_around(fam, axis, {cube.cut: 60.0}).values()
        for a, _phi in members
    ]
    assert turns(cube, 60.0) == pytest.approx([90.0, 180.0, 270.0])
    assert derived_turns(fam, axis, {cube.cut: 60.0}, carried=set(ring_axes)) == []


# ---- 명시 각과의 합집합 -------------------------------------------------


def test_extra_turn_angles_are_unioned():
    """유도가 못 찾는 각은 축에 명시한다."""
    cube = S.cube(turns=(45.0,))
    fam = family_of(cube)
    axis = list(cube)[0]
    angles = {cube.cut: 60.0}
    assert derived_turns(fam, axis, angles) == pytest.approx([90.0, 180.0, 270.0])
    assert available_turns(fam, axis, angles) == pytest.approx([45.0, 90.0, 180.0, 270.0])


def test_extra_turn_angles_do_not_duplicate_derived_ones():
    cube = S.cube(turns=(90.0, 450.0))
    fam = family_of(cube)
    axis = list(cube)[0]
    assert available_turns(fam, axis, {cube.cut: 60.0}) == pytest.approx(
        [90.0, 180.0, 270.0]
    )


def test_zero_is_never_a_turn():
    cube = S.cube(turns=(0.0, 360.0))
    fam = family_of(cube)
    axis = list(cube)[0]
    assert 0.0 not in available_turns(fam, axis, {cube.cut: 60.0})


# ---- 진단 ---------------------------------------------------------------


def test_unknown_axis_is_reported():
    cube = S.cube()
    stray = AxisSet("stray", axes={"s0": (1, 2, 3)})
    with pytest.raises(KeyError):
        derived_turns(family_of(cube), stray["s0"], {"cube": 60.0})
