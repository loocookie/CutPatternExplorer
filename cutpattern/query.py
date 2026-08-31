"""축 질의. 설계 문서 §2.1.

축 집합의 메서드가 아니라 **자유 함수**다. 분류는 본질적으로 집합 사이 연산이기
때문이다. 오각이십사면체의 축 24개를 정육면체 대칭으로 6군으로 나누는 것 같은
질문은 한 집합 안에서 답할 수 없다.

질의는 at_angle 하나로 충분하다. 수직(90), 반대(180), 자기 자신(0) 이 전부 그
특수한 경우이고, 입체에 따라 수직인 축이나 반대 축이 아예 없을 수도 있다.
자주 쓰는 조합은 파이썬 함수로 묶으면 된다.

    adjacent = lambda x: at_angle(x, 90, faces)
"""

from __future__ import annotations

import math
from collections import defaultdict

from .engine.axes import Axis
from .geometry.vector import Vec3, as_vec, clamp, normalize

__all__ = [
    "ANGLE_TOL_DEG",
    "angle_between",
    "at_angle",
    "angles_from",
    "group_by_nearest",
    "nearest",
    "axes_of",
]

# 축 사이 각 판정 허용 오차(도).
# acos 는 인자가 +-1 근처에서 오차를 sqrt(eps) ~ 1e-8 rad 까지 키우므로
# 수치 잡음보다는 넉넉하게, 실제로 구분되는 축 사이 각보다는 훨씬 작게 잡는다.
ANGLE_TOL_DEG = 1e-4


def _normal(x) -> Vec3:
    """축이든 벡터든 단위 법선으로."""
    if isinstance(x, Axis):
        return x.normal
    return normalize(as_vec(x))


def axes_of(*targets) -> list[Axis]:
    """축 집합과 축이 섞인 인자를 축 목록으로 편다.

    중첩을 끝까지 편다. 질의는 목록을 돌려주고 목록끼리 묶는 일이 흔한데,
    그때마다 ``*`` 를 붙이거나 for 문을 쓰게 하고 싶지 않다.

        axes_of(faces)                          집합
        axes_of(faces.c0, faces.c1)             축 여러 개
        axes_of(at_angle(x, 90, faces))         질의 결과 목록
        axes_of([at_angle(x, 90, faces), y])    섞어서, 중첩해서
    """
    out: list[Axis] = []
    for target in targets:
        if isinstance(target, Axis):
            out.append(target)
        elif isinstance(target, (str, bytes)):
            raise TypeError(f"not an axis set or an axis: {target!r}")
        elif hasattr(target, "__iter__"):
            out.extend(axes_of(*target))
        else:
            raise TypeError(f"not an axis set or an axis: {target!r}")
    return out


def angle_between(a, b) -> float:
    """두 축 사이 각(도). 축 객체와 생벡터를 모두 받는다."""
    return math.degrees(math.acos(float(clamp(float(_normal(a) @ _normal(b))))))


def at_angle(reference, degrees: float, *targets, tol_deg: float = ANGLE_TOL_DEG):
    """기준에서 지정한 사잇각을 이루는 축들.

        at_angle(faces.c0, 90, faces)              같은 집합 안
        at_angle(faces.c0, 90, faces, edges)       여러 집합에 걸쳐
    """
    if not targets:
        raise TypeError("give the axis set to search: at_angle(reference, angle, axes)")
    ref = _normal(reference)
    return [
        a
        for a in axes_of(*targets)
        if abs(math.degrees(math.acos(float(clamp(float(a.normal @ ref))))) - degrees)
        <= tol_deg
    ]


def angles_from(reference, *targets, tol_deg: float = ANGLE_TOL_DEG):
    """기준에서 본 사잇각별로 축을 묶는다. {각: [축들]}.

    낯선 입체를 다룰 때 어떤 각이 존재하는지 먼저 보는 용도다. at_angle 에 넣을
    값을 여기서 찾는다.
    """
    if not targets:
        raise TypeError("give the axis set to search: angles_from(reference, axes)")
    ref = _normal(reference)
    buckets: dict[float, list[Axis]] = defaultdict(list)
    for a in axes_of(*targets):
        value = math.degrees(math.acos(float(clamp(float(a.normal @ ref)))))
        for key in buckets:
            if abs(key - value) <= tol_deg:
                buckets[key].append(a)
                break
        else:
            buckets[round(value, 9)].append(a)
    return dict(sorted(buckets.items()))


def nearest(reference, *targets) -> Axis:
    """기준에 가장 가까운 축 하나."""
    axes = axes_of(*targets)
    if not axes:
        raise ValueError("no target axes")
    ref = _normal(reference)
    return max(axes, key=lambda a: float(a.normal @ ref))


def group_by_nearest(source, reference) -> dict[str, list[Axis]]:
    """source 의 축들을 가장 가까운 reference 축으로 분류한다.

    대칭이 낮은 축 집합을 익숙한 대칭으로 읽을 때 쓴다.

        group_by_nearest(pentagonal_icositetrahedron(), cube())
        -> 정육면체 면 6개마다 4개씩
    """
    ref_axes = axes_of(reference)
    if not ref_axes:
        raise ValueError("the reference axis set is empty")
    groups: dict[str, list[Axis]] = {a.id: [] for a in ref_axes}
    for a in axes_of(source):
        best = max(ref_axes, key=lambda r: float(r.normal @ a.normal))
        groups[best.id].append(a)
    return groups
