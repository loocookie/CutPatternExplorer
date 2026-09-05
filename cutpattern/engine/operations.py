"""구성 연산과 실행기. 설계 문서 §6, §7.5, §13.

XML 의 Turn 과 사용자 조작 Turn 은 같은 evaluator 를 쓴다 (§7.5).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, replace

from ..epsilon import ANGLE_EPS, NORMAL_EPS

# 회전 상쇄 판정 허용 오차(도)
TURN_CANCEL_EPS = 1e-9
from ..geometry.angular_coverage import Coverage, difference, full
from ..geometry.conjugate import TurnFrame, pull_back_all
from ..geometry.region import Constraint, Region, covers_within, dangling_endpoints
from ..geometry.region import _add_constraint as _extend_cell
from ..geometry.registry import BoundaryRegistry
from ..geometry.span import Provenance
from ..geometry.vector import rotation_matrix
from ..geometry.spherical_circle import SphericalCircle
from .axes import Axis, PuzzleFamily
from .turn import IllegalTurnError, TurnResult, turn

__all__ = [
    "SplitByAxis",
    "plan_conjugation",
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
            f"the region boundary is not a cut yet: axis {axis_id!r} "
            f"(gap {gap:.4f}). split that axis first"
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
    # 어떤 절단도 지나가지 않는 끝점들 (§6.3). 진단으로만 남긴다.
    #
    # region 블록 **안에서는** 매달리는 것이 정상이다. 숨은 재료가 치워져
    # 있으므로 그 자리에는 절단이 없다. 블록이 끝나고 회전이 되돌아온 뒤에도
    # 매달려 있으면 그것이 진짜 결함이다. 그래서 예외로 올리지 않는다
    dangling: tuple = ()


# ---- 실행 --------------------------------------------------------------


def core_moves(d: float, outer: bool, opposed_d: float | None = None) -> bool:
    """코어가 이 회전에 실리는가 (§2.4).

    **cap 은 도는 층이고 코어는 나머지 몸통에 있다.** 그래서 `outer` 가 싣고
    cap 은 안 싣는다. 절단이 얼마나 깊든 마찬가지다 — 깊은 cap 이 원점을 삼켜도
    그것이 도는 층이라는 사실은 안 바뀐다.

    예외는 **가운데 층**이 생길 때 하나뿐이다. 같은 축선의 반대쪽 축이 있고 두
    cap 이 겹치면, 그 교집합은 두 원이 다 이 축 둘레이므로 **돌 수 있는 띠**가
    된다. 그 띠는 양쪽 모두의 cap 이라 어느 쪽도 코어를 가질 수 없다 — 그런
    퍼즐은 코어를 구형으로 만들어 띠가 그 둘레를 미끄러지게 한다. 믹스업 계열이
    이것이다.

        cap(n, theta)  겹침  cap(-n, theta')   <=>   theta + theta' > 180
                                              <=>   d + d' < 0

    `opposed_d` 는 반대쪽 축의 `cos(theta')` 다. 그런 축이 **퍼즐에** 없으면
    None 이고, 그러면 겹칠 상대가 없으므로 예외도 없다.

    반대쪽이 아닌 축의 cap 과 겹치는 것은 상관없다. 두 원의 축이 다르면 그
    교집합은 어느 축 둘레로도 안 도는 그냥 영역이라 층이 아니다.
    """
    if not outer:
        return False
    if opposed_d is None:
        return True
    return d + opposed_d >= 0.0


def opposed_cut(
    family: PuzzleFamily,
    normals: dict[str, object],
    cut_angles: dict[str, float],
    axis_id: str,
) -> float | None:
    """`axis_id` 의 **반대쪽 축**의 `cos(theta)`. 그런 축이 없으면 None (§2.4).

    가운데 층은 같은 축선의 반대쪽 cap 과 겹쳐야 생기므로, 찾는 것은 `-n`
    방향의 축이다. 다른 방향의 축은 아무리 깊어도 층을 만들지 않는다 — 두 원의
    축이 다르면 그 교집합은 어느 축 둘레로도 안 돈다.

    여럿이면 **제일 깊은 것**을 준다. 하나라도 겹치면 띠가 생기기 때문이다.

    법선은 **지금 값**으로 본다. 실려 움직인 축이 있으면 그 자리가 진실이다 —
    영역 판정이 쓰는 것과 같은 값이라야 어긋나지 않는다.
    """
    a = normals[axis_id]
    found: float | None = None
    for aset in family.axis_sets:
        theta = cut_angles[aset.cut_angle_input]
        for other in aset.axes:
            if other.id == axis_id:
                continue
            if float(a @ normals[other.id]) > -1.0 + NORMAL_EPS:
                continue
            d = math.cos(math.radians(theta))
            if found is None or d < found:
                found = d
    return found


def plan_conjugation(family: PuzzleFamily) -> dict[int, int]:
    """접합 가능한 Turn 짝을 찾는다 (§7.10, §12.3-2).

    **계획은 연산 목록만 보고 정해진다.** 절단 각도와 무관하므로 슬라이더를
    밀어도 답이 같다. 그래도 캐시하지 않는다 — 재 보니 evaluate 의 0.2% 라
    아낄 것이 없고, 공개 함수가 공유 dict 를 돌려주면 부르는 쪽이 그것을 고쳐
    캐시를 오염시킬 수 있다.

    `turned(a, θ)` 는 회전하고 자르고 정확히 되돌린다. 그 왕복의 순효과는
    `E ∪ Φ⁻¹(C)` 뿐이므로 (§7.10), 짝을 알아보면 registry 를 건드리지 않고
    새 절단만 끌어올 수 있다.

    반환값은 {여는 Turn 의 연산 번호: 닫는 Turn 의 연산 번호}.

    **증명하지 못하면 넣지 않는다.** 빠진 짝은 지금 경로로 그대로 흘러 결과가
    같고 느릴 뿐이다. 정확성이 이 함수의 완전성에 걸리지 않는다는 것이 요점이다.

    닫는 쪽은 둘이다.

    - 짝을 이루는 반대 회전. `turned()` 가 내는 모양이다
    - `RollbackTurns`. 열려 있던 회전을 역순으로 한꺼번에 되돌리므로 그 자리가
      곧 닫는 괄호다. 정의 끝에 자동으로 붙으므로 (§7.6) 맨 `turn()` 도 접합
      대상이 된다. 그러지 않으면 같은 기하를 내는 두 표기가 소스만 봐서는
      안 보이는 성능 차이를 갖는다

    지금 거부하는 것:

    - 짝 사이에 `EnterRegion` / `ExitRegion` 이 열리는 경우. 블록 **바깥의**
      영역은 괜찮다 (`Φ⁻¹(C ∩ Φ(R)) = Φ⁻¹(C) ∩ R`). 안에서 여는 것은 영역이
      회전을 따라 변환되는 경로라 따로 다뤄야 한다

    일부만 거부해도 된다. 바깥이 폴백이고 안쪽이 접합이면, registry 는 바깥
    회전이 실제로 적용된 좌표계를 들고 있고 안쪽 프레임은 그 위에서 정의되므로
    둘이 일관된다. `RollbackTurns` 는 실행된 적 없는 회전을 되돌리지 않는다 —
    접합된 회전은 `pending_turns` 에 들어가지 않기 때문이다.
    """
    pairs: dict[int, int] = {}
    # (연산 번호, 축 id, 각도, outer, 접합 가능한가)
    stack: list[list] = []

    def poison_all() -> None:
        for entry in stack:
            entry[4] = False

    for i, op in enumerate(family.operations):
        if isinstance(op, Turn):
            if (
                stack
                and stack[-1][1] == op.axis
                and stack[-1][3] == op.outer
                and abs(stack[-1][2] + op.angle) < TURN_CANCEL_EPS
            ):
                entry = stack.pop()
                if entry[4]:
                    pairs[entry[0]] = i
                continue
            ok = True
            stack.append([i, op.axis, op.angle, op.outer, ok])
        elif isinstance(op, SplitByAxis):
            continue  # 접합 대상이다
        elif isinstance(op, RollbackTurns):
            # 열려 있던 회전을 전부 여기서 닫는다 (§7.6)
            for entry in stack:
                if entry[4]:
                    pairs[entry[0]] = i
            stack.clear()
        else:
            # EnterRegion / ExitRegion / 알 수 없는 연산
            poison_all()
    return pairs


def _pulled_pieces(reg: BoundaryRegistry, circle: SphericalCircle, frames):
    """원을 회전 스택으로 끌어오고, 각 조각을 저장된 carrier 좌표로 옮긴다.

    반환은 (carrier 또는 None, 원, 구간) 목록. carrier 가 None 이면 그 자리에
    아직 아무 경계도 없다.
    """
    out = []
    for c, spans in pull_back_all(circle, frames):
        hit = reg.find(c.n, c.h)
        if hit is None:
            out.append((None, c, spans))
        else:
            bc = hit[0]
            out.append((bc, bc.circle, reg.to_carrier_frame(bc, c.n, c.h, spans)))
    return out


def is_conjugated_turn_legal(
    reg: BoundaryRegistry, normal, theta_deg: float, frames, region
) -> tuple[bool, float]:
    """회전 스택 안에서의 §7.1 합법성 판정.

    registry 는 끌어온 좌표계(원래 좌표계)의 상태를 들고 있고, 판정해야 할
    것은 회전된 상태의 경계원이다. `Φ` 가 전단사이므로 물음을 끌어와서 묻는다.

        B ⊆ Φ(E)   <=>   Φ⁻¹(B) ⊆ E

    되돌리기 쪽 판정은 하지 않는다. 경계 carrier 의 span 은 회전이 옮기지 않고
    (§7.2 0단계) 블록 안 split 은 coverage 를 더하기만 하므로, 정방향이 합법이면
    되돌리기는 반드시 합법이다 (§7.10).
    """
    d = math.cos(math.radians(theta_deg))
    circle = SphericalCircle.from_normal_offset(normal, d)
    if circle.is_degenerate():
        return True, 0.0  # 반지름 0. 경계가 없다 (§6.1)
    gap = 0.0
    for bc, c, spans in _pulled_pieces(reg, circle, frames):
        want = spans
        if region is not None:
            want, _outside = region.clip(c, want)
        if not want:
            continue
        have = [] if bc is None else (bc.visible_coverage if region is not None else bc.coverage)
        missing = [(a, b) for a, b in difference(want, have) if b - a > ANGLE_EPS]
        gap += sum(b - a for a, b in missing)
    return gap <= 0.0, gap


def conjugated_split(
    registry: BoundaryRegistry,
    axis: Axis,
    theta_deg: float,
    frames,
    op_index: int = -1,
    axis_set_id: str = "",
    constraints=None,
) -> SplitResult:
    """회전 스택 안의 split. 회전을 실행하지 않고 절단원만 끌어온다 (§7.10).

    영역은 끌어온 **뒤에** 적용한다. 실제 경로에서는 영역이 회전을 따라
    변환되므로 `C ∩ Φ(R)` 을 자르는데, 그것을 끌어오면 `Φ⁻¹(C) ∩ R` 이다.
    끌어온 좌표계에서는 영역이 변환되지 않은 원본이다.
    """
    theta = math.radians(theta_deg)
    h = math.cos(theta)
    circle = SphericalCircle.from_normal_offset(axis.normal, h)
    if circle.is_degenerate():
        # 반지름 0. 보이는 경계가 없다 (§6.1)
        return SplitResult(axis.id, -1, [])
    prov = Provenance(
        op_index=op_index,
        axis_id=axis.id,
        kind="split",
        origin_axis_set=axis_set_id,
        origin_axis=axis.id,
    )
    first_index = -1
    added_total: Coverage = []
    bad: list = []
    for c, spans in pull_back_all(circle, frames):
        tags = None
        if constraints is not None:
            spans, tags = constraints.clip_tagged(c, spans)
            if not spans:
                continue
        bc, added = registry.add_coverage(
            c.n, c.h, spans, prov, only_visible=constraints is not None
        )
        if first_index < 0:
            first_index = bc.index
        added_total.extend(added)
        if constraints is not None:
            bad.extend(dangling_endpoints(c, spans, tags, registry))
    return SplitResult(axis.id, first_index, added_total, dangling=tuple(bad))


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
        return SplitResult(axis.id, -1, [])
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
        raise ValueError(f"on_illegal must be 'raise' or 'truncate', got {on_illegal!r}")

    # 각도를 진입 시점에 고정한다. operation 마다 다시 조회하므로, 실행 도중
    # 호출자가 값을 바꾸면 앞 연산은 theta1 로 split 하고 뒤 Turn 은 theta2 의
    # 경계원을 찾게 되어 합법인 회전이 불법으로 판정된다. UI 위젯 콜백이 별도
    # 스레드에서 오는 환경에서 실제로 발생한다.
    cut_angles = dict(cut_angles)
    reg = registry if registry is not None else BoundaryRegistry()
    log: list[SplitResult | TurnResult | Truncated] = []
    pending_turns: list[tuple[Axis, float, float, bool]] = []

    # 접합 계획 (§7.10). 증명된 짝만 들어 있고, 나머지는 지금 경로로 흐른다.
    # registry 는 항상 **끌어온 좌표계**(회전 이전)의 상태를 들고 있다
    conj_open = plan_conjugation(family)
    frames: list[TurnFrame] = []
    # 각 프레임을 닫는 연산 번호. 반대 회전일 수도 RollbackTurns 일 수도 있다
    frame_close: list[int] = []
    # 프레임을 연 회전. 닫을 때 실림을 되돌리는 데 쓴다 (§7.10)
    frame_turn: list[tuple[Axis, str, float, float, bool]] = []
    # 얹힌 집합이 하나라도 있는가. 없으면 코어 규칙만 보면 된다
    any_attached = any(s.attached is not None for s in family.axis_sets)

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

    def apply_carry(
        axis: Axis, turn_set_id: str, theta: float, angle_deg: float, outer: bool
    ) -> None:
        """회전한 재료에 얹힌 축들을 함께 돌린다 (§2.4).

        어느 축이 실리는지는 마운트(`attached`)와 위치가 정한다. 코어에 얹힌
        축은 코어가 움직일 때 돌고 (§2.4 "코어는 어디에 있나"), 어떤 집합에
        얹힌 축은 그 집합의 회전 영역 안에 있을 때 돈다.
        """
        d = math.cos(math.radians(theta))
        core_in_region = core_moves(
            d, outer,
            opposed_cut(family, normals, cut_angles, axis.id) if outer else None,
        )
        # 실릴 것이 아예 없으면 훑지 않는다. 얹힌 집합이 하나도 없는 정의
        # (지금 예제 전부)에서 코어가 안 움직이면 이 회전은 아무것도 안 옮긴다
        if not core_in_region and not any_attached:
            return
        a = normals[axis.id]
        matrix = rotation_matrix(a, math.radians(angle_deg))
        for other_set in family.axis_sets:
            for other in other_set.axes:
                if other.id == axis.id:
                    continue        # 회전축 자신은 이 회전에 불변이다
                value = float(a @ normals[other.id])
                in_region = (value < d) if outer else (value > d)
                if family.is_carried(
                    other_set.id, turn_set_id, outer=outer,
                    in_region=in_region, core_in_region=core_in_region,
                ):
                    normals[other.id] = matrix @ normals[other.id]
    for i, op in enumerate(family.operations):
        if isinstance(op, SplitByAxis):
            aset, axis = family.find_axis(op.axis)
            theta = cut_angles[aset.cut_angle_input]
            if frames:
                log.append(
                    conjugated_split(
                        reg, current(axis), theta, frames, i, aset.id, active_region()
                    )
                )
            else:
                log.append(
                    split_by_axis(reg, current(axis), theta, i, aset.id, active_region())
                )
        elif isinstance(op, Turn):
            aset, axis = family.find_axis(op.axis)
            theta = cut_angles[aset.cut_angle_input]
            if i in conj_open:
                # 접합. 회전을 실행하지 않고 스택에만 쌓는다 (§7.10).
                # 판정은 그대로 한다 — 정방향 하나면 되돌리기까지 보장된다
                ok, gap = is_conjugated_turn_legal(
                    reg, normals[axis.id], theta, frames, active_region()
                )
                if not ok:
                    where = " (within the region)" if active_region() else ""
                    reason = f"the turn boundary circle is not a complete cut{where} (gap {gap:.4f})"
                    if on_illegal == "raise":
                        raise IllegalTurnError(axis.id, reason)
                    log.append(
                        Truncated(
                            op_index=i,
                            axis_id=axis.id,
                            reason=reason,
                            remaining=len(family.operations) - i,
                        )
                    )
                    return reg, log
                frames.append(
                    TurnFrame.make(normals[axis.id], theta, op.angle, op.outer)
                )
                frame_close.append(conj_open[i])
                frame_turn.append((axis, aset.id, theta, op.angle, op.outer))
                # 접합해도 실림은 실제로 일어난다 (§2.4). registry 만 끌어온
                # 좌표계에 남고, 축 법선은 전역이 진실이다 — 그래야 블록 안
                # split 이 옮겨진 법선을 쓰고 pull_back 이 제자리로 끌어온다
                apply_carry(axis, aset.id, theta, op.angle, op.outer)
                log.append(
                    TurnResult(
                        axis_id=axis.id,
                        angle_deg=op.angle,
                        outer=op.outer,
                        conjugated=True,
                        carriers_before=len(reg),
                        carriers_after=len(reg),
                    )
                )
                continue
            if frame_close and frame_close[-1] == i:
                frames.pop()
                frame_close.pop()
                frame_turn.pop()
                # 이 op 자체가 반대 회전이므로 그대로 실으면 풀린다. 회전이
                # 축 둘레라 a . (R n) = a . n 이고, 그래서 영역 판정이 실림에
                # 불변이다 — 실렸던 것과 정확히 같은 집합이 되돌아간다
                apply_carry(axis, aset.id, theta, op.angle, op.outer)
                log.append(
                    TurnResult(
                        axis_id=axis.id,
                        angle_deg=op.angle,
                        outer=op.outer,
                        conjugated=True,
                        carriers_before=len(reg),
                        carriers_after=len(reg),
                    )
                )
                continue
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
                apply_carry(axis, aset.id, theta, op.angle, op.outer)
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
                raise ValueError(f"operation #{i}: unmatched ExitRegion")
            depth = len(region_stack) - 1
            region_stack.pop()
            mark = region_marks.pop()
            for bc in reg.circles:
                for span in bc.spans:
                    if span.hidden_at == depth:
                        span.hidden_at = None
            if len(pending_turns) != mark:
                raise ValueError(
                    f"operation #{i}: a turn inside the region block was not undone. "
                    "turns inside a region must be paired (use turned)"
                )
        elif isinstance(op, RollbackTurns):
            # 접합된 회전은 실행된 적이 없으므로 되돌릴 것도 없다. 프레임만
            # 걷어낸다 (§7.10). pending_turns 에는 폴백으로 실제 실행된 것만
            # 들어 있으므로 아래 되돌리기는 그것들만 다룬다
            while frame_close and frame_close[-1] == i:
                frames.pop()
                frame_close.pop()
                f_axis, f_set, f_theta, f_angle, f_outer = frame_turn.pop()
                apply_carry(f_axis, f_set, f_theta, -f_angle, f_outer)
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
                    apply_carry(
                        axis, family.find_axis(axis.id)[0].id, theta, -angle, outer
                    )
                except IllegalTurnError as exc:
                    if on_illegal == "raise":
                        raise
                    log.append(
                        Truncated(
                            op_index=i,
                            axis_id=axis.id,
                            reason=f"rollback failed: {exc.reason}",
                            remaining=len(family.operations) - i,
                        )
                    )
                    failed = True
                    break
            pending_turns.clear()
            if failed:
                return reg, log
        else:
            raise TypeError(f"unknown operation: {op!r}")
    return reg, log
