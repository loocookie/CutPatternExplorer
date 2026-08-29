"""호를 점 배열로 변환. 설계 문서 §11.

렌더러에 의존하지 않는다. numpy 배열만 내보내므로 vpython, Canvas 2D,
어느 백엔드로도 그대로 쓸 수 있다 (§15).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from ..geometry.registry import BoundaryRegistry
from ..geometry.span import Provenance
from ..geometry.spherical_circle import SphericalCircle

__all__ = ["RenderArc", "build_arcs", "arc_id"]


def arc_id(carrier_index: int, op_index: int, ordinal: int) -> str:
    """결정적 호 ID (§5, §11).

    ``(carrierKey, opIndex, ordinal)`` 로 만든다. 각도 값을 넣으면 slider 를
    조금만 움직여도 ID 가 바뀌어 렌더 객체 pool 이 무의미해진다. 같은 입력으로
    replay 하면 같은 ID 가 나와야 객체를 삭제, 재생성하지 않고 좌표만 갱신할
    수 있다.
    """
    return f"c{carrier_index}:o{op_index}:{ordinal}"


@dataclass
class RenderArc:
    id: str
    carrier_index: int
    circle: SphericalCircle
    t0: float
    t1: float
    points: np.ndarray  # (N, 3)
    provenance: Provenance
    is_full_circle: bool


def build_arcs(registry: BoundaryRegistry, max_step: float = 0.05) -> list[RenderArc]:
    """registry 의 모든 span 을 폴리라인으로 만든다.

    max_step 은 라디안 단위 tessellation 간격. slider 조작 중에는 크게,
    조작 종료 후에는 작게 준다 (§12).
    """
    out: list[RenderArc] = []
    for bc in registry:
        if not bc.spans or bc.circle.is_degenerate():
            continue
        complete = bc.is_complete
        for ordinal, span in enumerate(bc.spans):
            out.append(
                RenderArc(
                    id=arc_id(bc.index, span.provenance.op_index, ordinal),
                    carrier_index=bc.index,
                    circle=bc.circle,
                    t0=span.t0,
                    t1=span.t1,
                    points=bc.circle.sample_span(span.t0, span.t1, max_step=max_step),
                    provenance=span.provenance,
                    is_full_circle=complete and len(bc.spans) == 1,
                )
            )
    return out
