"""구성 연산과 실행기. 설계 문서 §6, §7.5, §13.

XML 의 Turn 과 사용자 조작 Turn 은 같은 evaluator 를 쓴다 (§7.5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..epsilon import RADIUS_EPS

# 회전 상쇄 판정 허용 오차(도)
TURN_CANCEL_EPS = 1e-9
from ..geometry.angular_coverage import Coverage, full
from ..geometry.region import Constraint, Region, covers_within, dangling_endpoints
from ..geometry.region import _add_constraint as _extend_cell
from ..geometry.registry import BoundaryRegistry
from ..geometry.span import Provenance
from ..geometry.vector import rotation_matrix
from ..geometry.spherical_circle import SphericalCircle
from .axes import Axis, AxisSet, PuzzleFamily
from .turn import IllegalTurnError, TurnResult, turn

__all__ = [
    "SplitByAxis",
    "Turn",
    "RollbackTurns",
    "EnterRegion",
    "ExitRegion",
    "SplitResult",
    "TurnResult",
    "Truncated",
    "UncutBoundaryError",
    "IllegalTurnError",
    "split_by_axis",
    "evaluate",
]


# ---- 연산 --------------------------------------------------------------


@dataclass(frozen=True)
class SplitByAxis:
    """축 하나로만 split.

    활성 영역이 있으면 절단원 중 그 영역 안의 부분만 추가한다 (§6.3).
    """

    axis: str


@dataclass(frozen=True)
class Turn:
    """축의 절단원 한쪽을 angle(도)만큼 회전 (§7).

    outer=False  cap        0 ~ theta
    outer=True   complement theta ~ 180

    slice 회전은 둘의 합성이다. 별도 원시 연산을 두지 않는다.
    """

    axis: str
    angle: float
    outer: bool = False


@dataclass(frozen=True)
class RollbackTurns:
    """여기까지 실행한 Turn 들을 역순으로 되돌린다.

    구성용 회전과 그 결과 생긴 split 을 분리해서 보기 위한 것이다. U 를 45도
    돌려 R split 을 만든 뒤 되돌리면, 원래 6개 원이 제자리로 돌아오고 새로
    생긴 경계만 남는다. 초기 상태와의 차이가 바로 보인다.

    split 은 coverage 를 추가하기만 하므로, 되돌리는 회전은 원래 회전이
    합법이었다면 대체로 합법이다. 그래도 §7.1 판정은 그대로 거친다.
    """


@dataclass(frozen=True)
class EnterRegion:
    """가시 영역을 좁힌다. (축 id, side) 쌍들 (§6.3, §7.9).

    블록 경계가 연산 목록에 명시적으로 들어간다. 그래야 영역이 회전을 따라
    변환되는 것을 replay 로 재현할 수 있다.
    """

    constraints: tuple[tuple[str, float], ...]


@dataclass(frozen=True)
class ExitRegion:
    """직전 EnterRegion 을 되돌린다."""


class UncutBoundaryError(Exception):
    """region 의 경계가 아직 절단이 아니다 (§6.3).

    영역 제한 split 은 경계에서 잘린다. 그 자리에 절단이 없으면 잘린 끝이
    아무 데도 닿지 않아 면 한가운데 매달린 모서리가 남는다. 블록이 끝나고
    회전이 되돌아온 뒤에도 남는 진짜 결함이다.

    경계를 먼저 split 하면 된다. Turn 합법성(§7.1)과 같은 성격의 사전 판정이고,
    같은 covers_within 으로 본다 — 셀을 실제로 가르는 부분만 요구한다.
    """

    def __init__(self, axis_id: str, gap: float) -> None:
        super().__init__(
            f"영역 경계가 아직 절단이 아니다: 축 {axis_id!r} "
            f"(빈 길이 {gap:.4f}). 그 축을 먼저 split 해야 한다"
        )
        self.axis_id = axis_id
        self.gap = gap


@dataclass(frozen=True)
class Truncated:
    """불법 Turn 을 만나 실행을 중단한 지점 (§13.1).

    이후 연산은 버리지 않고 비활성으로 남긴다. cut angle 을 되돌리면 다시
    합법이 되어 복원된다.
    """

    op_index: int
    axis_id: str
    reason: str
    remaining: int


@dataclass(frozen=True)
class SplitResult:
    axis_id: str
    carrier_index: int
    added: Coverage
    skipped_degenerate: bool = False
    # 어떤 절단도 지나가지 않는 끝점들 (§6.3). 진단으로만 남긴다.
    #
    # region 블록 **안에서는** 매달리는 것이 정상이다. 숨은 재료가 치워져
    # 있으므로 그 자리에는 절단이 없다. 블록이 끝나고 회전이 되돌아온 뒤에도
    # 매달려 있으면 그것이 진짜 결함이다. 그래서 예외로 올리지 않는다
    dangling: tuple = ()


# ---- 실행 --------------------------------------------------------------


def split_by_axis(
    registry: BoundaryRegistry,
    axis: Axis,
    theta_deg: float,
    op_index: int = -1,
    axis_set_id: str = "",
    constraints=None,
) -> SplitResult:
    """절단 원 전체를 후보로 만들고, 아직 덮이지 않은 구간만 추가한다.

    다른 원과의 교점을 전혀 계산하지 않는다 (§6.2). constraints 를 주면 그 영역
    안의 부분만 추가한다 (§6.3). 잘리는 지점이 아직 cut 이 아니면 매달린 절단이
    되므로 거부한다.
    """
    bad: list = []
    theta = math.radians(theta_deg)
    h = math.cos(theta)
    circle = SphericalCircle.from_normal_offset(axis.normal, h)
    if circle.is_degenerate():
        # 반지름 0. 보이는 경계가 없다 (§6.1)
        return SplitResult(axis.id, -1, [], skipped_degenerate=True)
    prov = Provenance(
        op_index=op_index,
        axis_id=axis.id,
        kind="split",
        origin_axis_set=axis_set_id,
        origin_axis=axis.id,
    )
    spans = full()
    if constraints is not None:
        spans, tags = constraints.clip_tagged(circle, spans)
        if not spans:
            return SplitResult(axis.id, -1, [])
    bc, added = registry.add_coverage(
        axis.normal, h, spans, prov, only_visible=constraints is not None
    )
    if constraints is not None:
        bad = dangling_endpoints(circle, spans, tags, registry)
    return SplitResult(axis.id, bc.index, added, dangling=tuple(bad))


def evaluate(
    family: PuzzleFamily,
    cut_angles: dict[str, float],
    registry: BoundaryRegistry | None = None,
    on_illegal: str = "raise",
) -> tuple[BoundaryRegistry, list["SplitResult | TurnResult | Truncated"]]:
    """family operations 를 순서대로 실행한다.

    cut_angles 는 입력 식별자 -> 각반경(도). 범위는 (0, 180).
    진입 시점에 복사하므로 실행 도중 호출자가 바꿔도 한 번의 평가는 일관된다.

    on_illegal:
        "raise"    — 불법 Turn 에서 IllegalTurnError 를 올린다 (기본)
        "truncate" — 불법이 되기 직전 상태에서 멈추고 Truncated 를 기록한다.
                     slider 를 움직이는 동안 family Turn 이 불법이 될 수 있으므로
                     UI 는 이쪽을 쓴다 (§13.2).

    IllegalTurnError 와 UncutBoundaryError 가 둘 다 이 정책을 탄다. 어느 쪽도
    각도의 함수라, 합법이던 정의가 슬라이더를 미는 것만으로 불법이 된다.
    """
    if on_illegal not in ("raise", "truncate"):
        raise ValueError(f"on_illegal 은 'raise' 또는 'truncate' (받은 값: {on_illegal!r})")

    # 각도를 진입 시점에 고정한다. operation 마다 다시 조회하므로, 실행 도중
    # 호출자가 값을 바꾸면 앞 연산은 theta1 로 split 하고 뒤 Turn 은 theta2 의
    # 경계원을 찾게 되어 합법인 회전이 불법으로 판정된다. UI 위젯 콜백이 별도
    # 스레드에서 오는 환경에서 실제로 발생한다.
    cut_angles = dict(cut_angles)
    reg = registry if registry is not None else BoundaryRegistry()
    log: list[SplitResult | TurnResult | Truncated] = []
    pending_turns: list[tuple[Axis, float, float, bool]] = []

    # 축 법선은 런타임 상태다. 실림이 선언된 축은 회전과 함께 움직인다 (§2.1).
    # 정의(PuzzleFamily)는 초기 위치만 들고 있고, 각도가 바뀌면 처음부터 다시
    # 실행되므로 결정적이다.
    normals = {a.id: a.normal for aset in family.axis_sets for a in aset.axes}

    def current(axis: Axis) -> Axis:
        return replace(axis, normal=normals[axis.id])

    # 가시 영역 스택. 회전마다 모든 층이 함께 변환된다 (§7.9)
    region_stack: list[Region] = []
    region_marks: list[int] = []

    def make_constraints(spec) -> tuple:
        out = []
        for axis_id, side in spec:
            aset, _bound = family.find_axis(axis_id)
            theta = float(cut_angles[aset.cut_angle_input])
            out.append(
                Constraint(
                    axis_id=axis_id,
                    normal=normals[axis_id],
                    offset=math.cos(math.radians(theta)),
                    side=float(side),
                )
            )
        return tuple(out)

    def check_region_boundaries(cells) -> None:
        """셀들의 경계가 전부 실제 절단 위에 있는가 (§6.3).

        한 경계가 셀을 가르는 부분은 **같은 셀의 나머지 제약**으로 잘린 부분
        뿐이다. 원 전체를 요구하면 멀쩡한 정의가 거부된다.
        """
        for cell in cells:
            for k, c in enumerate(cell):
                others = tuple(o for j, o in enumerate(cell) if j != k)
                hit = reg.find(c.normal, c.offset)
                if hit is not None:
                    circle, coverage = hit[0].circle, hit[0].visible_coverage
                else:
                    circle, coverage = (
                        SphericalCircle.from_normal_offset(c.normal, c.offset),
                        [],
                    )
                if circle.is_degenerate():
                    continue  # 반지름 0. 가르는 경계가 없다 (§6.1)
                ok, missing = covers_within(circle, coverage, others)
                if not ok:
                    raise UncutBoundaryError(
                        c.axis_id, sum(b - a for a, b in missing)
                    )

    def active_region():
        return region_stack[-1] if region_stack else None

    def apply_carry(axis: Axis, angle_deg: float) -> None:
        carried = family.carried_by(axis.id)
        if not carried:
            return
        matrix = rotation_matrix(normals[axis.id], math.radians(angle_deg))
        for other in carried:
            normals[other] = matrix @ normals[other]
    for i, op in enumerate(family.operations):
        if isinstance(op, SplitByAxis):
            aset, axis = family.find_axis(op.axis)
            theta = cut_angles[aset.cut_angle_input]
            log.append(
                split_by_axis(reg, current(axis), theta, i, aset.id, active_region())
            )
        elif isinstance(op, Turn):
            aset, axis = family.find_axis(op.axis)
            theta = cut_angles[aset.cut_angle_input]
            try:
                log.append(
                    turn(
                        reg,
                        current(axis),
                        theta,
                        op.angle,
                        i,
                        op.outer,
                        active_region(),
                    )
                )
                apply_carry(axis, op.angle)
                if region_stack:
                    a = normals[axis.id]
                    d = math.cos(math.radians(theta))
                    matrix = rotation_matrix(a, math.radians(op.angle))
                    side = -1.0 if op.outer else 1.0
                    for k, r in enumerate(region_stack):
                        region_stack[k] = r.turned(a, d, side, matrix)
                # 되돌려야 할 회전 스택. 직전에 쌓인 것을 정확히 상쇄하면
                # 밀어넣지 않고 뺀다. turned() 블록처럼 중간에 split 이 끼어도
                # LIFO 로 짝이 맞으므로 RollbackTurns 가 헛일을 하지 않는다.
                if (
                    pending_turns
                    and pending_turns[-1][0].id == axis.id
                    and pending_turns[-1][3] == op.outer
                    and abs(pending_turns[-1][2] + op.angle) < TURN_CANCEL_EPS
                ):
                    pending_turns.pop()
                else:
                    pending_turns.append((axis, theta, op.angle, op.outer))
            except IllegalTurnError as exc:
                if on_illegal == "raise":
                    raise
                log.append(
                    Truncated(
                        op_index=i,
                        axis_id=axis.id,
                        reason=exc.reason,
                        remaining=len(family.operations) - i,
                    )
                )
                return reg, log
        elif isinstance(op, EnterRegion):
            cells = make_constraints(op.constraints)
            base = active_region() or Region.whole_sphere()
            merged = []
            for cell in base.cells:
                out = cell
                for c in cells:
                    out = _extend_cell(out, c)
                    if out is None:
                        break
                if out is not None:
                    merged.append(out)
            try:
                check_region_boundaries(merged)
            except UncutBoundaryError as exc:
                # 불법 Turn 과 같은 정책을 탄다 (§13.2). 경계가 절단인지는 cut
                # angle 에 따라 달라지므로, 슬라이더를 미는 것만으로 합법이던
                # 정의가 불법이 될 수 있다. 여기서 예외를 그대로 올리면 뷰어의
                # 재생성 루프가 죽고, 각도를 되돌려도 복원할 앱이 남지 않는다
                if on_illegal == "raise":
                    raise
                log.append(
                    Truncated(
                        op_index=i,
                        axis_id=exc.axis_id,
                        reason=str(exc),
                        remaining=len(family.operations) - i,
                    )
                )
                return reg, log
            new_region = Region(merged)
            depth = len(region_stack)
            region_stack.append(new_region)
            region_marks.append(len(pending_turns))
            # 보이는 호를 영역으로 잘라 바깥쪽에 표시를 단다
            for bc in reg.circles:
                if not bc.spans:
                    continue
                rebuilt = []
                for span in list(bc.spans):
                    if not span.visible:
                        rebuilt.append(span)
                        continue
                    ins, outs = new_region.clip(bc.circle, [span.as_tuple()])
                    rebuilt.extend(span.with_range(t0, t1) for t0, t1 in ins)
                    for t0, t1 in outs:
                        piece = span.with_range(t0, t1)
                        piece.hidden_at = depth
                        rebuilt.append(piece)
                bc.spans.replace_all(rebuilt)
        elif isinstance(op, ExitRegion):
            if not region_stack:
                raise ValueError(f"연산 #{i}: 짝 없는 ExitRegion")
            depth = len(region_stack) - 1
            region_stack.pop()
            mark = region_marks.pop()
            for bc in reg.circles:
                for span in bc.spans:
                    if span.hidden_at == depth:
                        span.hidden_at = None
            if len(pending_turns) != mark:
                raise ValueError(
                    f"연산 #{i}: 영역 블록 안의 회전이 되돌려지지 않았다. "
                    "영역 회전은 블록 안에서 짝을 맞춰야 한다 (turned 를 쓴다)"
                )
        elif isinstance(op, RollbackTurns):
            failed = False
            for axis, theta, angle, outer in reversed(pending_turns):
                try:
                    log.append(
                        turn(
                            reg,
                            current(axis),
                            theta,
                            -angle,
                            i,
                            outer,
                            None,
                        )
                    )
                    apply_carry(axis, -angle)
                except IllegalTurnError as exc:
                    if on_illegal == "raise":
                        raise
                    log.append(
                        Truncated(
                            op_index=i,
                            axis_id=axis.id,
                            reason=f"되돌리기 실패: {exc.reason}",
                            remaining=len(family.operations) - i,
                        )
                    )
                    failed = True
                    break
            pending_turns.clear()
            if failed:
                return reg, log
        else:
            raise TypeError(f"알 수 없는 연산: {op!r}")
    return reg, log
