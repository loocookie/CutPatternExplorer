"""단위구 위의 절단 원. 설계 문서 §4.

    ||x|| = 1,  n·x = h,   h = d = cos(theta),  r = sin(theta)

기준점은 항상 원점이다 (§4.1). pCubes 의 h = n·b + d 는 b = 0 에서 h = d 로
축약된다.

numpy 를 쓰지 않는다 (§12, §15). `points` 의 폴리라인 생성만이 배열다운 유일한
연산인데, 호 600개 규모에서 numpy 5.5ms 대 순수 파이썬 10ms 로 절대값이 이미
무시할 수준이다. 그 10ms 를 위해 의존성 전체를 지고 갈 이유가 없다 (§19).
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..epsilon import ANGLE_EPS, RADIUS_EPS
from .angular_coverage import Coverage, reflect, shift, wrap_angle
from .vector import Vec3, clamp, normalize, orthonormal_basis

__all__ = ["SphericalCircle", "transfer_spans"]


@dataclass(frozen=True)
class SphericalCircle:
    """법선 n, offset h 로 정해지는 구면 위의 원."""

    n: Vec3
    h: float
    u: Vec3
    v: Vec3

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
        return math.acos(clamp(self.h))

    def is_degenerate(self) -> bool:
        """반지름이 0 에 가까우면 보이는 경계가 없다."""
        return self.r < RADIUS_EPS

    # ---- 각도 좌표 <-> 3D ---------------------------------------------

    def point(self, t: float) -> Vec3:
        n, u, v, h = self.n, self.u, self.v, self.h
        r = self.r
        c = r * math.cos(t)
        s = r * math.sin(t)
        return tuple.__new__(
            Vec3,
            (
                h * n[0] + c * u[0] + s * v[0],
                h * n[1] + c * u[1] + s * v[1],
                h * n[2] + c * u[2] + s * v[2],
            ),
        )

    def points(self, ts) -> list[Vec3]:
        """각도 열 -> 좌표 목록. 폴리라인 생성용 (§11, §12)."""
        n, u, v, h = self.n, self.u, self.v, self.h
        r = self.r
        hn0, hn1, hn2 = h * n[0], h * n[1], h * n[2]
        u0, u1, u2 = u
        v0, v1, v2 = v
        out: list[Vec3] = []
        new = tuple.__new__
        for t in ts:
            t = float(t)
            c = r * math.cos(t)
            s = r * math.sin(t)
            out.append(
                new(
                    Vec3,
                    (
                        hn0 + c * u0 + s * v0,
                        hn1 + c * u1 + s * v1,
                        hn2 + c * u2 + s * v2,
                    ),
                )
            )
        return out

    def angle_of(self, p) -> float:
        """구면 위 점의 이 원 기준 각도 좌표."""
        u, v = self.u, self.v
        x, y, z = p[0], p[1], p[2]
        return wrap_angle(
            math.atan2(
                x * v[0] + y * v[1] + z * v[2],
                x * u[0] + y * u[1] + z * u[2],
            )
        )

    def sample_span(self, t0: float, t1: float, max_step: float = 0.05) -> list[Vec3]:
        """호 하나를 폴리라인 점 목록으로 tessellate 한다."""
        length = t1 - t0
        n_seg = max(2, int(math.ceil(length / max_step)))
        step = length / n_seg
        # 끝점은 누적 오차 없이 t1 을 그대로 쓴다 (np.linspace 와 같은 규약)
        ts = [t0 + i * step for i in range(n_seg)]
        ts.append(t1)
        return self.points(ts)

    def negated(self) -> "SphericalCircle":
        """같은 평면의 반대 표현 (-n, -h)."""
        return SphericalCircle.from_normal_offset(-self.n, -self.h)


def transfer_spans(src: SphericalCircle, dst: SphericalCircle, spans: Coverage) -> Coverage:
    """src 기준 각도 구간을 같은 평면인 dst 기준 각도 구간으로 옮긴다.

    두 원은 같은 기하 원이어야 한다. src.n 과 dst.n 이 같은 방향이면 사상은
    순수 회전 ``t_dst = t_src + c`` 이고, 반대 방향이면 손이 뒤집혀
    ``t_dst = -t_src + c`` 가 된다 (§4.3).
    """
    same_side = (src.n @ dst.n) > 0.0
    c = dst.angle_of(src.point(0.0))
    if same_side:
        if c < ANGLE_EPS or c > 2.0 * math.pi - ANGLE_EPS:
            return list(spans)  # 사실상 동일한 기저. 쓸데없는 잡음을 넣지 않는다
        return shift(spans, c)
    return reflect(spans, c)
