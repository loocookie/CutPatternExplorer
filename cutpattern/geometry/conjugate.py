"""회전 짝 접합. 설계 문서 §7.10, §12.3-2.

`turned(a, θ)` 블록은 회전하고, 자르고, 정확히 되돌린다. 지금은 그 왕복이
registry 의 모든 span 을 두 번 훑는데, 살아남는 것은 그 사이 split 이 추가한
호뿐이다. 전체 시간의 대부분이 버려지는 상태 변경에 들어간다.

접합의 근거
-----------
`turn` 은 전역 회전이 아니다. cap 쪽만 돌고 나머지는 그대로다.

    Φ(x) = R(x)   x ∈ cap
           x      그 밖

`R` 이 축 `a` 둘레 회전이므로 `R(cap) = cap` 이고, 따라서 `Φ` 는 구면의
전단사다. 그러면 블록 전체가 한 줄로 줄어든다.

    E → Φ(E) → Φ(E) ∪ C → Φ⁻¹(Φ(E) ∪ C) = E ∪ Φ⁻¹(C)

`E` 를 건드릴 이유가 없다. 새로 자르는 원 `C` 만 `Φ⁻¹` 로 끌어오면 된다.
비용이 `O(|E|)` 에서 `O(|C|)` 로 내려가고, 왕복이 만들던 빈 carrier 도 안
생긴다 — 그쪽이 registry 를 부풀려 `turn` 을 제곱으로 만들던 원인이었다.

중첩된 블록은 안쪽부터 끌어온다. 정방향이 `Φ₁` 다음 `Φ₂` 였다면 되돌리기는
`Φ₁⁻¹ ∘ Φ₂⁻¹` 다.

이 모듈은 registry 를 모른다. (원, 구간) 조각 목록을 받아 (원, 구간) 조각
목록을 돌려줄 뿐이다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..epsilon import ANGLE_EPS
from .angular_coverage import TAU, Coverage, make_span, normalize_spans
from .classify import FIXED, MOVING, classify_carrier, split_span_by_cap
from .spherical_circle import SphericalCircle
from .vector import Mat3, Vec3, normalize, rotation_matrix

__all__ = ["TurnFrame", "Piece", "pull_back", "pull_back_all"]

# (원, 그 원 위의 구간들)
Piece = tuple[SphericalCircle, Coverage]


@dataclass(frozen=True)
class TurnFrame:
    """접합에 필요한 회전 하나 (§7.10).

    normal, offset 이 회전 경계원이고 side 는 +1 이면 cap, -1 이면 그 여집합
    (`outer=True`). angle 은 **정방향** 각도(라디안)다. 끌어올 때는 그 역을 쓴다.
    """

    normal: Vec3
    offset: float
    side: float
    angle: float

    @staticmethod
    def make(normal, theta_deg: float, angle_deg: float, outer: bool) -> "TurnFrame":
        return TurnFrame(
            normal=normalize(normal),
            offset=math.cos(math.radians(theta_deg)),
            side=-1.0 if outer else 1.0,
            angle=math.radians(angle_deg),
        )

    def inverse_matrix(self) -> Mat3:
        return rotation_matrix(self.normal, -self.angle)


def _cap_pieces(
    circle: SphericalCircle, spans: Coverage, frame: TurnFrame
) -> tuple[Coverage, Coverage]:
    """구간들을 cap 안(도는 쪽)과 밖(그대로 있는 쪽)으로 가른다.

    §7.2 의 분류를 그대로 쓴다. 원 단위로 끝나면 span 검사를 건너뛴다.
    """
    a, d, side = frame.normal, frame.offset, frame.side
    cls = classify_carrier(circle, a, d, side)
    if cls == MOVING:
        return normalize_spans(spans), []
    if cls == FIXED:
        return [], normalize_spans(spans)
    inside: Coverage = []
    outside: Coverage = []
    for t0, t1 in spans:
        for s, e, is_moving in split_span_by_cap(circle, a, d, t0, t1, side):
            if e - s <= ANGLE_EPS:
                continue
            (inside if is_moving else outside).append((s, e))
    return normalize_spans(inside), normalize_spans(outside)


def pull_back(pieces: list[Piece], frame: TurnFrame) -> list[Piece]:
    """`Φ⁻¹` 을 적용한다.

    cap 밖은 그대로 두고, cap 안만 `R⁻¹` 로 옮긴다. 옮긴 조각은 다른 원 위에
    앉으므로 조각 수가 늘 수 있다.
    """
    matrix = frame.inverse_matrix()
    out: list[Piece] = []
    for circle, spans in pieces:
        if not spans:
            continue
        inside, outside = _cap_pieces(circle, spans, frame)
        if outside:
            out.append((circle, outside))
        if not inside:
            continue
        # 구 중심을 지나는 회전이므로 offset 은 불변. 사상은 순수 회전 t -> t + c
        rotated = SphericalCircle.from_normal_offset(matrix @ circle.n, circle.h)
        c = rotated.angle_of(matrix @ circle.point(0.0))
        moved: Coverage = []
        for t0, t1 in inside:
            moved.extend(make_span(t0 + c, t1 - t0))
        if moved:
            out.append((rotated, normalize_spans(moved)))
    return out


def pull_back_all(circle: SphericalCircle, frames) -> list[Piece]:
    """원 하나를 회전 스택 전체로 끌어온다.

    frames 는 **정방향으로 적용된 순서**다. 되돌리기는 그 역순이므로 뒤에서부터
    적용한다.
    """
    pieces: list[Piece] = [(circle, [(0.0, TAU)])]
    for frame in reversed(frames):
        pieces = pull_back(pieces, frame)
    return pieces
