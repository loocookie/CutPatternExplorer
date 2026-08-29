"""회전군과 궤도. 설계 문서 §2.1 축 집합 생성의 기반.

정다면체와 카탈란 다면체는 **면추이적(face-transitive)** 이다. 즉 면 법선 전체가
대칭군 아래 씨앗 벡터 하나의 궤도다. 그래서 좌표표를 손으로 넣는 대신

    orbit(seed, O)

한 줄로 축 집합이 나온다. 궤도 크기가 기대한 면 개수와 같은지로 씨앗이 맞는지
자동 검증된다.

회전군은 셋뿐이다.

    T   정사면체 회전군   12개
    O   정팔면체 회전군   24개   (정육면체와 공유)
    I   정이십면체 회전군 60개   (정십이면체와 공유)

각기둥 계열은 별도로 순환/이면체군을 쓴다.
"""

from __future__ import annotations

import math

from ..epsilon import NORMAL_EPS
from .vector import IDENTITY3, Mat3, Vec3, norm, rotation_matrix

__all__ = [
    "rotation_group",
    "cyclic_group",
    "dihedral_group",
    "orbit",
    "dedupe_directions",
    "GROUP_ORDERS",
]

# 회전군과, 반사를 포함한 전체군.
#   Td 는 T 에 반사면을 더한 것으로 반전 -I 를 포함하지 않는다.
#   Oh = O x {I, -I},  Ih = I x {I, -I} 이므로 반전을 생성원에 더하면 된다.
#
# 면 법선이 |회전군| 을 넘는 개수로 필요하면 (예: 마름모삼십면체 계열의 120면)
# 회전군만으로는 한 궤도에서 나올 수 없어 전체군이 필요하다. 반대로 손대칭
# 입체(깎은육팔면체 계열)는 반사를 넣으면 반대 손까지 생기므로 회전군만 쓴다.
GROUP_ORDERS = {"T": 12, "O": 24, "I": 60, "Td": 24, "Oh": 48, "Ih": 120}

# 방향이 같다고 볼 허용 오차. 군 원소를 곱해 쌓는 과정의 오차보다 넉넉하게.
_DIR_TOL = 1e-9


def _round_key(m: Mat3, decimals: int = 9) -> tuple:
    """행렬을 사전 키로. ``+ 0.0`` 은 -0.0 을 0.0 으로 접어 키를 안정시킨다."""
    return tuple(round(x, decimals) + 0.0 for row in m for x in row)


def _close_group(
    generators: list[Mat3], expected: int | None = None
) -> list[Mat3]:
    """생성원으로부터 군 전체를 닫는다. 폭 우선으로 곱해 나간다."""
    elements: dict[tuple, Mat3] = {}
    identity = IDENTITY3
    elements[_round_key(identity)] = identity
    frontier = [identity]
    while frontier:
        nxt = []
        for a in frontier:
            for g in generators:
                m = g @ a
                key = _round_key(m)
                if key not in elements:
                    elements[key] = m
                    nxt.append(m)
        frontier = nxt
        if len(elements) > 400:
            raise RuntimeError("군이 닫히지 않는다. 생성원을 확인하라")
    out = list(elements.values())
    if expected is not None and len(out) != expected:
        raise RuntimeError(f"군 크기가 {len(out)}, 기대값은 {expected}")
    return out


# 축 회전은 §4.2 의 것과 같은 Rodrigues 공식이다. 사본을 두지 않는다
_axis_rotation = rotation_matrix


_GROUP_CACHE: dict[str, list[Mat3]] = {}


def rotation_group(name: str) -> list[Mat3]:
    """대칭군의 원소를 3x3 행렬 목록으로 돌려준다.

    "T", "O", "I" 는 회전군이고 "Td", "Oh", "Ih" 는 반사를 포함한 전체군이다.
    """
    name = {"td": "Td", "oh": "Oh", "ih": "Ih"}.get(name.lower(), name.upper())
    if name in _GROUP_CACHE:
        return _GROUP_CACHE[name]
    if name not in GROUP_ORDERS:
        raise KeyError(
            f"모르는 대칭군: {name!r} ({', '.join(sorted(GROUP_ORDERS))} 중 하나)"
        )

    if name == "Td":
        # 정사면체 회전군 + 반사면. 반전은 포함하지 않는다
        gens = [
            _axis_rotation((0, 0, 1), math.pi),
            _axis_rotation((1, 1, 1), 2 * math.pi / 3),
            Mat3(((0.0, 1.0, 0.0), (1.0, 0.0, 0.0), (0.0, 0.0, 1.0))),  # x<->y 반사
        ]
    elif name in ("Oh", "Ih"):
        gens = list(rotation_group(name[0])) + [-IDENTITY3]
    elif name == "O":
        gens = [
            _axis_rotation((0, 0, 1), math.pi / 2),
            _axis_rotation((1, 1, 1), 2 * math.pi / 3),
        ]
    elif name == "T":
        gens = [
            _axis_rotation((0, 0, 1), math.pi),
            _axis_rotation((1, 1, 1), 2 * math.pi / 3),
        ]
    else:  # I
        phi = (1.0 + math.sqrt(5.0)) / 2.0
        gens = [
            _axis_rotation((0, 0, 1), math.pi),
            _axis_rotation((1, 1, 1), 2 * math.pi / 3),
            _axis_rotation((0, 1, phi), 2 * math.pi / 5),
        ]

    group = _close_group(gens, expected=GROUP_ORDERS[name])
    _GROUP_CACHE[name] = group
    return group


def cyclic_group(n: int, axis=(0, 0, 1)) -> list[Mat3]:
    """주축 둘레 n회 회전군. 각기둥 계열에 쓴다."""
    return [_axis_rotation(axis, 2 * math.pi * k / n) for k in range(n)]


def dihedral_group(n: int, axis=(0, 0, 1), flip_axis=(1, 0, 0)) -> list[Mat3]:
    """이면체 회전군 D_n. 주축 n회 + 수직축 2회. 크기 2n."""
    flip = _axis_rotation(flip_axis, math.pi)
    out = []
    for r in cyclic_group(n, axis):
        out.append(r)
        out.append(r @ flip)
    return out


def dedupe_directions(vectors, tol: float = _DIR_TOL) -> list[Vec3]:
    """같은 방향을 하나로 합친다. 반대 방향은 **다른** 방향으로 본다 (§2.2)."""
    out: list[Vec3] = []
    for v in vectors:
        v = Vec3(v)
        length = norm(v)
        if length < NORMAL_EPS:
            continue
        v = v / length
        if not any(norm(v - w) < tol for w in out):
            out.append(v)
    return out


def orbit(seed, group, expected: int | None = None) -> list[Vec3]:
    """씨앗 방향에 군을 전부 적용해 얻는 서로 다른 방향들.

    면추이 다면체의 면 법선 집합이 정확히 이것이다. `expected` 를 주면 궤도
    크기를 검증한다. 씨앗이 틀리면 (대칭축 위에 얹히는 등) 궤도가 작아지므로
    바로 잡힌다.
    """
    if isinstance(group, str):
        group = rotation_group(group)
    seed = Vec3(seed)
    length = norm(seed)
    if length < NORMAL_EPS:
        raise ValueError("씨앗이 영벡터다")
    seed = seed / length

    dirs = dedupe_directions(g @ seed for g in group)
    dirs.sort(key=lambda v: (round(-v[2], 9), round(math.atan2(v[1], v[0]), 9)))
    if expected is not None and len(dirs) != expected:
        raise ValueError(
            f"궤도 크기가 {len(dirs)}, 기대값은 {expected}. "
            f"씨앗 {tuple(round(x, 6) for x in seed)} 확인 필요"
        )
    return dirs
