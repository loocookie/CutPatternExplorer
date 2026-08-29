"""provenance 를 가진 각도 구간. 설계 문서 §5, §16 단계 2.

순수 구간 수학(`angular_coverage`)과 분리한다. 집합 연산은 평범한 `(t0, t1)`
튜플에서 하고, provenance 는 이 계층이 들고 있는다.

**서로 다른 provenance 를 가진 인접 span 은 병합하지 않는다.** 병합하면 어느
연산이 그 호를 만들었는지가 사라진다. 렌더링에서는 맞닿은 두 호로 보이므로
시각적 차이가 없고, `is_full` 같은 판정은 구간 수학 계층에서 하므로 영향이
없다.
"""

from __future__ import annotations

from dataclasses import dataclass, replace

from ..epsilon import ANGLE_EPS
from .angular_coverage import Coverage, difference, normalize_spans

__all__ = ["Provenance", "AngularSpan", "SpanList"]


@dataclass(frozen=True)
class Provenance:
    """이 호가 어디서 왔는지 (§5).

    기하 계산에는 쓰이지 않지만 디버깅, 선택 표시, 되감기, 오류 보고에 필요하다.

    두 층으로 나뉜다.

    - ``op_index``/``axis_id``/``kind`` — 이 호를 **지금 자리로 보낸** 연산.
      Turn 이 옮기면 갱신된다.
    - ``origin_axis_set``/``origin_axis`` — 이 재료를 **처음 만든 split**.
      Turn 을 거쳐도 보존된다. 재료를 만드는 연산은 Split 뿐이므로 모든 호가
      출처를 가진다. 축 집합별 색칠이 이 값을 쓴다 (§11).
    """

    op_index: int
    axis_id: str
    kind: str  # "split" | "turn"
    origin_axis_set: str = ""
    origin_axis: str = ""

    def __str__(self) -> str:
        where = f"#{self.op_index}:{self.kind}:{self.axis_id}"
        if self.kind == "turn" and self.origin_axis:
            return f"{where}<-{self.origin_axis_set}:{self.origin_axis}"
        return where


ROOT = Provenance(op_index=-1, axis_id="", kind="root")


@dataclass
class AngularSpan:
    t0: float
    t1: float
    provenance: Provenance = ROOT
    # 가시성 표시 (§7.9). None 이면 보인다. 숫자면 그 깊이의 region 블록이
    # 숨긴 것이고, 같은 깊이의 ExitRegion 이 지운다.
    #
    # 기하 영역으로는 대신할 수 없다. 회전이 보이는 재료를 숨은 재료 위로
    # 옮기면 같은 자리에 둘이 겹치는데, 위치만으로는 구분되지 않는다.
    # 표시는 재료를 따라다니므로 회전이 몇 번이든 정확하다.
    hidden_at: int | None = None

    @property
    def visible(self) -> bool:
        return self.hidden_at is None

    @property
    def length(self) -> float:
        return self.t1 - self.t0

    @property
    def midpoint(self) -> float:
        return 0.5 * (self.t0 + self.t1)

    def as_tuple(self) -> tuple[float, float]:
        return (self.t0, self.t1)

    def with_range(self, t0: float, t1: float) -> "AngularSpan":
        """provenance 를 물려주며 범위만 바꾼다. straddling 분할에 쓴다 (§7.3)."""
        return replace(self, t0=t0, t1=t1)


class SpanList:
    """한 carrier 원 위의 span 목록."""

    def __init__(self, spans: list[AngularSpan] | None = None) -> None:
        self.spans: list[AngularSpan] = list(spans or [])
        self._sort()

    def _sort(self) -> None:
        self.spans.sort(key=lambda s: s.t0)

    # ---- 구간 수학 계층으로 넘기는 view --------------------------------

    def intervals(self) -> Coverage:
        return normalize_spans([s.as_tuple() for s in self.spans])

    def raw_intervals(self) -> Coverage:
        """병합하지 않은 원본 구간. 길이 합 검증용."""
        return [s.as_tuple() for s in self.spans]

    # ---- 편집 ----------------------------------------------------------

    def add(
        self,
        intervals: Coverage,
        provenance: Provenance,
        only_visible: bool = False,
    ) -> Coverage:
        """아직 덮이지 않은 부분만 추가한다. 반환값은 실제로 추가된 구간.

        이것이 ``ΔE = C - E`` 다 (§3, §6.1).

        only_visible 이면 숨은 호는 덮인 것으로 치지 않는다. region 블록 안의
        split 은 숨은 재료를 치워둔 상태에서 자르므로, 숨은 호가 있는 자리에도
        새로 잘라야 한다 (§6.3, §7.9). 숨은 호가 그 자리를 막으면 새 절단이
        보이는 재료 한가운데서 끝나 매달린 모서리가 된다.
        """
        gap = difference(
            intervals, self.visible_intervals() if only_visible else self.intervals()
        )
        for t0, t1 in gap:
            if t1 - t0 > ANGLE_EPS:
                self.spans.append(AngularSpan(t0, t1, provenance))
        self._sort()
        return gap

    def replace_all(self, spans: list[AngularSpan]) -> None:
        self.spans = [s for s in spans if s.length > ANGLE_EPS]
        self._sort()

    def total_length(self) -> float:
        return sum(s.length for s in self.spans)

    def visible(self) -> list[AngularSpan]:
        return [s for s in self.spans if s.visible]

    def hidden(self) -> list[AngularSpan]:
        return [s for s in self.spans if not s.visible]

    def visible_intervals(self) -> Coverage:
        return normalize_spans([s.as_tuple() for s in self.spans if s.visible])

    def __len__(self) -> int:
        return len(self.spans)

    def __iter__(self):
        return iter(self.spans)

    def __bool__(self) -> bool:
        return bool(self.spans)
