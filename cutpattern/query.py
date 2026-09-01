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
from .epsilon import NORMAL_EPS
from .geometry.angular_coverage import TAU
from .geometry.vector import Vec3, as_vec, clamp, normalize, orthonormal_basis

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


# 간격을 비교하기 전에 붙일 격자. 사잇각 허용 오차(1e-4 도)보다 훨씬 촘촘하되
# 부동소수 잡음(~1e-15)보다는 굵다 (§2.6)
_GAP_GRID = 9


def _azimuths(ref, axes):
    """기준 축 둘레의 방위각. `(u, v, n)` 이 오른손계라 증가 방향이 반시계다."""
    u, v = orthonormal_basis(ref)
    return [math.atan2(float(a.normal @ v), float(a.normal @ u)) for a in axes]


def _start_azimuth(ref, start):
    """시작 방향의 방위각. 기준 축과 나란하면 사영이 0 이라 정의되지 않는다."""
    d = _normal(start)
    u, v = orthonormal_basis(ref)
    x, y = float(d @ u), float(d @ v)
    if math.hypot(x, y) < NORMAL_EPS:
        raise ValueError(
            "start is parallel to the reference axis, so it has no azimuth"
        )
    return math.atan2(y, x)


def _ordered_from(ref, axes, start):
    """`start` 의 방위각을 0 으로 놓고 반시계로 센다 (§2.6).

    방위각이 `start` 와 **정확히 같은** 축은 뺄셈 오차로 `(phi - start) % 2pi`
    가 0 이 아니라 2pi 바로 아래로 떨어져 맨 뒤로 밀릴 수 있다. 격자에 붙여
    그 자리를 0 으로 되돌린다.
    """
    base = _start_azimuth(ref, start)
    def offset(phi):
        d = round((phi - base) % TAU, _GAP_GRID)
        return 0.0 if abs(d - round(TAU, _GAP_GRID)) < 10 ** -_GAP_GRID else d
    return [a for _, a in sorted(
        zip(_azimuths(ref, axes), axes), key=lambda pair: (offset(pair[0]), pair[1].id)
    )]


def _canonical_ring(ref, axes):
    """고리를 반시계로 정렬하고, 회전 중 하나를 표준형으로 고른다 (§2.6).

    기준 축 `ref` 둘레의 방위각으로 정렬한다. `orthonormal_basis` 가 결정적이고
    `(u, v, n)` 이 오른손계이므로 (§4.2) `+n` 에서 볼 때 반시계다.

    정렬만으로는 부족하다. 시작점이 기저에 따라 달라지므로 같은 고리가 다른
    순서로 나온다. **이웃 간격 수열이 사전순으로 가장 작아지는 회전**을 고르면
    시작점이 사라진다 — 목걸이 표준형이다. 그러면 기하가 같은 두 고리가 같은
    순서로 나오고, 간격 수열을 그대로 비교할 수 있다.

    간격은 격자에 붙여 비교한다. 같아야 할 간격이 1e-15 씩 다르므로 (실측)
    생값으로 사전순 비교를 하면 그 잡음이 어느 회전이 최소인지를 뒤집는다.
    엡실론 비교는 전순서가 아니라 최소가 정의되지 않으므로 쓰지 않는다.

    거울상은 구분한다. 뒤집기까지 최소화하면 손대칭이 다른 두 고리가 같아진다
    (§2.5 의 키랄 카탈란 둘).
    """
    if len(axes) < 3:
        return list(axes)                     # 간격이 하나뿐이면 회전할 것이 없다
    ordered = [a for _, a in sorted(zip(_azimuths(ref, axes), axes),
                                    key=lambda pair: (pair[0], pair[1].id))]
    phi = _azimuths(ref, ordered)
    n = len(ordered)
    gaps = [round((phi[(i + 1) % n] - phi[i]) % TAU, _GAP_GRID) for i in range(n)]
    start = min(range(n), key=lambda s: tuple(gaps[(s + i) % n] for i in range(n - 1)))
    return [ordered[(start + i) % n] for i in range(n)]


def at_angle(reference, degrees: float, *targets, tol_deg: float = ANGLE_TOL_DEG,
             start=None):
    """기준에서 지정한 사잇각을 이루는 축들. **표준 순서로 돌려준다** (§2.6).

        at_angle(faces.c0, 90, faces)              같은 집합 안
        at_angle(faces.c0, 90, faces, edges)       여러 집합에 걸쳐

    결과는 기준 축 둘레로 반시계 정렬하고, 이웃 간격 수열이 사전순 최소가 되는
    회전에서 시작한다. 그래서 기하가 같은 두 고리는 같은 순서로 나온다 —
    `x, y, z = at_angle(...)` 로 풀 때 어느 축을 어느 이름에 묶을지가 정해진다.

    `start` 를 주면 그 방향의 방위각을 0 으로 놓고 반시계로 센다. 방위각이
    0, 120, 240 인 고리에서 방위각 60 인 것을 `start` 로 주면 120, 240, 0 순서가
    된다. 시작점을 바깥에서 정하고 싶을 때 쓴다 — 이때는 목걸이 표준형을 쓰지
    않는다.

    고리 밖은 담기지 않는다. 극각이 다른 두 고리가 같은 간격 수열을 가질 수
    있으므로, 비교할 때는 각도도 함께 봐야 한다.
    """
    if not targets:
        raise TypeError("give the axis set to search: at_angle(reference, angle, axes)")
    ref = _normal(reference)
    found = [
        a
        for a in axes_of(*targets)
        if abs(math.degrees(math.acos(float(clamp(float(a.normal @ ref))))) - degrees)
        <= tol_deg
    ]
    if start is not None:
        return _ordered_from(ref, found, start)
    return _canonical_ring(ref, found)


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


def group_by_nearest(reference, *targets) -> dict[str, list[Axis]]:
    """targets 의 축들을 가장 가까운 reference 축으로 분류한다.

    대칭이 낮은 축 집합을 익숙한 대칭으로 읽을 때 쓴다.

        group_by_nearest(cube(), pentagonal_icositetrahedron())
        -> 정육면체 면 6개마다 4개씩

    **기준이 먼저다.** 이 파일의 질의는 전부 그렇다 (`at_angle`, `angles_from`,
    `nearest`). 전에는 이것만 반대였는데, 두 인자가 둘 다 축 집합이라 잘못
    써도 예외가 안 나고 **결과만 틀렸다.**
    """
    ref_axes = axes_of(reference)
    if not ref_axes:
        raise ValueError("the reference axis set is empty")
    groups: dict[str, list[Axis]] = {a.id: [] for a in ref_axes}
    for a in axes_of(*targets):
        best = max(ref_axes, key=lambda r: float(r.normal @ a.normal))
        groups[best.id].append(a)
    return groups
