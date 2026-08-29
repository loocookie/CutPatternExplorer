"""축 위치 마커. 설계 문서 §11, §15.

축 id 는 `c0`, `c2` 처럼 그 자체로는 방향을 말해주지 않는다. 정의를 쓸 때는
`faces["c2"]` 라고 타이핑해야 하는데 화면에서 어느 것이 `c2` 인지 알 길이
없다. 마커는 그 대응을 보여준다.

**절단 호와 같은 방식으로 그린다.** 축 방향 `n` 을 중심으로 작은 각반경의 원을
만들면 그것도 구면 위의 원이므로, 반투명 구가 뒤쪽 마커를 흐리게 하는 것이
뒤쪽 절단 호를 흐리게 하는 것과 정확히 같은 방식으로 일어난다. 점 스프라이트나
빌보드였으면 그 깊이 표현을 따로 만들어야 했다.

**registry 를 거치지 않는다.** 마커는 표시 전용이다. 마커 원이
`BoundaryRegistry` 에 들어가면 `total_arc_length` 가 오염되고 `is_complete` 가
바뀌어 §7.1 회전 합법성 판정이 달라진다. 조용히 틀리는 종류라, 아예 `evaluate`
를 태우지 않고 `PuzzleFamily` 에서 직접 만든다.

절단 각도와 무관하다. 축 방향은 슬라이더가 움직여도 그대로이므로 (실림이
선언된 축도 평가가 끝나면 제자리다, §2.1) 한 번 만들어 두고 쓰면 된다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from ..engine.axes import PuzzleFamily
from ..geometry.angular_coverage import TAU
from ..geometry.spherical_circle import SphericalCircle
from ..geometry.vector import Vec3

__all__ = ["AxisMarker", "MARKER_ANGLE_DEG", "LABEL_OFFSET", "build_axis_markers"]

# 마커 원의 각반경(도). 작을수록 점에 가깝다.
#
# 진짜 얕은 절단과 헷갈리면 안 된다 (theta 를 2도로 놓을 수 있다). 크기만으로는
# 구분이 안 되므로 렌더러가 굵기와 투명도를 다르게 준다 (§11.3). 이 값이 충분히
# 작으면 선 굵기가 원 지름을 넘어 고리가 아니라 점으로 읽힌다.
MARKER_ANGLE_DEG = 1.0

# 라벨을 구 표면에서 얼마나 띄울지. 1.0 이면 표면에 붙는다.
LABEL_OFFSET = 1.08

# 마커 폴리라인의 구면 위 목표 변 길이(라디안).
#
# `sample_span(max_step)` 의 단위는 **carrier 각도**이지 구면 위 호 길이가
# 아니다. 반지름 r 인 원에서 실제 길이는 `r * Δt` 이고 `r = sin(theta)` 다.
# 절단원은 r 이 1 에 가까워 둘이 거의 같지만, 5도 마커는 r = 0.087 이라 같은
# max_step 을 주면 11배 잘게 쪼갠다. 그래서 여기서 환산한다.
MARKER_ARC_STEP = 0.05

# 아무리 작은 원이라도 이보다 적은 변으로는 그리지 않는다. 안 그러면 각져 보인다
MARKER_MIN_SEGMENTS = 16


@dataclass
class AxisMarker:
    """축 하나의 화면 표시."""

    id: str
    axis_id: str
    axis_set_id: str
    # 축 방향. 앞/뒤 반구 판정에 쓴다 (라벨은 빌보드라 구에 가려지지 않는다)
    direction: Vec3
    points: list[Vec3]
    label_position: Vec3


def marker_id(axis_set_id: str, axis_id: str) -> str:
    """결정적 마커 ID (§11 렌더 객체 pool).

    호 ID 와 달리 절단 각도가 섞이지 않는다. 축 집합과 축 id 만으로 정해지므로
    슬라이더를 아무리 움직여도 같은 객체를 재사용한다.
    """
    return f"m:{axis_set_id}:{axis_id}"


def build_axis_markers(
    family: PuzzleFamily,
    angle_deg: float = MARKER_ANGLE_DEG,
    arc_step: float = MARKER_ARC_STEP,
    label_offset: float = LABEL_OFFSET,
) -> list[AxisMarker]:
    """축 집합의 모든 축에 대해 마커를 만든다.

    angle_deg 는 마커 원의 각반경이다. 축이 많은 집합(카탈란 60면체, 120면체)
    에서는 줄여서 겹침을 줄인다.

    arc_step 은 **구면 위** 변 길이다. carrier 각도 단위인 `sample_span` 의
    max_step 으로 환산해서 넘긴다.
    """
    theta = math.radians(angle_deg)
    radius = math.sin(theta)
    max_step = TAU / MARKER_MIN_SEGMENTS
    if radius > 0.0:
        max_step = min(max_step, arc_step / radius)
    out: list[AxisMarker] = []
    for aset in family.axis_sets:
        for axis in aset.axes:
            n = axis.normal
            circle = SphericalCircle.from_axis_angle(n, theta)
            out.append(
                AxisMarker(
                    id=marker_id(aset.id, axis.id),
                    axis_id=axis.id,
                    axis_set_id=aset.id,
                    direction=n,
                    points=circle.sample_span(0.0, TAU, max_step=max_step),
                    label_position=n * label_offset,
                )
            )
    return out
