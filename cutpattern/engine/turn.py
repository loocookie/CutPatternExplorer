"""Turn 연산. 설계 문서 §7.

Turn 은 새 절단을 만들지 않는다. 선택 영역 안의 기존 호를 강체 회전시킬 뿐이다.
경계를 걸치는 호는 경계 교차점에서 레코드를 쪼개는데, 그 교차점은 이미 존재하는
cut(회전 경계원) 위의 점이므로 점집합으로서의 E 는 변하지 않는다.

**Turn 은 항상 합법성을 검사한다.** 불법이면 상태를 전혀 바꾸지 않는다.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..epsilon import ANGLE_EPS
from ..geometry.angular_coverage import TAU, difference, make_span
from ..geometry.classify import (
    FIXED,
    MOVING,
    classify_carrier,
    classify_span,
    split_span_by_cap,
)
from ..geometry.region import Region, covers_within
from ..geometry.registry import BoundaryCircle, BoundaryRegistry
from ..geometry.span import AngularSpan
from ..geometry.spherical_circle import SphericalCircle
from ..geometry.vector import normalize, rotation_matrix
from .axes import Axis

__all__ = ["IllegalTurnError", "TurnResult", "is_turn_legal", "turn"]


class IllegalTurnError(Exception):
    """회전 경계원이 완전한 cut 이 아니라서 돌릴 수 없다 (§7.1)."""

    def __init__(self, axis_id: str, reason: str) -> None:
        super().__init__(f"불법 회전: 축 {axis_id!r} - {reason}")
        self.axis_id = axis_id
        self.reason = reason


@dataclass
class TurnResult:
    axis_id: str
    angle_deg: float
    moved_spans: int = 0
    straddling_spans: int = 0
    carriers_before: int = 0
    carriers_after: int = 0
    no_op: bool = False
    outer: bool = False
    # 접합으로 실행을 건너뛴 회전 (§7.10). 로그 모양을 유지하려고 남긴다
    conjugated: bool = False
    # 진단용. 실제로 옮긴 호들 (출발 carrier 법선, t0, t1)
    moved: tuple = ()


def is_turn_legal(
    registry: BoundaryRegistry, axis: Axis, theta_deg: float, constraints=()
) -> bool:
    """회전 경계원이 이미 E 안에서 2pi 전체 covered 인가. 이것만이 조건이다.

    다른 호가 그 경계를 가로지르는 것은 문제가 아니다. 교차점은 정의상 경계원
    위에 있고, 경계원이 완전한 cut 이므로 그 지점에 이어진 재료가 없다.
    3x3x3 에서 R cut 원이 U cut 원을 가로지르지만 U 회전이 합법인 이유다.
    """
    d = math.cos(math.radians(theta_deg))
    hit = registry.find(axis.normal, d)
    if hit is None:
        return False
    carrier = hit[0]
    complete, _missing = covers_within(carrier.circle, carrier.coverage, constraints)
    return complete


def _as_region(constraints):
    """제약 목록이든 Region 이든 Region 으로."""
    if constraints is None:
        return None
    if isinstance(constraints, Region):
        return constraints if constraints.cells != [()] else None
    return Region([tuple(constraints)]) if constraints else None


def _covers(carrier, region):
    if region is None:
        return covers_within(carrier.circle, carrier.coverage, ())
    inside, _outside = region.clip(carrier.circle, [(0.0, TAU)])
    if not inside:
        return True, []
    gaps = difference(inside, carrier.visible_coverage)
    gaps = [(a, b) for a, b in gaps if b - a > ANGLE_EPS]
    return (not gaps), gaps


def turn(
    registry: BoundaryRegistry,
    axis: Axis,
    theta_deg: float,
    angle_deg: float,
    op_index: int = -1,
    outer: bool = False,
    constraints=(),
) -> TurnResult:
    """축의 절단원 한쪽을 회전한다.

    outer=False  cap        a·x > d      0 ~ theta
    outer=True   complement a·x < d      theta ~ 180

    경계원이 같으므로 합법성 판정은 동일하다. slice 회전은 두 연산의 합성이다.

        M 슬라이스 = turn(U, alpha, outer=True) + turn(D, alpha)

    constraints 를 주면 그 영역 안의 호만 참여한다. 영역 밖의 호는 없는 셈 치고
    계산한다 (§7.9). 물리적 회전이 아니라 pCubes 의 Hide 와 같은 구성 장치이므로
    회전축과 영역 경계가 코축일 필요가 없다.
    """
    a = normalize(axis.normal)
    d = math.cos(math.radians(theta_deg))
    side = -1.0 if outer else 1.0
    constraints = _as_region(constraints)

    # ---- §7.1 합법성. 상태를 건드리기 전에 먼저 --------------------------
    hit = registry.find(a, d)
    if hit is None:
        raise IllegalTurnError(axis.id, "회전 경계원이 경계 집합에 없다")
    boundary_bc = hit[0]
    complete, missing = _covers(boundary_bc, constraints)
    if not complete:
        gap = sum(b - a2 for a2, b in missing)
        where = " (영역 안)" if constraints else ""
        raise IllegalTurnError(
            axis.id,
            f"회전 경계원이 완전한 cut 이 아니다{where} (빈 길이 {gap:.4f})",
        )

    result = TurnResult(
        axis_id=axis.id,
        angle_deg=angle_deg,
        carriers_before=len(registry),
        outer=outer,
    )

    angle = math.radians(angle_deg)
    if abs(math.remainder(angle, TAU)) < ANGLE_EPS:
        result.no_op = True
        result.carriers_after = len(registry)
        return result

    # ---- 1단계: 분류. 이동할 span 을 모으고 원래 자리에서 뺀다 ------------
    moving: list[tuple[BoundaryCircle, AngularSpan]] = []

    for bc in list(registry.circles):
        if not bc.spans:
            continue

        # 0단계: 경계 carrier 는 통째로 고정. 원을 자기 축으로 돌리면
        # 자기 자신이므로 결과가 같고, 호 ID 와 provenance 가 보존된다
        if bc is boundary_bc:
            continue

        # 숨은 호는 참여하지 않는다. 표시는 재료를 따라다니므로 회전이
        # 몇 번이든 정방향과 되돌리기가 같은 재료를 고른다 (§7.9)
        keep: list[AngularSpan] = list(bc.spans.hidden())
        participating = bc.spans.visible()
        if not participating:
            continue

        cls = classify_carrier(bc.circle, a, d, side)
        if cls == FIXED:
            continue
        if cls == MOVING:
            moving.extend((bc, s) for s in participating)
            bc.spans.replace_all(keep)
            continue

        # MIXED: span 단위로 본다
        for span in participating:
            scls = classify_span(bc.circle, a, d, span.t0, span.t1, side)
            if scls == FIXED:
                keep.append(span)
            elif scls == MOVING:
                moving.append((bc, span))
            else:  # STRADDLING
                result.straddling_spans += 1
                for t0, t1, is_moving in split_span_by_cap(
                    bc.circle, a, d, span.t0, span.t1, side
                ):
                    piece = span.with_range(t0, t1)
                    if is_moving:
                        moving.append((bc, piece))
                    else:
                        keep.append(piece)
        bc.spans.replace_all(keep)

    # ---- 2단계: 회전 후 재삽입 -------------------------------------------
    R = rotation_matrix(a, angle)
    for bc, span in moving:
        src = bc.circle
        n2 = R @ src.n
        h2 = src.h  # 구 중심을 지나는 회전이므로 offset 은 불변
        rotated = SphericalCircle.from_normal_offset(n2, h2)
        # 회전은 방향을 보존하므로 사상은 순수 회전 t -> t + c
        c = rotated.angle_of(R @ src.point(0.0))
        intervals = make_span(span.t0 + c, span.length)
        # 옮긴 연산만 갱신하고 출처(origin_*)는 그대로 물려준다
        moved_prov = replace(
            span.provenance, op_index=op_index, axis_id=axis.id, kind="turn"
        )
        # 영역 블록 안에서는 숨은 호가 도착지를 막지 않는다 (§7.9).
        # 숨은 재료는 치워져 있으므로 그 자리로 올 수 있다. 막으면 옮긴 호가
        # 삼켜져 사라지고, 되돌릴 때 돌아오지 않아 원래 carrier 가 뚫린다
        registry.add_coverage(
            n2, h2, intervals, moved_prov, only_visible=bool(constraints)
        )

    result.moved_spans = len(moving)
    result.moved = tuple(
        (tuple(round(x, 9) for x in bc.circle.n), round(span.t0, 9), round(span.t1, 9))
        for bc, span in moving
    )
    result.carriers_after = len(registry)
    return result
