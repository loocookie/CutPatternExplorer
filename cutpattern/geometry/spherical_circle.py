"""단위구 위의 절단 원. 설계 문서 §4.

    ||x|| = 1,  n·x = h,   h = d = cos(theta),  r = sin(theta)

기준점은 항상 원점이다 (§4.1). pCubes 의 h = n·b + d 는 b = 0 에서 h = d 로
축약된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from ..epsilon import ANGLE_EPS, RADIUS_EPS
from .angular_coverage import Coverage, reflect, shift, wrap_angle
from .vector import as_vec, clamp, normalize, orthonormal_basis

__all__ = ["SphericalCircle", "transfer_spans"]


@dataclass(frozen=True)
class SphericalCircle:
    """법선 n, offset h 로 정해지는 구면 위의 원."""

    n: np.ndarray
    h: float
    u: np.ndarray
    v: np.ndarray

    # ---- 생성 ----------------------------------------------------------

    @classmethod
    def from_normal_offset(cls, n, h: float) -> "SphericalCircle":
        nn = normalize(n)
        u, w = orthonormal_basis(nn)
        return cls(n=nn, h=float(h), u=u, v=w)

    @classmethod
    def from_axis_angle(cls, n, theta: float) -> "SphericalCircle":
        """축 방향 n 과 각반경 theta(라디안)로 만든다. h = cos(theta)."""
        return cls.from_normal_offset(n, math.cos(theta))

    # ---- 기본량 --------------------------------------------------------

    @property
    def r(self) -> float:
        """원의 반지름. sqrt 안을 max(0, .) 로 감싼다 (§14)."""
        return math.sqrt(max(0.0, 1.0 - self.h * self.h))

    @property
    def theta(self) -> float:
        """각반경."""
        return math.acos(float(clamp(self.h)))

    def is_degenerate(self) -> bool:
        """반지름이 0 에 가까우면 보이는 경계가 없다."""
        return self.r < RADIUS_EPS

    # ---- 각도 좌표 <-> 3D ---------------------------------------------

    def point(self, t: float) -> np.ndarray:
        r = self.r
        return self.h * self.n + r * (math.cos(t) * self.u + math.sin(t) * self.v)

    def points(self, ts) -> np.ndarray:
        """각도 배열 -> (N, 3) 좌표. numpy 일괄 처리 (§11, §12)."""
        ts = np.asarray(ts, dtype=np.float64).reshape(-1, 1)
        r = self.r
        return self.h * self.n + r * (np.cos(ts) * self.u + np.sin(ts) * self.v)

    def angle_of(self, p) -> float:
        """구면 위 점의 이 원 기준 각도 좌표."""
        p = as_vec(p)
        return wrap_angle(math.atan2(float(p @ self.v), float(p @ self.u)))

    def sample_span(self, t0: float, t1: float, max_step: float = 0.05) -> np.ndarray:
        """호 하나를 폴리라인 점 배열로 tessellate 한다."""
        length = t1 - t0
        n_seg = max(2, int(math.ceil(length / max_step)))
        return self.points(np.linspace(t0, t1, n_seg + 1))

    def negated(self) -> "SphericalCircle":
        """같은 평면의 반대 표현 (-n, -h)."""
        return SphericalCircle.from_normal_offset(-self.n, -self.h)


def transfer_spans(src: SphericalCircle, dst: SphericalCircle, spans: Coverage) -> Coverage:
    """src 기준 각도 구간을 같은 평면인 dst 기준 각도 구간으로 옮긴다.

    두 원은 같은 기하 원이어야 한다. src.n 과 dst.n 이 같은 방향이면 사상은
    순수 회전 ``t_dst = t_src + c`` 이고, 반대 방향이면 손이 뒤집혀
    ``t_dst = -t_src + c`` 가 된다 (§4.3).
    """
    same_side = float(src.n @ dst.n) > 0.0
    c = dst.angle_of(src.point(0.0))
    if same_side:
        if c < ANGLE_EPS or c > 2.0 * math.pi - ANGLE_EPS:
            return list(spans)  # 사실상 동일한 기저. 쓸데없는 잡음을 넣지 않는다
        return shift(spans, c)
    return reflect(spans, c)
