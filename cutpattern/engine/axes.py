"""축과 축 집합. 설계 문서 §2.1, §2.2, §5.

Axis 하나 = cut 원 하나 = cap 하나. layer 인덱스는 존재하지 않는다 (§2.3).
반대 방향 축은 자동 생성하지 않고 명시한다 (§2.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np

from ..geometry.vector import normalize

__all__ = ["Axis", "AxisSet", "PuzzleFamily"]


@dataclass(frozen=True)
class Axis:
    """방향 하나. 자기 집합의 cut angle 로 절단 원과 cap 을 결정한다.

        cut circle  : n·x = cos(theta)
        turn region : n·x >= cos(theta)   (바깥쪽이면 <=)

    회전각은 여기 저장하지 않는다. 현재 절단 각도에 따라 달라지므로
    engine.turns.derived_turns 로 유도한다 (§7). extra_turn_angles 는 유도가
    찾지 못하는 각을 명시하는 자리다.
    """

    id: str
    normal: np.ndarray
    extra_turn_angles: tuple[float, ...] = ()

    @staticmethod
    def make(id: str, normal, extra_turn_angles=()) -> "Axis":
        return Axis(
            id=id,
            normal=normalize(normal),
            extra_turn_angles=tuple(float(a) for a in extra_turn_angles),
        )


@dataclass(frozen=True)
class AxisSet:
    """같은 외부 cut-angle 입력을 공유하는 논리적 묶음.

    cut angle 의 현재값은 저장하지 않는다. 외부 입력의 식별자만 참조한다 (§13).
    enabled / style 같은 UI 상태도 여기 두지 않고 RuntimeState 에 둔다 (§5).
    """

    id: str
    axes: tuple[Axis, ...]
    cut_angle_input: str
    name: str = ""

    def axis(self, axis_id: str) -> Axis:
        for a in self.axes:
            if a.id == axis_id:
                return a
        raise KeyError(f"축 없음: {axis_id!r} (집합 {self.id!r})")


@dataclass(frozen=True)
class PuzzleFamily:
    """immutable. 각도에 따라 달라지는 퍼즐 계열의 정의."""

    axis_sets: tuple[AxisSet, ...]
    operations: tuple = field(default_factory=tuple)
    # 축 실림 선언 ((돌리는 축 id, (함께 도는 축 id, ...)), ...)
    #
    # 축이 어느 재료에 물려 있는지는 경계면만으로 알 수 없다. 유도하려 하면
    # 조건이 절단 각도의 함수가 되어 슬라이더를 움직일 때마다 축이 붙었다
    # 떨어졌다 하는데, 메커니즘은 그렇게 바뀌지 않는다. 그래서 선언한다 (§2.1).
    carries: tuple[tuple[str, tuple[str, ...]], ...] = ()

    def carried_by(self, axis_id: str) -> tuple[str, ...]:
        for mover, carried in self.carries:
            if mover == axis_id:
                return carried
        return ()

    def axis_set(self, set_id: str) -> AxisSet:
        for s in self.axis_sets:
            if s.id == set_id:
                return s
        raise KeyError(f"축 집합 없음: {set_id!r}")

    def find_axis(self, axis_id: str) -> tuple[AxisSet, Axis]:
        for s in self.axis_sets:
            for a in s.axes:
                if a.id == axis_id:
                    return s, a
        raise KeyError(f"축 없음: {axis_id!r}")

    def cut_angle_inputs(self) -> tuple[str, ...]:
        seen: list[str] = []
        for s in self.axis_sets:
            if s.cut_angle_input not in seen:
                seen.append(s.cut_angle_input)
        return tuple(seen)
