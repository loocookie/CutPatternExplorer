"""cap 분류와 교점. 설계 문서 §7.2, §7.3.

회전축 a, 임계값 d 에 대해 선택 영역은 절단원 ``a·x = d`` 의 한쪽이다.

    side = +1   cap        a·x > d      극 쪽 (0 ~ theta)
    side = -1   complement a·x < d      나머지 (theta ~ 180)

경계원이 같으므로 합법성 판정도 교점 계산도 그대로다. 판정 부호만 뒤집힌다.
이것만으로 slice 회전이 합성으로 나온다.

    M 슬라이스를 U 축으로 alpha 회전
        turn(U, alpha, outer=True)   U cap 을 뺀 나머지를 회전
        turn(D, alpha)               D cap 을 되돌림 (D 축 기준이라 U 축으로는 -alpha)
carrier 원 (n, h) 위에서

    a·x(t) = m + s·cos(t - phi)

    an  = clamp(a·n)
    m   = h · an
    s   = sqrt(1-h^2) · sqrt(1-an^2)
    phi = atan2(a·v, a·u)

s 는 원을 한 바퀴 돌 때 a 방향 높이의 진폭이다.
"""

from __future__ import annotations

import math

from ..epsilon import ANGLE_EPS, S_EPS, SEL_EPS
from .angular_coverage import TAU, wrap_angle
from .spherical_circle import SphericalCircle
from .vector import clamp

__all__ = [
    "MOVING",
    "FIXED",
    "MIXED",
    "STRADDLING",
    "CircleTerms",
    "circle_terms",
    "classify_carrier",
    "classify_span",
    "straddle_roots",
    "split_span_by_cap",
]

MOVING = "MOVING"
FIXED = "FIXED"
MIXED = "MIXED"
STRADDLING = "STRADDLING"


class CircleTerms:
    """한 carrier 원에 대한 a·x(t) 의 계수."""

    __slots__ = ("an", "m", "s", "phi")

    def __init__(self, an: float, m: float, s: float, phi: float) -> None:
        self.an = an
        self.m = m
        self.s = s
        self.phi = phi

    @property
    def is_coaxial(self) -> bool:
        """진폭이 0. 원 전체가 축 방향으로 같은 높이에 있다 (§7.2 1단계)."""
        return self.s < S_EPS

    def value(self, t: float) -> float:
        return self.m + self.s * math.cos(t - self.phi)

    def extrema_angles(self) -> tuple[float, float]:
        """최대각, 최소각."""
        return wrap_angle(self.phi), wrap_angle(self.phi + math.pi)


def circle_terms(circle: SphericalCircle, a) -> CircleTerms:
    """호출 빈도가 제일 높은 함수다. 벡터 연산자를 쓰지 않고 성분을 지역 변수로
    풀어 float 산술을 직접 한다 (§12).
    """
    ax, ay, az = a[0], a[1], a[2]
    n = circle.n
    an = ax * n[0] + ay * n[1] + az * n[2]
    if an > 1.0:
        an = 1.0
    elif an < -1.0:
        an = -1.0
    h = circle.h
    m = h * an
    s = math.sqrt(max(0.0, 1.0 - h * h)) * math.sqrt(max(0.0, 1.0 - an * an))
    u, v = circle.u, circle.v
    phi = math.atan2(
        ax * v[0] + ay * v[1] + az * v[2],
        ax * u[0] + ay * u[1] + az * u[2],
    )
    return CircleTerms(an, m, s, wrap_angle(phi))


def classify_carrier(circle: SphericalCircle, a, d: float, side: float = 1.0) -> str:
    """원 단위 판정. MOVING / FIXED 면 span 검사를 통째로 건너뛴다.

    1단계 ``s ~= 0`` 분기가 먼저다. 이 분기가 없으면 §7.3 의 ``(d-m)/s`` 가
    0 으로 나누기가 되고, 준동축에서는 arccos 정의역을 벗어나 NaN 이 된다.
    동축은 드문 경우가 아니라 Turn 마다 반드시 나온다 (회전축 자신의 cut 원,
    그리고 축과 평행한 법선을 가진 모든 cut).
    """
    ct = circle_terms(circle, a)

    # 1단계: 동축(또는 퇴화). 원 전체가 한 높이이므로 통째로 판정
    if ct.is_coaxial:
        return MOVING if side * (ct.m - d) > SEL_EPS else FIXED

    # 2단계: 원 전체 값 범위 [m-s, m+s] 로 조기 기각. 기각 전용이다
    ends = (side * (ct.m - ct.s - d), side * (ct.m + ct.s - d))
    lo, hi = min(ends), max(ends)
    if lo > SEL_EPS:
        return MOVING
    if hi <= SEL_EPS:
        return FIXED
    return MIXED


def classify_span(
    circle: SphericalCircle, a, d: float, t0: float, t1: float, side: float = 1.0
) -> str:
    """3단계: span 단위 판정. 끝점 + 구간 안의 내부 극값을 본다.

    원 전체 범위를 span 판정에 그대로 쓰면 안 된다.
    """
    ct = circle_terms(circle, a)
    if ct.is_coaxial:
        return MOVING if side * (ct.m - d) > SEL_EPS else FIXED

    cands = [t0, t1]
    for e in ct.extrema_angles():
        if t0 - ANGLE_EPS <= e <= t1 + ANGLE_EPS:
            cands.append(e)

    vals = [side * (ct.value(t) - d) for t in cands]
    above = any(v > SEL_EPS for v in vals)
    below = any(v < -SEL_EPS for v in vals)
    if above and below:
        return STRADDLING
    if above:
        return MOVING
    # 전부 경계 위인 경우도 FIXED 다. 경계에 얹힌 호는 움직이지 않는다 (§7.2 0단계)
    return FIXED


def straddle_roots(circle: SphericalCircle, a, d: float) -> list[float]:
    """a·x(t) = d 의 해. 0개 또는 2개 (접점이면 같은 값 하나로 처리)."""
    ct = circle_terms(circle, a)
    if ct.is_coaxial:
        return []
    c = (d - ct.m) / ct.s
    if c > 1.0 + 1e-12 or c < -1.0 - 1e-12:
        return []
    ac = math.acos(clamp(c))
    r0 = wrap_angle(ct.phi + ac)
    r1 = wrap_angle(ct.phi - ac)
    if abs(r0 - r1) < ANGLE_EPS or abs(abs(r0 - r1) - TAU) < ANGLE_EPS:
        return [r0]  # 접점. 두 개의 가까운 교점으로 만들지 않는다 (§14)
    return sorted([r0, r1])


def split_span_by_cap(
    circle: SphericalCircle, a, d: float, t0: float, t1: float, side: float = 1.0
) -> list[tuple[float, float, bool]]:
    """span 을 cap 경계에서 나눈다. 반환은 (t0, t1, is_moving) 목록.

    straddling 인 span 에만 부른다. 각 조각의 **중점**을 평가해 이동/고정을
    정한다 (§7.3).
    """
    ct = circle_terms(circle, a)
    cuts = [t0, t1]
    for r in straddle_roots(circle, a, d):
        if t0 + ANGLE_EPS < r < t1 - ANGLE_EPS:
            cuts.append(r)
    cuts.sort()

    out: list[tuple[float, float, bool]] = []
    for s, e in zip(cuts, cuts[1:]):
        if e - s <= ANGLE_EPS:
            continue
        mid = 0.5 * (s + e)
        out.append((s, e, side * (ct.value(mid) - d) > SEL_EPS))
    return out
