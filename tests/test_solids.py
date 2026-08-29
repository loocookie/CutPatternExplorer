"""표준 입체 프리셋. 설계 문서 §2.1, §2.2."""

import math
from collections import Counter

import numpy as np
import pytest

from cutpattern import solids as S


def angle(a, b) -> float:
    return math.degrees(math.acos(max(-1.0, min(1.0, float(a @ b)))))


def signature(aset) -> Counter:
    """회전 불변량. 축 쌍 사잇각의 다중집합.

    같은 입체라도 놓인 방향이 다를 수 있으므로 방향 집합을 그대로 비교하면 안 된다.
    """
    ns = [a.normal for a in aset]
    return Counter(
        round(angle(x, y), 6) for i, x in enumerate(ns) for y in ns[i + 1 :]
    )


# ---- 정다면체 -----------------------------------------------------------

PLATONIC_COUNTS = [
    (S.tetrahedron, 4, "t"),
    (S.cube, 6, "c"),
    (S.octahedron, 8, "o"),
    (S.dodecahedron, 12, "d"),
    (S.icosahedron, 20, "i"),
]


@pytest.mark.parametrize("factory,count,prefix", PLATONIC_COUNTS)
def test_platonic_face_count(factory, count, prefix):
    aset = factory()
    assert len(aset) == count
    assert [a.id for a in aset] == [f"{prefix}{i}" for i in range(count)]


@pytest.mark.parametrize("factory,count,prefix", PLATONIC_COUNTS)
def test_platonic_normals_are_unit(factory, count, prefix):
    for a in factory():
        assert float(np.linalg.norm(a.normal)) == pytest.approx(1.0)


@pytest.mark.parametrize("factory,count,prefix", PLATONIC_COUNTS)
def test_platonic_is_face_transitive(factory, count, prefix):
    """면추이적이면 모든 축에서 본 사잇각 분포가 같아야 한다."""
    axes = list(factory())
    profiles = {
        tuple(sorted(round(angle(a.normal, b.normal), 6) for b in axes if b.id != a.id))
        for a in axes
    }
    assert len(profiles) == 1


@pytest.mark.parametrize("factory,count,prefix", PLATONIC_COUNTS)
def test_platonic_carries_no_static_turn_angles(factory, count, prefix):
    """회전각은 절단 각도의 함수라 프리셋에 박지 않는다 (engine.turns)."""
    assert all(a.extra_turn_angles == () for a in factory())


def test_octahedron_directions_are_cube_vertices():
    verts = [
        np.array(v, dtype=float) / math.sqrt(3)
        for v in [
            (1, 1, 1), (1, 1, -1), (1, -1, 1), (1, -1, -1),
            (-1, 1, 1), (-1, 1, -1), (-1, -1, 1), (-1, -1, -1),
        ]
    ]
    got = [a.normal for a in S.octahedron()]
    for v in verts:
        assert any(np.allclose(v, g, atol=1e-9) for g in got)


# ---- 각기둥 계열 --------------------------------------------------------

PRISM_COUNTS = [
    (S.prism, lambda n: n + 2, "p"),
    (S.antiprism, lambda n: 2 * n + 2, "a"),
    (S.bipyramid, lambda n: 2 * n, "b"),
    (S.trapezohedron, lambda n: 2 * n, "z"),
]


@pytest.mark.parametrize("factory,count,prefix", PRISM_COUNTS)
@pytest.mark.parametrize("n", [3, 4, 5, 6, 8])
def test_prism_family_face_count(factory, count, prefix, n):
    aset = factory(n)
    assert len(aset) == count(n)
    assert all(float(np.linalg.norm(a.normal)) == pytest.approx(1.0) for a in aset)
    assert [a.id for a in aset] == [f"{prefix}{i}" for i in range(count(n))]


@pytest.mark.parametrize("factory,count,prefix", PRISM_COUNTS)
def test_prism_family_rejects_small_n(factory, count, prefix):
    with pytest.raises(ValueError):
        factory(2)


# 꼭짓점 하나에서 유도하므로 쌍대 관계가 방향까지 맞아야 한다
DUAL_IDENTITIES = [
    ("trapezohedron(3)", lambda: S.trapezohedron(3), "cube", S.cube),
    ("antiprism(3)", lambda: S.antiprism(3), "octahedron", S.octahedron),
    ("bipyramid(4)", lambda: S.bipyramid(4), "octahedron", S.octahedron),
    ("prism(4)", lambda: S.prism(4), "cube", S.cube),
]


@pytest.mark.parametrize("label,left,other,right", DUAL_IDENTITIES)
def test_known_solid_identities(label, left, other, right):
    """구성이 옳다는 증거. 회전 불변량으로 비교한다."""
    assert signature(left()) == signature(right())


@pytest.mark.parametrize("n", [3, 4, 5, 6, 8, 12])
def test_bipyramid_has_equal_dihedral_angles(n):
    """균등 각기둥의 쌍대가 곧 이면각 등가 쌍뿔이다.

        균등기둥 쌍대  s^2 = 1/(1 + sin^2(pi/n))
        이면각 등가    s^2 = 2/(3 - cos(2pi/n))     같은 값
    """
    axes = list(S.bipyramid(n))
    top, bottom = axes[:n], axes[n:]
    side_to_side = angle(top[0].normal, top[1].normal)
    across_equator = angle(top[0].normal, bottom[0].normal)
    assert side_to_side == pytest.approx(across_equator)


@pytest.mark.parametrize("n", [3, 4, 5, 6, 8, 12])
def test_trapezohedron_has_equal_dihedral_angles(n):
    """균등 엇각기둥의 쌍대가 곧 이면각 등가 사다리꼴다면체다.

        균등엇각기둥 쌍대  s^2 = 1/(1 + sin^2(pi/n) - sin^2(pi/2n))
        이면각 등가        s^2 = 2/(2 + cos(pi/n) - cos(2pi/n))     같은 값
    """
    axes = list(S.trapezohedron(n))
    top, bottom = axes[:n], axes[n:]
    side_to_side = angle(top[0].normal, top[1].normal)
    across = min(angle(top[0].normal, b.normal) for b in bottom)
    assert side_to_side == pytest.approx(across)


@pytest.mark.parametrize("n", [3, 5, 7])
def test_prism_caps_are_on_the_main_axis(n):
    aset = list(S.prism(n))
    assert np.allclose(aset[n].normal, (0, 0, 1))
    assert np.allclose(aset[n + 1].normal, (0, 0, -1))
    for side in aset[:n]:
        assert float(side.normal[2]) == pytest.approx(0.0, abs=1e-12)


@pytest.mark.parametrize("n", [3, 4, 5])
def test_antiprism_side_faces_are_equilateral(n):
    """옆면이 정삼각형이 되도록 높이를 잡는다."""
    top, bottom = S._antiprism_vertices(n)
    top = [np.array(v) for v in top]
    bottom = [np.array(v) for v in bottom]
    within = float(np.linalg.norm(top[0] - top[1 % n]))
    between = float(np.linalg.norm(top[0] - bottom[0]))
    assert within == pytest.approx(between)


# ---- 직접 만들기 --------------------------------------------------------


def test_from_normals_numbers_axes_with_a_prefix():
    aset = S.from_normals("custom", [(1, 0, 0), (0, 1, 0)], "x")
    assert [a.id for a in aset] == ["x0", "x1"]
    assert aset.cut == "custom"


def test_from_orbit_validates_the_seed():
    with pytest.raises(ValueError, match="궤도 크기"):
        S.from_orbit("bad", (1, 1, 1), "O", 6, "q")


def test_extra_turns_can_be_supplied_per_solid():
    aset = S.cube(turns=(45.0,))
    assert all(a.extra_turn_angles == (45.0,) for a in aset)


# ---- 카탈란 다면체 -------------------------------------------------------
#
# 씨앗은 쌍대 아르키메데스 다면체의 꼭짓점 방향이다. 궤도 크기가 면 개수와
# 맞는지로 씨앗이 자동 검증된다.

CATALAN_COUNTS = [
    ("triakis_tetrahedron", 12, "kt", "Td"),
    ("rhombic_dodecahedron", 12, "rd", "Oh"),
    ("triakis_octahedron", 24, "ko", "Oh"),
    ("tetrakis_hexahedron", 24, "th", "Oh"),
    ("deltoidal_icositetrahedron", 24, "di", "Oh"),
    ("disdyakis_dodecahedron", 48, "dd", "Oh"),
    ("pentagonal_icositetrahedron", 24, "pi", "O"),
    ("rhombic_triacontahedron", 30, "rt", "Ih"),
    ("triakis_icosahedron", 60, "ki", "Ih"),
    ("pentakis_dodecahedron", 60, "pd", "Ih"),
    ("deltoidal_hexecontahedron", 60, "dh", "Ih"),
    ("disdyakis_triacontahedron", 120, "dt", "Ih"),
    ("pentagonal_hexecontahedron", 60, "ph", "I"),
]


def test_all_thirteen_catalan_solids_are_present():
    assert len(S.CATALAN) == 13
    assert {k for k, _, _, _ in CATALAN_COUNTS} == set(S.CATALAN)


@pytest.mark.parametrize("key,count,prefix,group", CATALAN_COUNTS)
def test_catalan_face_count_and_names(key, count, prefix, group):
    aset = S.CATALAN[key]()
    assert len(aset) == count
    assert [a.id for a in aset] == [f"{prefix}{i}" for i in range(count)]
    assert all(float(np.linalg.norm(a.normal)) == pytest.approx(1.0) for a in aset)


@pytest.mark.parametrize("key,count,prefix,group", CATALAN_COUNTS)
def test_catalan_is_face_transitive(key, count, prefix, group):
    """카탈란은 면추이적이다. 모든 축에서 본 사잇각 분포가 같아야 한다."""
    axes = list(S.CATALAN[key]())
    profiles = {
        tuple(sorted(round(angle(a.normal, b.normal), 5) for b in axes if b.id != a.id))
        for a in axes
    }
    assert len(profiles) == 1


@pytest.mark.parametrize("key,count,prefix,group", CATALAN_COUNTS)
def test_catalan_orbit_is_closed_under_its_group(key, count, prefix, group):
    from cutpattern.geometry.symmetry import rotation_group

    normals = [a.normal for a in S.CATALAN[key]()]
    for m in rotation_group(group):
        for v in normals:
            w = m @ v
            assert any(float(np.linalg.norm(w - u)) < 1e-9 for u in normals)


def test_chiral_catalans_use_the_rotation_group_only():
    """손대칭 입체는 반사를 넣으면 반대 손까지 생긴다. O, I 만 써야 한다."""
    from cutpattern.geometry.symmetry import orbit

    seed = S._CATALAN_SEEDS["pentagonal_icositetrahedron"][0]
    assert len(orbit(seed, "O")) == 24
    assert len(orbit(seed, "Oh")) == 48  # 반사를 넣으면 두 배가 된다


def test_large_catalans_need_the_full_group():
    """120면은 |I| = 60 으로는 한 궤도에서 나올 수 없다."""
    from cutpattern.geometry.symmetry import orbit

    seed = S._CATALAN_SEEDS["disdyakis_triacontahedron"][0]
    assert len(orbit(seed, "Ih")) == 120
    assert len(orbit(seed, "I")) == 60


def test_rhombic_dodecahedron_matches_cube_edge_directions():
    from cutpattern.dsl import cube_edges

    assert signature(S.rhombic_dodecahedron()) == signature(cube_edges())


def test_octahedron_matches_cube_vertex_directions():
    from cutpattern.dsl import cube_vertices

    assert signature(S.octahedron()) == signature(cube_vertices())


def test_archimedean_direction_sets_come_from_merge():
    """아르키메데스 13개 중 11개는 플라톤/카탈란 방향집합의 합집합이다."""
    from cutpattern.axisops import merge

    cuboctahedron = merge("cubocta", S.cube(), S.octahedron())
    assert len(cuboctahedron) == 14
    rhombicuboctahedron = merge(
        "rco", S.cube(), S.octahedron(), S.rhombic_dodecahedron()
    )
    assert len(rhombicuboctahedron) == 26


def test_catalan_seed_errors_are_caught_by_the_orbit_size():
    with pytest.raises(ValueError, match="궤도 크기"):
        S.from_orbit("bad", (1, 1, 3), "Oh", 12, "q")


def test_pentagonal_icositetrahedron_groups_by_cube_symmetry():
    """네 예시. 24개 축이 정육면체 면 6개마다 4개씩 나뉜다."""
    from cutpattern.query import group_by_nearest

    groups = group_by_nearest(S.pentagonal_icositetrahedron(), S.cube())
    assert len(groups) == 6
    assert sorted(len(v) for v in groups.values()) == [4] * 6
