"""carrier 원 registry. 설계 문서 §4.3, §7.4.

핵심 두 가지
------------
1. **양방향 키 조회** — 법선 부호를 정규화하지 않는다. 정규화는 |n_x| ~ eps
   근처에서 뒤집혀 키가 불안정해진다. 대신 ``(n, h)`` 와 ``(-n, -h)`` 를 모두
   조회한다. 2x2x2 를 면 6축 theta=90 으로 정의하면 U 축과 D 축이 같은 평면
   y=0 을 만드는데, 이를 병합하지 않으면 coverage 가 두 carrier 로 쪼개져
   Turn 합법성 판정이 오작동한다 (§4.3).

2. **최근접 조회 + 스냅** — 회전 결과 법선은 부동소수 오차를 안는다.
   R_u90 · (1,0,0) = (1.11e-16, 0, -1.0) 이라 정확 해시로는 기존 (0,0,-1) 을
   못 찾는다. 격자 버킷 + 인접 셀 탐색으로 최근접을 찾고, 찾으면 계산된 값을
   버리고 **registry 에 이미 있는 값을 그대로 쓴다**. 오차가 매번 리셋되어
   누적되지 않는다 (§7.4).
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field

import numpy as np

from ..epsilon import ANGLE_EPS, MERGE_EPS
from .angular_coverage import Coverage, difference, is_full
from .span import ROOT, AngularSpan, Provenance, SpanList
from .spherical_circle import SphericalCircle, transfer_spans
from .vector import normalize

__all__ = ["BoundaryCircle", "BoundaryRegistry"]

_NEIGHBORS = tuple(itertools.product((-1, 0, 1), repeat=4))


@dataclass
class BoundaryCircle:
    """하나의 carrier 원과 그 위의 현재 span 들."""

    index: int
    circle: SphericalCircle
    spans: SpanList = field(default_factory=SpanList)

    @property
    def coverage(self) -> Coverage:
        """병합된 구간 view. 집합 판정은 전부 이걸 쓴다."""
        return self.spans.intervals()

    @property
    def visible_coverage(self) -> Coverage:
        """보이는 호만 모은 구간 (§7.9)."""
        return self.spans.visible_intervals()

    @property
    def is_complete(self) -> bool:
        """원 전체가 덮였는가. Turn 합법성 판정의 본체 (§7.1)."""
        return is_full(self.coverage)

    def subtract(self, intervals: Coverage) -> None:
        """구간을 제거한다. 남은 조각은 provenance 를 물려받는다."""
        out: list[AngularSpan] = []
        for s in self.spans:
            for t0, t1 in difference([s.as_tuple()], intervals):
                if t1 - t0 > ANGLE_EPS:
                    out.append(s.with_range(t0, t1))
        self.spans.replace_all(out)

    def __bool__(self) -> bool:
        return True


class BoundaryRegistry:
    """(n, h) 로 carrier 를 찾고 병합하는 저장소."""

    def __init__(self, merge_eps: float = MERGE_EPS) -> None:
        self.merge_eps = merge_eps
        self.circles: list[BoundaryCircle] = []
        self._buckets: dict[tuple[int, int, int, int], list[int]] = {}

    # ---- 내부 -----------------------------------------------------------

    def _cell(self, n: np.ndarray, h: float) -> tuple[int, int, int, int]:
        e = self.merge_eps
        return (
            int(np.floor(n[0] / e)),
            int(np.floor(n[1] / e)),
            int(np.floor(n[2] / e)),
            int(np.floor(h / e)),
        )

    def _nearest(self, n: np.ndarray, h: float) -> BoundaryCircle | None:
        """MERGE_EPS 안의 가장 가까운 carrier. 없으면 None."""
        cx, cy, cz, ch = self._cell(n, h)
        best: BoundaryCircle | None = None
        best_d = self.merge_eps
        seen: set[int] = set()
        for dx, dy, dz, dh in _NEIGHBORS:
            for idx in self._buckets.get((cx + dx, cy + dy, cz + dz, ch + dh), ()):
                if idx in seen:
                    continue
                seen.add(idx)
                bc = self.circles[idx]
                d = max(float(np.linalg.norm(bc.circle.n - n)), abs(bc.circle.h - h))
                if d < best_d:
                    best, best_d = bc, d
        return best

    def _insert(self, circle: SphericalCircle) -> BoundaryCircle:
        bc = BoundaryCircle(index=len(self.circles), circle=circle)
        self.circles.append(bc)
        self._buckets.setdefault(self._cell(circle.n, circle.h), []).append(bc.index)
        return bc

    # ---- 조회 -----------------------------------------------------------

    def find(self, n, h: float) -> tuple[BoundaryCircle, int] | None:
        """기존 carrier 를 찾는다. 없으면 None. **생성하지 않는다.**

        orientation 이 +1 이면 저장된 법선이 요청과 같은 방향, -1 이면 반대다.
        """
        nn = normalize(n)
        h = float(h)
        bc = self._nearest(nn, h)
        if bc is not None:
            return bc, 1
        bc = self._nearest(-nn, -h)
        if bc is not None:
            return bc, -1
        return None

    def lookup(self, n, h: float) -> tuple[BoundaryCircle, int]:
        """기존 carrier 를 찾고, 없으면 새로 만든다."""
        hit = self.find(n, h)
        if hit is not None:
            return hit
        return self._insert(SphericalCircle.from_normal_offset(n, h)), 1

    # ---- coverage --------------------------------------------------------

    def to_carrier_frame(self, bc: BoundaryCircle, n, h: float, intervals: Coverage) -> Coverage:
        """요청한 표현 기준 구간을 저장된 carrier 의 각도 좌표로 옮긴다."""
        src = SphericalCircle.from_normal_offset(n, h)
        return transfer_spans(src, bc.circle, intervals)

    def add_coverage(
        self,
        n,
        h: float,
        intervals: Coverage,
        provenance: Provenance = ROOT,
        only_visible: bool = False,
    ) -> tuple[BoundaryCircle, Coverage]:
        """요청한 원 위의 구간을 등록한다.

        반환값은 (carrier, 새로 추가된 구간). 추가된 구간은 carrier 각도 좌표
        기준이며 이미 덮여 있던 부분은 제외된다. ``ΔE = C - E`` (§3, §6.1).
        """
        bc, _orient = self.lookup(n, h)
        moved = self.to_carrier_frame(bc, n, h, intervals)
        added = bc.spans.add(moved, provenance, only_visible)
        return bc, added

    def is_fully_covered(self, n, h: float) -> bool:
        """§7.1 Turn 합법성: 회전 경계원이 이미 완전한 cut 인가."""
        hit = self.find(n, h)
        return hit is not None and hit[0].is_complete

    # ---- 조회 편의 -------------------------------------------------------

    def __len__(self) -> int:
        return len(self.circles)

    def __iter__(self):
        return iter(self.circles)

    def non_empty(self) -> list[BoundaryCircle]:
        return [bc for bc in self.circles if bc.spans]

    def total_arc_length(self) -> float:
        """전체 호 길이. Turn 은 이 값을 보존해야 한다."""
        return sum(bc.spans.total_length() for bc in self.circles)
