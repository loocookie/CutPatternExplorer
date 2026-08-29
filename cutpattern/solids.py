"""표준 입체의 면 법선으로 만드는 축 집합. 설계 문서 §2.1, §2.2.

축 집합은 항상 **면 기준**이다. 정다면체와 카탈란 다면체는 면추이적이라 면
법선 전체가 대칭군 아래 씨앗 하나의 궤도다 (`geometry.symmetry.orbit`).
그래서 좌표표 대신 씨앗과 군만 적으면 되고, 궤도 크기가 면 개수와 맞는지로
자동 검증된다.

각기둥 계열은 대칭군이 다르므로 순환군으로 옆면을, 주축으로 밑면을 만든다.

축 이름
-------
관례 이름(U, R, F, ...)을 쓰지 않는다. merge 하면 충돌하고, rotate 하면 U 가
더 이상 위가 아니어서 뜻을 잃기 때문이다. 대신 **출처 접두사 + 번호**를 준다.

    cube()          c0 .. c5
    octahedron()    o0 .. o7
    merge 후에도    c0 .. c5, o0 .. o7   충돌 없음

회전해도 접두사가 남아 편집기에서 출처가 보인다. 바꾸고 싶으면 rename 한다.
"""

from __future__ import annotations

import math

from .geometry.symmetry import cyclic_group, orbit
from .geometry.vector import Vec3, cross, normalize

__all__ = [
    "PHI",
    "from_normals",
    "from_orbit",
    "tetrahedron",
    "cube",
    "octahedron",
    "dodecahedron",
    "icosahedron",
    "prism",
    "antiprism",
    "bipyramid",
    "trapezohedron",
    "triakis_tetrahedron",
    "rhombic_dodecahedron",
    "triakis_octahedron",
    "tetrakis_hexahedron",
    "deltoidal_icositetrahedron",
    "disdyakis_dodecahedron",
    "pentagonal_icositetrahedron",
    "rhombic_triacontahedron",
    "triakis_icosahedron",
    "pentakis_dodecahedron",
    "deltoidal_hexecontahedron",
    "disdyakis_triacontahedron",
    "pentagonal_hexecontahedron",
    "PLATONIC",
    "CATALAN",
    "PRISM_FAMILY",
]

PHI = (1.0 + math.sqrt(5.0)) / 2.0          # 황금비
DELTA = 1.0 + math.sqrt(2.0)                # 백은비
TRIBONACCI = 1.8392867552141612             # t^3 = t^2 + t + 1


def _axis_set_cls():
    # dsl 이 solids 를 쓰고 solids 가 dsl.AxisSet 을 쓰므로 순환을 늦춘다
    from .dsl import AxisSet

    return AxisSet


def from_normals(id: str, normals, prefix: str, turns=(), name: str = ""):
    """법선 목록으로 축 집합을 만든다. 이름은 접두사 + 번호."""
    AxisSet = _axis_set_cls()
    s = AxisSet(id, extra_turns=tuple(turns), name=name or id)
    for i, n in enumerate(normals):
        s.add(f"{prefix}{i}", normalize(n))
    return s


def from_orbit(id: str, seed, group, expected: int, prefix: str, turns=(), name: str = ""):
    """씨앗과 대칭군의 궤도로 축 집합을 만든다.

    expected 로 궤도 크기를 검증한다. 씨앗이 대칭축 위에 얹히는 등 잘못되면
    궤도가 작아지므로 바로 잡힌다.
    """
    return from_normals(id, orbit(seed, group, expected=expected), prefix, turns, name)


# ------------------------------------------------------------ 정다면체

# 면추이적이므로 씨앗 하나의 궤도. 궤도 크기 = |군| / |안정자|.
#   |T|=12, |O|=24, |I|=60
#
# 회전각은 여기서 정하지 않는다. 절단 각도에 따라 달라지므로
# engine.turns.derived_turns 가 유도한다 (§7). turns 인자는 유도가 못 찾는 각을
# 명시하는 자리일 뿐이다.


def tetrahedron(id: str = "tetra", turns=()):
    """정사면체 면축 4개. 반대 방향 축이 없는 대표 사례 (§2.2)."""
    return from_orbit(
        id, (1, 1, 1), "T", 4, "t", turns, name="정사면체 면축"
    )


def cube(id: str = "cube", turns=()):
    """정육면체 면축 6개."""
    return from_orbit(
        id, (1, 0, 0), "O", 6, "c", turns, name="정육면체 면축"
    )


def octahedron(id: str = "octa", turns=()):
    """정팔면체 면축 8개. 정육면체의 꼭짓점 방향과 같다."""
    return from_orbit(
        id, (1, 1, 1), "O", 8, "o", turns, name="정팔면체 면축"
    )


def dodecahedron(id: str = "dodeca", turns=()):
    """정십이면체 면축 12개."""
    return from_orbit(
        id, (0, 1, PHI), "I", 12, "d", turns, name="정십이면체 면축"
    )


def icosahedron(id: str = "icosa", turns=()):
    """정이십면체 면축 20개. 정십이면체의 꼭짓점 방향과 같다."""
    return from_orbit(
        id, (1, 1, 1), "I", 20, "i", turns, name="정이십면체 면축"
    )


PLATONIC = {
    "tetrahedron": tetrahedron,
    "cube": cube,
    "octahedron": octahedron,
    "dodecahedron": dodecahedron,
    "icosahedron": icosahedron,
}


# ------------------------------------------------------------ 카탈란 다면체
#
# 카탈란은 아르키메데스의 쌍대다. 따라서 카탈란의 **면 법선**은 쌍대 아르키메데스
# 다면체의 **꼭짓점 방향**이고, 그것이 씨앗이다. 크기는 정규화로 사라진다.
#
# 군 선택이 중요하다.
#   - 면이 |회전군| 을 넘으면 회전군만으로는 한 궤도가 안 나온다.
#     마름모삼십면체 계열 120면에는 Ih(120) 가 필요하다.
#   - 반대로 손대칭 입체(깎은육팔면체, 깎은십이이십면체의 쌍대)는 반사를 넣으면
#     반대 손까지 생기므로 회전군 O, I 만 쓴다.
#
# 씨앗은 전부 궤도 크기로 검증된다. 틀리면 from_orbit 이 즉시 거부한다.

_CATALAN_SEEDS = {
    #                                    씨앗                          군     면   접두사  쌍대 아르키메데스
    "triakis_tetrahedron":         ((1, 1, 3),                        "Td",  12, "kt", "깎은정사면체"),
    "rhombic_dodecahedron":        ((1, 1, 0),                        "Oh",  12, "rd", "육팔면체"),
    "triakis_octahedron":          ((1, DELTA, DELTA),                "Oh",  24, "ko", "깎은정육면체"),
    "tetrakis_hexahedron":         ((0, 1, 2),                        "Oh",  24, "th", "깎은정팔면체"),
    "deltoidal_icositetrahedron":  ((DELTA, 1, 1),                    "Oh",  24, "di", "마름모육팔면체"),
    "disdyakis_dodecahedron":      ((1, DELTA, 1 + 2 * math.sqrt(2)), "Oh",  48, "dd", "깎은육팔면체"),
    "pentagonal_icositetrahedron": ((1, 1 / TRIBONACCI, TRIBONACCI),  "O",   24, "pi", "다듬은육면체"),
    "rhombic_triacontahedron":     ((0, 0, PHI),                      "Ih",  30, "rt", "십이이십면체"),
    "triakis_icosahedron":         ((0, 1 / PHI, 2 + PHI),            "Ih",  60, "ki", "깎은정십이면체"),
    "pentakis_dodecahedron":       ((0, 1, 3 * PHI),                  "Ih",  60, "pd", "깎은정이십면체"),
    "deltoidal_hexecontahedron":   ((1, 1, PHI**3),                   "Ih",  60, "dh", "마름모십이이십면체"),
    "disdyakis_triacontahedron":   ((1, 1, 1 + 4 * PHI),              "Ih", 120, "dt", "깎은십이이십면체"),
    # 다듬은십이면체의 표준 좌표 중 하나. 한쪽 손대칭만 만든다
    "pentagonal_hexecontahedron":  ((-0.66184204946, 0.74964331623, 4.19410767050),
                                                                      "I",   60, "ph", "다듬은십이면체"),
}


def _make_catalan(key: str):
    seed, group, count, prefix, dual = _CATALAN_SEEDS[key]
    korean = {
        "triakis_tetrahedron": "삼각사면체",
        "rhombic_dodecahedron": "마름모십이면체",
        "triakis_octahedron": "삼각팔면체",
        "tetrakis_hexahedron": "사각육면체",
        "deltoidal_icositetrahedron": "연꼴이십사면체",
        "disdyakis_dodecahedron": "육각팔면체",
        "pentagonal_icositetrahedron": "오각이십사면체",
        "rhombic_triacontahedron": "마름모삼십면체",
        "triakis_icosahedron": "삼각이십면체",
        "pentakis_dodecahedron": "오각십이면체",
        "deltoidal_hexecontahedron": "연꼴육십면체",
        "disdyakis_triacontahedron": "육각십면체",
        "pentagonal_hexecontahedron": "오각육십면체",
    }[key]

    def factory(id: str = key, turns=()):
        return from_orbit(
            id, seed, group, count, prefix, turns, name=f"{korean} 면축 ({dual} 쌍대)"
        )

    factory.__name__ = key
    factory.__doc__ = (
        f"{korean} 면축 {count}개. {dual}의 쌍대. "
        f"씨앗 {tuple(round(float(v), 6) for v in seed)}, 군 {group}, 궤도 {count}"
    )
    return factory


triakis_tetrahedron = _make_catalan("triakis_tetrahedron")
rhombic_dodecahedron = _make_catalan("rhombic_dodecahedron")
triakis_octahedron = _make_catalan("triakis_octahedron")
tetrakis_hexahedron = _make_catalan("tetrakis_hexahedron")
deltoidal_icositetrahedron = _make_catalan("deltoidal_icositetrahedron")
disdyakis_dodecahedron = _make_catalan("disdyakis_dodecahedron")
pentagonal_icositetrahedron = _make_catalan("pentagonal_icositetrahedron")
rhombic_triacontahedron = _make_catalan("rhombic_triacontahedron")
triakis_icosahedron = _make_catalan("triakis_icosahedron")
pentakis_dodecahedron = _make_catalan("pentakis_dodecahedron")
deltoidal_hexecontahedron = _make_catalan("deltoidal_hexecontahedron")
disdyakis_triacontahedron = _make_catalan("disdyakis_triacontahedron")
pentagonal_hexecontahedron = _make_catalan("pentagonal_hexecontahedron")

CATALAN = {key: globals()[key] for key in _CATALAN_SEEDS}


# ---------------------------------------------------------- 각기둥 계열
#
# 주축을 +z 로 둔다. 정다면체와 달리 면추이적이 아니므로 옆면과 밑면의 회전각이
# 서로 다르다. 그 차이는 유도로 나온다 (engine.turns).
#
# 네 입체를 **꼭짓점 좌표 하나에서** 모두 만든다. 그래야 쌍대 관계가 방향까지
# 정렬된다. 기둥의 꼭짓점 방향이 곧 쌍뿔의 면 방향이다.


def _prism_vertices(n: int):
    """옆면이 정사각형인 n각기둥의 꼭짓점. 외접원 반지름 1."""
    h = math.sin(math.pi / n)
    top = [
        (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), h)
        for i in range(n)
    ]
    bottom = [(x, y, -z) for x, y, z in top]
    return top, bottom


def _antiprism_vertices(n: int):
    """옆면이 정삼각형인 n각엇각기둥의 꼭짓점. 아래 띠가 180/n 도 어긋난다."""
    h = math.sqrt(
        max(0.0, math.sin(math.pi / n) ** 2 - math.sin(math.pi / (2 * n)) ** 2)
    )
    half = math.pi / n
    top = [
        (math.cos(2 * math.pi * i / n), math.sin(2 * math.pi * i / n), h)
        for i in range(n)
    ]
    bottom = [
        (
            math.cos(2 * math.pi * i / n + half),
            math.sin(2 * math.pi * i / n + half),
            -h,
        )
        for i in range(n)
    ]
    return top, bottom


def _face_normal(v1, v2, v3) -> Vec3:
    """세 꼭짓점이 이루는 면의 바깥쪽 법선."""
    a, b, c = Vec3(v1), Vec3(v2), Vec3(v3)
    n = cross(b - a, c - a)
    if (n @ (a + b + c)) < 0.0:
        n = -n
    return normalize(n)


def prism(n: int, id: str | None = None, turns=()):
    """n각기둥 면축 n + 2 개. 옆면 n 개와 밑면 2 개.

    옆면 법선은 이웃한 두 꼭짓점의 중간 방위각을 향한다.
    """
    if n < 3:
        raise ValueError(f"각기둥은 n >= 3 이어야 한다 (받은 값: {n})")
    id = id or f"prism{n}"
    AxisSet = _axis_set_cls()
    s = AxisSet(id, extra_turns=tuple(turns), name=f"{n}각기둥 면축")
    half = math.pi / n
    for i in range(n):
        phi = 2 * math.pi * i / n + half
        s.add(f"p{i}", (math.cos(phi), math.sin(phi), 0.0))
    s.add(f"p{n}", (0, 0, 1))
    s.add(f"p{n + 1}", (0, 0, -1))
    return s


def antiprism(n: int, id: str | None = None, turns=()):
    """n각엇각기둥 면축 2n + 2 개. 옆면 정삼각형 2n 개와 밑면 2 개.

    옆면 법선은 삼각형 평면에서 직접 구한다. n=3 이면 정팔면체와 같아진다.
    """
    if n < 3:
        raise ValueError(f"엇각기둥은 n >= 3 이어야 한다 (받은 값: {n})")
    id = id or f"antiprism{n}"
    AxisSet = _axis_set_cls()
    s = AxisSet(id, extra_turns=tuple(turns), name=f"{n}각엇각기둥 면축")
    top, bottom = _antiprism_vertices(n)
    k = 0
    for i in range(n):
        # 위 두 꼭짓점 + 아래 하나
        s.add(f"a{k}", _face_normal(top[i], top[(i + 1) % n], bottom[i]))
        k += 1
        # 아래 두 꼭짓점 + 위 하나
        s.add(f"a{k}", _face_normal(bottom[i], bottom[(i + 1) % n], top[(i + 1) % n]))
        k += 1
    s.add(f"a{k}", (0, 0, 1))
    s.add(f"a{k + 1}", (0, 0, -1))
    return s


def bipyramid(n: int, id: str | None = None, turns=()):
    """n각쌍뿔 면축 2n 개. n각기둥의 쌍대.

    면 법선은 기둥의 꼭짓점 방향이다. n=4 면 정팔면체와 같아진다.
    """
    if n < 3:
        raise ValueError(f"쌍뿔은 n >= 3 이어야 한다 (받은 값: {n})")
    id = id or f"bipyramid{n}"
    top, bottom = _prism_vertices(n)
    return from_normals(id, list(top) + list(bottom), "b", turns, f"{n}각쌍뿔 면축")


def trapezohedron(n: int, id: str | None = None, turns=()):
    """n각 사다리꼴다면체 면축 2n 개. n각엇각기둥의 쌍대.

    면 법선은 엇각기둥의 꼭짓점 방향이다. n=3 이면 정육면체와 같아진다.
    """
    if n < 3:
        raise ValueError(f"사다리꼴다면체는 n >= 3 이어야 한다 (받은 값: {n})")
    id = id or f"trapezo{n}"
    top, bottom = _antiprism_vertices(n)
    return from_normals(
        id, list(top) + list(bottom), "z", turns, f"{n}각 사다리꼴다면체 면축"
    )


PRISM_FAMILY = {
    "prism": prism,
    "antiprism": antiprism,
    "bipyramid": bipyramid,
    "trapezohedron": trapezohedron,
}
