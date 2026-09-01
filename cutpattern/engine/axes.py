"""축과 축 집합. 설계 문서 §2.1, §2.2, §5.

Axis 하나 = cut 원 하나 = cap 하나. layer 인덱스는 존재하지 않는다 (§2.3).
반대 방향 축은 자동 생성하지 않고 명시한다 (§2.2).
"""

from __future__ import annotations

from dataclasses import dataclass, field

from ..geometry.vector import Vec3, normalize

__all__ = ["Axis", "AxisSet", "PuzzleFamily"]


@dataclass(frozen=True)
class Axis:
    """방향 하나. 자기 집합의 cut angle 로 절단 원과 cap 을 결정한다.

        cut circle  : n·x = cos(theta)
        turn region : n·x >= cos(theta)   (바깥쪽이면 <=)

    turn_angles 는 이 축이 **있을 수 있는 방향**의 선언이다 (§7.11). 돌 수 있는
    양이 아니다 — 시작이 0 이고 모든 회전은 축을 선언된 방향으로 데려가야 한다.
    비어 있으면 제약이 없고, 0 은 늘 유효하다. 정적 검사라 `Puzzle.check()`
    에서 본다.

    유도되는 회전각(engine.turns.derived_turns, §7.7)은 별개다. 그쪽은 현재
    절단 각도의 함수라 여기 저장하지 않는다.
    """

    id: str
    normal: Vec3
    turn_angles: tuple[float, ...] = ()

    @staticmethod
    def make(id: str, normal, turn_angles=()) -> "Axis":
        return Axis(
            id=id,
            normal=normalize(normal),
            turn_angles=tuple(float(a) for a in turn_angles),
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
    # 이 집합이 얹혀 있는 집합의 id. None 이면 코어다 (§2.4)
    attached: str | None = None

    def axis(self, axis_id: str) -> Axis:
        for a in self.axes:
            if a.id == axis_id:
                return a
        raise KeyError(f"no such axis: {axis_id!r} in set {self.id!r}")


@dataclass(frozen=True)
class PuzzleFamily:
    """immutable. 각도에 따라 달라지는 퍼즐 계열의 정의."""

    axis_sets: tuple[AxisSet, ...]
    operations: tuple = field(default_factory=tuple)

    def attached_to(self, set_id: str) -> str | None:
        """이 집합이 얹혀 있는 집합 id. None 이면 코어다 (§2.4)."""
        for s in self.axis_sets:
            if s.id == set_id:
                return s.attached
        raise KeyError(f"no such axis set: {set_id!r}")

    def is_carried(
        self,
        set_id: str,
        turn_set_id: str,
        *,
        outer: bool,
        in_region: bool,
        core_in_region: bool,
    ) -> bool:
        """이 회전이 `set_id` 의 축을 함께 돌리는가 (§2.4).

        마운트를 따라 올라간다.

        - 코어에 얹혀 있으면 **코어가 회전 영역 안에 있을 때** 돈다.
          어느 쪽인지는 절단각이 정한다 — `core_in_region` 을 보라
        - 어떤 집합에 얹혀 있고 그 집합이 지금 도는 집합이면, 내 위치가 회전
          영역 안일 때 돈다
        - 그 집합이 지금 도는 집합이 아니면, **그 집합이 실리는지**를 묻는다.
          사슬이 이렇게 이어진다

        `in_region` 은 묻는 축의 위치가 이 회전의 영역 안인지다.
        """
        seen: set[str] = set()
        current = set_id
        while True:
            if current in seen:
                raise ValueError(f"attached loop through {current!r}")
            seen.add(current)
            host = self.attached_to(current)
            if host is None:
                return core_in_region
            if host == turn_set_id:
                return in_region
            current = host

    def find_axis(self, axis_id: str) -> tuple[AxisSet, Axis]:
        for s in self.axis_sets:
            for a in s.axes:
                if a.id == axis_id:
                    return s, a
        raise KeyError(f"no such axis: {axis_id!r}")

    def cut_angle_inputs(self) -> tuple[str, ...]:
        seen: list[str] = []
        for s in self.axis_sets:
            if s.cut_angle_input not in seen:
                seen.append(s.cut_angle_input)
        return tuple(seen)
