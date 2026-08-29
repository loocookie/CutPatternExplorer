"""축 집합 조작. 설계 문서 §2.1, §2.2.

전부 **새 축 집합을 돌려준다**. 원본은 건드리지 않으므로 합성해 쓸 수 있다.

    merge("both", cube(), rotate(cube(), axis=(1, 1, 1), angle=180))

아르키메데스 다면체 대부분은 플라톤/카탈란 방향집합의 합집합이라 merge 로 나온다.

    cuboctahedron        = merge(cube(), octahedron())
    rhombicuboctahedron  = merge(cube(), octahedron(), rhombic_dodecahedron())

예외는 깎은육팔면체와 깎은십이이십면체 두 개뿐이고, 그건 손대칭 궤도라
orbit 으로 직접 만든다.
"""

from __future__ import annotations

import math

from .geometry.vector import (
    Mat3,
    Vec3,
    as_vec,
    clamp,
    cross,
    norm,
    normalize,
    rotation_matrix,
)

__all__ = [
    "MERGE_TOL",
    "merge",
    "rotate",
    "mirror",
    "invert",
    "same_directions",
    "remove",
    "keep",
    "rename",
    "rotation_from_pairs",
    "quaternion_matrix",
]

# 같은 방향으로 볼 허용 오차. 회전을 여러 번 합성해도 남을 만큼 넉넉하게.
MERGE_TOL = 1e-7


def _axis_set_cls():
    from .dsl import AxisSet

    return AxisSet


def _new_like(id: str, name: str, template):
    AxisSet = _axis_set_cls()
    return AxisSet(id, extra_turns=template.extra_turns, name=name)


def _same_direction(a, b, tol: float = MERGE_TOL) -> bool:
    d0, d1, d2 = a[0] - b[0], a[1] - b[1], a[2] - b[2]
    return math.sqrt(d0 * d0 + d1 * d1 + d2 * d2) < tol


# ------------------------------------------------------------------ merge


def merge(id: str, *sets, name: str = "", tol: float = MERGE_TOL):
    """축 집합 여러 개를 하나로 합친다.

    같은 방향이 겹치면 **먼저 온 쪽만 남긴다**. 축 id 는 그대로 물려받으므로
    출처를 알 수 있다. 접두사가 겹쳐 id 가 충돌하면 뒤에 오는 쪽에 꼬리표를
    붙인다.
    """
    if not sets:
        raise ValueError("합칠 축 집합이 없다")
    out = _new_like(id, name or f"merged({', '.join(s.id for s in sets)})", sets[0])
    seen: list[Vec3] = []
    used: set[str] = set()
    for source in sets:
        for axis in source:
            if any(_same_direction(axis.normal, v, tol) for v in seen):
                continue  # 같은 방향은 한 번만
            seen.append(axis.normal)
            axis_id = axis.id
            suffix = 1
            while axis_id in used:
                axis_id = f"{axis.id}_{suffix}"
                suffix += 1
            used.add(axis_id)
            out.add(axis_id, axis.normal, extra_turns=axis.extra_turn_angles)
    return out


# ----------------------------------------------------------------- rotate


def quaternion_matrix(q) -> Mat3:
    """쿼터니언 (w, x, y, z) -> 3x3 회전행렬."""
    w, x, y, z = (float(v) for v in q)
    norm = math.sqrt(w * w + x * x + y * y + z * z)
    if norm < 1e-12:
        raise ValueError("영 쿼터니언은 회전이 아니다")
    w, x, y, z = w / norm, x / norm, y / norm, z / norm
    return Mat3(
        (
            (1 - 2 * (y * y + z * z), 2 * (x * y - w * z), 2 * (x * z + w * y)),
            (2 * (x * y + w * z), 1 - 2 * (x * x + z * z), 2 * (y * z - w * x)),
            (2 * (x * z - w * y), 2 * (y * z + w * x), 1 - 2 * (x * x + y * y)),
        )
    )


def _frame(a, b) -> Mat3:
    """a 와 b 로 정규직교틀을 만든다. 열이 기저벡터다."""
    e1 = normalize(a)
    rest = Vec3(b) - (e1 @ b) * e1
    length = norm(rest)
    if length < 1e-9:
        raise ValueError("두 방향이 평행해 회전이 하나로 정해지지 않는다")
    e2 = rest / length
    e3 = cross(e1, e2)
    # 열이 기저이므로 행 표현에서는 성분을 가로로 늘어놓는다
    return Mat3(((e1[i], e2[i], e3[i]) for i in range(3)))


def rotation_from_pairs(pairs) -> Mat3:
    """(a -> a'), (b -> b') 두 쌍으로 회전을 정한다.

    사잇각이 보존되지 않으면 그런 회전은 존재하지 않는다. 조용히 근사하지 않고
    거부한다.
    """
    if len(pairs) != 2:
        raise ValueError(f"쌍이 정확히 두 개여야 한다 (받은 개수: {len(pairs)})")
    (a, a2), (b, b2) = ((normalize(x), normalize(y)) for x, y in pairs)
    before = math.degrees(math.acos(clamp(a @ b)))
    after = math.degrees(math.acos(clamp(a2 @ b2)))
    if abs(before - after) > 1e-6:
        raise ValueError(
            f"사잇각이 보존되지 않는다: {before:.6f}도 -> {after:.6f}도. "
            "그런 회전은 존재하지 않는다"
        )
    return _frame(a2, b2) @ _frame(a, b).T


def rotate(
    aset,
    *,
    axis=None,
    angle: float | None = None,
    pairs=None,
    quaternion=None,
    id: str | None = None,
    name: str = "",
):
    """축 집합 전체를 회전한다. 세 형식 중 하나를 쓴다.

        rotate(s, axis=(1, 1, 1), angle=180)          축과 각
        rotate(s, pairs=[(a, a2), (b, b2)])           두 쌍의 대응
        rotate(s, quaternion=(w, x, y, z))            쿼터니언

    축 id 는 그대로 둔다. 회전해도 출처가 보여야 하기 때문이다.
    """
    given = [axis is not None, pairs is not None, quaternion is not None]
    if sum(given) != 1:
        raise ValueError("axis+angle, pairs, quaternion 중 정확히 하나를 준다")

    if axis is not None:
        if angle is None:
            raise ValueError("axis 를 주면 angle 도 줘야 한다")
        matrix = rotation_matrix(as_vec(axis), math.radians(float(angle)))
    elif pairs is not None:
        matrix = rotation_from_pairs(pairs)
    else:
        matrix = quaternion_matrix(quaternion)

    out = _new_like(id or aset.id, name or aset.name, aset)
    for a in aset:
        out.add(a.id, matrix @ a.normal, extra_turns=a.extra_turn_angles)
    return out


# ------------------------------------------------------ mirror / invert
#
# 반사는 det = -1 이라 회전이 아니다. rotate 로는 만들 수 없다.
#
# 카탈란 13종 중 오각이십사면체와 오각육십면체 둘만 손대칭이다. 나머지는
# 거울상이 자기 자신과 (회전을 허용하면) 같으므로 mirror 를 걸어도 새 입체가
# 나오지 않는다. 손대칭 여부는 궤도 크기로 확인된다.
#
#     orbit(pi_seed, "O")  -> 24        회전군만
#     orbit(pi_seed, "Oh") -> 48        반사를 넣으면 두 손이 모두 생긴다


def mirror(aset, normal=(0, 0, 1), *, id: str | None = None, name: str = ""):
    """원점을 지나고 `normal` 을 법선으로 하는 평면에 대해 반사한다.

    손대칭 입체의 반대 손을 만드는 데 쓴다.

        left  = pentagonal_icositetrahedron()
        right = mirror(left, (0, 0, 1), id="pi_right")
    """
    n = normalize(normal)
    # 반사 행렬 I - 2 n n^T
    matrix = Mat3(
        (
            ((1.0 if i == j else 0.0) - 2.0 * n[i] * n[j] for j in range(3))
            for i in range(3)
        )
    )
    out = _new_like(id or aset.id, name or aset.name, aset)
    for a in aset:
        out.add(a.id, matrix @ a.normal, extra_turns=a.extra_turn_angles)
    return out


def invert(aset, *, id: str | None = None, name: str = ""):
    """원점 반전. 모든 축을 반대 방향으로 보낸다.

    반전도 det = -1 이라 손대칭을 뒤집는다. 중심대칭 입체(정육면체 등)에서는
    방향집합이 그대로다.
    """
    out = _new_like(id or aset.id, name or aset.name, aset)
    for a in aset:
        out.add(a.id, -a.normal, extra_turns=a.extra_turn_angles)
    return out


def same_directions(a, b, tol: float = MERGE_TOL) -> bool:
    """두 축 집합이 같은 방향집합인가. 순서와 이름은 보지 않는다.

    놓인 방향까지 같아야 참이다. 회전을 허용한 비교가 필요하면 축 쌍 사잇각
    다중집합 같은 회전 불변량을 쓴다.
    """
    left = [x.normal for x in a]
    right = [y.normal for y in b]
    if len(left) != len(right):
        return False
    return all(any(_same_direction(x, y, tol) for y in right) for x in left)


# ------------------------------------------------------- remove / keep


def _ids(axes) -> set[str]:
    out = set()
    for a in axes:
        out.add(a if isinstance(a, str) else a.id)
    return out


def remove(aset, *axes, id: str | None = None, name: str = ""):
    """지정한 축을 뺀 집합. merge 뒤 정리에 쓴다."""
    drop = _ids(axes)
    unknown = drop - {a.id for a in aset}
    if unknown:
        raise KeyError(f"없는 축: {sorted(unknown)} (집합 {aset.id!r})")
    out = _new_like(id or aset.id, name or aset.name, aset)
    for a in aset:
        if a.id not in drop:
            out.add(a.id, a.normal, extra_turns=a.extra_turn_angles)
    return out


def keep(aset, *axes, id: str | None = None, name: str = ""):
    """지정한 축만 남긴 집합."""
    wanted = _ids(axes)
    unknown = wanted - {a.id for a in aset}
    if unknown:
        raise KeyError(f"없는 축: {sorted(unknown)} (집합 {aset.id!r})")
    out = _new_like(id or aset.id, name or aset.name, aset)
    for a in aset:
        if a.id in wanted:
            out.add(a.id, a.normal, extra_turns=a.extra_turn_angles)
    return out


def rename(aset, mapping: dict[str, str], id: str | None = None):
    """축 id 를 바꾼다. 자동 번호가 마음에 들지 않을 때 쓴다."""
    unknown = set(mapping) - {a.id for a in aset}
    if unknown:
        raise KeyError(f"없는 축: {sorted(unknown)} (집합 {aset.id!r})")
    out = _new_like(id or aset.id, aset.name, aset)
    for a in aset:
        out.add(mapping.get(a.id, a.id), a.normal, extra_turns=a.extra_turn_angles)
    return out
