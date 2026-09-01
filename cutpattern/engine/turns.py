"""회전각 유도. 설계 문서 §7.

회전각은 정적 필드가 아니라 **현재 절단 각도의 함수**다. 슬라이더를 움직이면
고리가 침범했다 말았다 하므로 가능한 회전 자체가 달라진다.

원리
----
축 a1 둘레로 같은 극각에 놓인 축들이 고리를 이룬다. a1 을 alpha 만큼 돌렸을 때
고리 안의 어떤 축 하나가 **같은 고리의 다른 축 위로** 가면, 옮겨간 절단원이
이미 있던 절단원에 얹힌다. 그 다음에 그 축으로 또 돌릴 수 있다.

전체 고리를 자기 자신으로 보낼 필요는 없다. 그걸 요구하면 doctrinaire 회전만
남고 jumbling 을 통째로 놓친다. 손대칭 24궤도(오각이십사면체 등)에서는 고리를
보존하는 회전이 하나도 없어 목록이 비어버린다.

그래서 **고리 안의 모든 쌍차를 모으고, 고리와 축 집합에 걸쳐 합집합**한다.
대칭 입체에서는 고리가 하나의 궤도라 합집합과 교집합이 어차피 같다.

침범 조건
---------
a1 의 cap 반경 theta1, a2 의 절단원은 a2 에서 극각 theta2. a1 에서 그 원까지
최단 거리가 |angle - theta2| 이므로

    a2 의 원이 a1 의 cap 에 걸린다  <=>  |angle - theta2| < theta1

즉 angle, theta1, theta2 가 구면삼각형 부등식을 만족해야 한다. 바깥쪽 회전이면
반대로 원의 일부가 cap 밖에 있어야 한다.

한계
----
유도되는 것은 절단원끼리 맞아떨어지는 각이다. 축이 어느 재료에 물려 있는지는
경계면만으로 알 수 없으므로, 실려 도는 축은 `carry` 로 선언하고 여기서 제외한다
(§2.1). 유도가 못 찾는 각은 축의 `turn_angles` 로 명시한다.
"""

from __future__ import annotations

import math
from collections import defaultdict

from ..geometry.vector import clamp, orthonormal_basis
from .axes import Axis, PuzzleFamily

__all__ = ["ANGLE_TOL_DEG", "derived_turns", "available_turns", "rings_around",
           "declares", "matches_declared"]

# 극각과 방위각을 같은 값으로 볼 허용 오차(도).
# acos 는 인자가 +-1 근처에서 오차를 sqrt(eps) ~ 1e-8 rad 까지 키운다.
ANGLE_TOL_DEG = 1e-4


def _angle_between(a, b) -> float:
    return math.degrees(math.acos(clamp(a @ b)))


def rings_around(
    family: PuzzleFamily,
    axis: Axis,
    cut_angles: dict[str, float],
    *,
    outer: bool = False,
    carried: set[str] | None = None,
) -> dict[tuple[float, float], list[tuple[Axis, float]]]:
    """axis 를 돌릴 때 영향받는 축들을 (극각, 상대 절단각) 으로 묶는다.

    회전은 극각을 보존하고, 원이 겹치려면 반지름도 같아야 하므로 두 값이 모두
    같아야 한 고리다. 반환값은 {(극각, theta2): [(축, 방위각), ...]}.
    """
    carried = carried or set()
    a = axis.normal
    u, v = orthonormal_basis(a)

    theta1 = None
    for aset in family.axis_sets:
        if any(x.id == axis.id for x in aset.axes):
            theta1 = float(cut_angles[aset.cut_angle_input])
            break
    if theta1 is None:
        raise KeyError(f"axis {axis.id!r} is not in any set")

    rings: dict[tuple[float, float], list[tuple[Axis, float]]] = defaultdict(list)
    for aset in family.axis_sets:
        theta2 = float(cut_angles[aset.cut_angle_input])
        for other in aset.axes:
            if other.id == axis.id or other.id in carried:
                continue
            angle = _angle_between(a, other.normal)
            # 축 위에 있으면 방위각이 정의되지 않는다. 회전에 불변이므로 제약 없음
            if angle < ANGLE_TOL_DEG or angle > 180.0 - ANGLE_TOL_DEG:
                continue
            if not _is_engaged(angle, theta1, theta2, outer):
                continue
            phi = math.degrees(
                math.atan2(float(other.normal @ v), float(other.normal @ u))
            ) % 360.0
            if phi > 360.0 - ANGLE_TOL_DEG:
                phi = 0.0  # 부동소수로 360 에 붙은 값
            rings[(round(angle, 6), round(theta2, 6))].append((other, phi))
    return dict(rings)


def _is_engaged(angle: float, theta1: float, theta2: float, outer: bool) -> bool:
    """a2 의 절단원이 회전 영역에 걸리는가.

    안쪽(cap)   : 원의 일부가 cap 안에 있어야 한다.  |angle - theta2| < theta1
    바깥쪽      : 원의 일부가 cap 밖에 있어야 한다.  최대 거리 > theta1
    """
    d_min = abs(angle - theta2)
    if not outer:
        return d_min < theta1 - ANGLE_TOL_DEG
    d_max = min(angle + theta2, 360.0 - angle - theta2)
    return d_max > theta1 + ANGLE_TOL_DEG


def derived_turns(
    family: PuzzleFamily,
    axis: Axis,
    cut_angles: dict[str, float],
    *,
    outer: bool = False,
    carried: set[str] | None = None,
    tol_deg: float = ANGLE_TOL_DEG,
) -> list[float]:
    """현재 절단 각도에서 이 축을 돌릴 만한 각들.

    고리 안의 축 하나가 같은 고리의 다른 축 위로 가는 각을 전부 모은다.
    """
    rings = rings_around(family, axis, cut_angles, outer=outer, carried=carried)
    out: list[float] = []
    for members in rings.values():
        if len(members) < 2:
            continue  # 쌍이 없으면 기여할 각이 없다
        phis = [phi for _axis, phi in members]
        for i, pi in enumerate(phis):
            for j, pj in enumerate(phis):
                if i == j:
                    continue
                out.append((pj - pi) % 360.0)

    uniq: list[float] = []
    for value in sorted(out):
        if value < tol_deg or value > 360.0 - tol_deg:
            continue  # 0 도는 회전이 아니다
        if not uniq or value - uniq[-1] > tol_deg:
            uniq.append(value)
    return uniq


def _circular_diff(a: float, b: float) -> float:
    """0~360 을 고리로 보고 잰 차이."""
    d = abs((a % 360.0) - (b % 360.0))
    return min(d, 360.0 - d)


def declares(axis: Axis) -> bool:
    """이 축이 회전각을 선언했는가. 안 했으면 제약이 없다."""
    return bool(axis.turn_angles)


def matches_declared(axis: Axis, angle: float, outer: bool = False) -> bool:
    """이 회전이 축에 선언된 각인가 (§7.11).

    **선언이 비어 있으면 참이다.** 타입을 안 붙인 인자와 같다 — 안 적었으면
    제약이 없고, 적었으면 검사한다.

    **선언은 cap 기준이다.** cap 을 +t 돌린 상태는 outer 를 -t 돌린 상태와
    (구 전체 회전 차이로) 같으므로, outer 회전은 부호를 뒤집어 본다. 그래서
    `-60` 을 선언해 두면 `turn(x, 60, outer=True)` 가 열린다.
    """
    if not axis.turn_angles:
        return True
    want = (-angle if outer else angle)
    return any(_circular_diff(want, float(d)) <= ANGLE_TOL_DEG
               for d in axis.turn_angles)


def available_turns(
    family: PuzzleFamily,
    axis: Axis,
    cut_angles: dict[str, float],
    *,
    outer: bool = False,
    carried: set[str] | None = None,
) -> list[float]:
    """유도된 각과 축에 선언된 각의 합집합.

    유도는 절단원이 맞아떨어지는 각만 찾는다. 그밖에 의미 있는 각이 있으면
    축의 turn_angles 로 넣는다.

    **outer 면 선언된 각의 부호를 뒤집어 얹는다.** 선언은 cap 기준이고
    cap(+t) == outer(-t) 이기 때문이다 (matches_declared 와 같은 규칙).
    부호 반전에 닫힌 목록(`45, -45, 90, -90, 180`)에서는 차이가 안 나지만,
    비대칭 목록에서는 다른 값이 나온다.
    """
    values = derived_turns(family, axis, cut_angles, outer=outer, carried=carried)
    for extra in axis.turn_angles:
        value = (-float(extra) if outer else float(extra)) % 360.0
        if value < ANGLE_TOL_DEG:
            continue
        if not any(abs(value - v) <= ANGLE_TOL_DEG for v in values):
            values.append(value)
    return sorted(values)
