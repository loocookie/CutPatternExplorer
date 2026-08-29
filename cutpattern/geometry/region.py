"""영역 제약. 설계 문서 §6.3, §7.9.

영역은 **절단원 하나와 그 어느 쪽**들의 교집합이다. 회전 영역과 같은 원시
개념이므로(§2.3) 분류 코드를 그대로 쓴다.

영역은 물리적 제약이 아니라 **구성 장치**다. pCubes 의 `Hide` 와 같다.

    Hide Ax1 Layer 0        정지 재료를 잠시 치운다
    Hide Ax1 Layer 2
    Turn Ax2 ...            남은 것만 돌리고
    SplitByAxes             남은 것만 자른 뒤
    Undo / Undo / ShowAll   되돌리고 복구한다

그래서 영역 안의 회전은 "그 영역이 물리적으로 돌아간다"는 뜻이 아니다. 영역
밖의 호는 없는 셈 치고 계산할 뿐이다. 회전축과 영역 경계가 코축일 필요도 없다.
OctoCube Master 가 바로 그 경우로, `Hide` 축과 `Turn` 축이 직교한다.

영역은 회전과 함께 변환된다
---------------------------
`Hide` 는 조각의 속성이라 조각이 돌아가도 따라다닌다. 영역을 공간에 고정된
기하 필터로만 두면, 회전이 재료를 영역 밖으로 밀어내는 순간 그 재료를 다시
찾을 수 없다.

가시 영역은 2차원이지만 항상 **반공간 교집합(셀)들의 합집합**으로 쓸 수 있다.
회전은 각 셀을 회전 경계로 둘로 쪼개고 안쪽 셀만 돌린다. 그러면 호는 자동으로
따라간다. 셀은 회전마다 최대 두 배가 되지만, 모순된 셀(같은 원의 양쪽을 동시에
요구)은 즉시 버린다.

경계가 반드시 기존 절단원이라는 점은 그대로 중요하다. 부분 절단은 어딘가에서
끝나야 하는데 아무 데서나 끝나면 면 한가운데 매달린 모서리가 생긴다. 영역을
절단원의 반공간 교집합으로 정의하면 잘리는 지점이 정의상 기존 절단원 위이므로
그 조건이 자동으로 만족된다.
"""

from __future__ import annotations

from dataclasses import dataclass

from ..epsilon import ANGLE_EPS, SEL_EPS
from .angular_coverage import Coverage, difference, is_full, normalize_spans
from .classify import MOVING, STRADDLING, classify_span, split_span_by_cap
from .spherical_circle import SphericalCircle
from .vector import Vec3, as_vec

__all__ = [
    "Constraint",
    "Region",
    "clip",
    "split_by_region",
    "covers_within",
    "dangling_endpoints",
]


@dataclass(frozen=True)
class Constraint:
    """절단원 하나의 한쪽.

    normal, offset 이 경계 절단원이고 side 는 +1 이면 안쪽(cap), -1 이면 바깥쪽.
    axis_id 는 진단용이다.
    """

    axis_id: str
    normal: Vec3
    offset: float
    side: float

    def contains(self, point) -> bool:
        n = self.normal
        value = point[0] * n[0] + point[1] * n[1] + point[2] * n[2] - self.offset
        return self.side * value > -SEL_EPS

    def __str__(self) -> str:
        return f"{'inside' if self.side > 0 else 'outside'}({self.axis_id})"


def split_by_region(
    circle: SphericalCircle, spans: Coverage, constraint: Constraint
) -> tuple[Coverage, Coverage]:
    """구간들을 제약 안쪽과 바깥쪽으로 나눈다.

    자르는 지점은 정의상 경계 절단원 위다.
    """
    inside: Coverage = []
    outside: Coverage = []
    for t0, t1 in spans:
        cls = classify_span(circle, constraint.normal, constraint.offset, t0, t1, constraint.side)
        if cls == MOVING:
            inside.append((t0, t1))
        elif cls == STRADDLING:
            for s, e, is_in in split_span_by_cap(
                circle, constraint.normal, constraint.offset, t0, t1, constraint.side
            ):
                (inside if is_in else outside).append((s, e))
        else:
            outside.append((t0, t1))
    return normalize_spans(inside), normalize_spans(outside)


def clip(
    circle: SphericalCircle, spans: Coverage, constraints
) -> tuple[Coverage, Coverage]:
    """모든 제약을 만족하는 부분과 나머지로 나눈다.

    반환값은 (영역 안, 영역 밖). 둘을 합치면 원래 구간과 같다.
    """
    inside = normalize_spans(spans)
    outside: Coverage = []
    for c in constraints:
        inside, dropped = split_by_region(circle, inside, c)
        outside.extend(dropped)
        if not inside:
            break
    return inside, normalize_spans(outside)


def covers_within(
    circle: SphericalCircle, coverage: Coverage, constraints
) -> tuple[bool, Coverage]:
    """영역 안에서 이 원이 빈틈없이 덮였는가.

    영역이 없으면 2pi 전체 판정으로 환원된다. Turn 합법성의 일반형이다 (§7.1).
    반환값은 (완전한가, 비어 있는 구간).
    """
    if not constraints:
        return is_full(coverage), difference([(0.0, 6.283185307179586)], coverage)
    wanted, _ = clip(circle, [(0.0, 6.283185307179586)], constraints)
    if not wanted:
        return True, []  # 영역이 이 원에 닿지 않는다. 제약할 것이 없다
    missing = difference(wanted, coverage)
    missing = [(a, b) for a, b in missing if b - a > ANGLE_EPS]
    return not missing, missing


def dangling_endpoints(circle: SphericalCircle, spans: Coverage, tags, registry):
    """영역 경계에서 잘린 끝점 중 **어떤 절단도 지나가지 않는** 것들.

    부분 절단은 다른 절단 위에서 끝나야 한다. 그렇지 않으면 면 한가운데
    매달린 모서리가 생긴다.

    어느 제약이 잘랐는지로 보지 않고 registry 전체를 본다. 회전을 거치면
    영역 제약의 원과 실제 절단이 부분적으로만 겹치므로, 제약별로 보면
    오탐이 난다. 판정에 필요한 것은 "그 점에 절단이 있는가" 하나뿐이다.

    seam(0 / 2pi)에서 갈라진 끝점은 자른 제약이 없으므로 제외된다.
    """
    from .angular_coverage import contains

    bad = []
    for t0, t1 in spans:
        for t in (t0, t1):
            if tags.get(round(t, 9)) is None:
                continue  # 자른 제약이 없다. seam 에서 갈라진 끝점
            point = circle.point(t)
            covered = False
            for bc in registry.non_empty():
                if abs((point @ bc.circle.n) - bc.circle.h) > 1e-9:
                    continue
                if contains(bc.coverage, bc.circle.angle_of(point)):
                    covered = True
                    break
            if not covered:
                bad.append((t, tags[round(t, 9)], point))
    return bad


class Region:
    """가시 영역. 셀(반공간 교집합)들의 합집합.

    회전과 함께 변환되므로 Hide 와 같이 재료를 따라다닌다. 셀의 합집합이므로
    non-convex 도 non-connected 도 그대로 표현된다.
    """

    __slots__ = ("cells",)

    def __init__(self, cells=None) -> None:
        self.cells: list[tuple[Constraint, ...]] = [tuple(c) for c in (cells or [])]

    @classmethod
    def whole_sphere(cls) -> "Region":
        return cls([()])

    def __bool__(self) -> bool:
        return bool(self.cells)

    def __len__(self) -> int:
        return len(self.cells)

    def __repr__(self) -> str:
        inner = [", ".join(str(c) for c in cell) or "전체" for cell in self.cells]
        return f"Region({inner})"

    def clip(self, circle: SphericalCircle, spans: Coverage):
        """영역 안과 밖으로 나눈다."""
        from .angular_coverage import difference

        inside, _tags = self.clip_tagged(circle, spans)
        return inside, difference(normalize_spans(spans), inside)

    def clip_tagged(self, circle: SphericalCircle, spans: Coverage):
        """clip 과 같되, 각 끝점을 자른 제약을 함께 돌려준다.

        원래 구간의 끝점에는 태그를 달지 않는다. 그래야 seam 에서 갈라진
        끝점이 매달림 판정에서 빠진다.
        """
        from .angular_coverage import union

        original = {round(t, 9) for span in normalize_spans(spans) for t in span}
        inside: Coverage = []
        tags: dict[float, Constraint] = {}
        for cell in self.cells:
            kept = normalize_spans(spans)
            cell_tags: dict[float, Constraint] = {}
            for c in cell:
                kept, _dropped = split_by_region(circle, kept, c)
                for span in kept:
                    for t in span:
                        key = round(t, 9)
                        if key not in original and key not in cell_tags:
                            cell_tags[key] = c
                if not kept:
                    break
            if kept:
                inside = union(inside, kept)
                tags.update(cell_tags)
        return inside, tags

    def turned(self, axis_normal, offset: float, side: float, matrix) -> "Region":
        """회전 뒤의 영역.

        각 셀을 회전 경계로 둘로 쪼개고, 도는 쪽(side)만 행렬을 적용한다.
        """
        n = as_vec(axis_normal)
        boundary_in = Constraint("<turn>", n, offset, side)
        boundary_out = Constraint("<turn>", n, offset, -side)
        out: list[tuple[Constraint, ...]] = []
        for cell in self.cells:
            moving = _add_constraint(cell, boundary_in)
            if moving is not None:
                out.append(tuple(_rotated(c, matrix) for c in moving))
            staying = _add_constraint(cell, boundary_out)
            if staying is not None:
                out.append(staying)
        return Region(out)


def _rotated(c: Constraint, matrix) -> Constraint:
    return Constraint(c.axis_id, matrix @ c.normal, c.offset, c.side)


def _aligned(c: Constraint, reference_normal):
    """제약을 기준 법선 방향으로 환산한 (offset, side). 다른 방향이면 None.

    (n, d, side) 와 (-n, -d, -side) 는 같은 반공간이다. 이걸 못 알아보면
    모순된 셀(같은 축의 반대쪽 두 cap)이 살아남아 회전을 두 번 먹는다.
    """
    n = c.normal
    dot = reference_normal[0] * n[0] + reference_normal[1] * n[1] + reference_normal[2] * n[2]
    if abs(dot - 1.0) < 1e-9:
        return c.offset, c.side
    if abs(dot + 1.0) < 1e-9:
        return -c.offset, -c.side
    return None


def _add_constraint(cell, new: Constraint):
    """셀에 제약을 더한다. 모순되면 None (빈 셀).

    같은 법선 방향의 제약들은 구간 [lo, hi] 로 접는다. lo > hi 면 빈 셀이다.
    """
    lo, hi = -2.0, 2.0
    same: list[int] = []
    for i, c in enumerate(cell):
        got = _aligned(c, new.normal)
        if got is None:
            continue
        same.append(i)
        d, side = got
        if side > 0:
            lo = max(lo, d)
        else:
            hi = min(hi, d)
    if new.side > 0:
        lo = max(lo, new.offset)
    else:
        hi = min(hi, new.offset)
    if lo > hi + 1e-12:
        return None  # 같은 축의 양쪽을 동시에 요구한다
    if same and all(
        _aligned(cell[i], new.normal) == (new.offset, new.side) for i in same
    ):
        return cell  # 이미 있다
    return (*cell, new)
