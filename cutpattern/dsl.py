"""퍼즐 정의용 내장 DSL. 설계 문서 §9 대체.

XML 대신 파이썬 자체를 문법으로 쓴다. for, def, with, 컴프리헨션, 조건문이
전부 그냥 동작한다. pCubes 가 Script, Macro, ExecMacro 로 따로 만들어야 했던
변수/매크로/반복이 공짜로 딸려온다. 파서는 한 줄도 없다.

    from cutpattern import solids as S
    from cutpattern.dsl import puzzle, split, turned

    faces = S.cube("faces", turns=(45, -45, 90, -90, 180))

    with puzzle("OctoCube Master", faces) as p:
        split(faces)
        for x in faces:
            with turned(x, 45):
                split(*faces.at_angle(x, 90))

    p.run({"faceCut": 63.2563})

원시 연산은 split 과 turn 둘뿐이다. 활성 puzzle 블록에 연산을 기록한다.
블록을 벗어나면 immutable PuzzleFamily 가 만들어진다 (§5).

설계 방침
---------
- 축 집합은 항상 면 기준이다. 정다면체의 면 법선이 축이 된다.
- 축 질의는 at_angle 하나뿐이다. 수직/반대/평행은 전부 그 특수한 경우이고,
  입체에 따라 아예 존재하지 않을 수도 있다. 자주 쓰는 조합은 파이썬 함수로
  묶으면 된다.
- 구성용 회전은 정의 끝에서 자동으로 되돌아간다. 별도 함수가 없다.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass

from .engine.axes import Axis
from .engine.axes import AxisSet as _EngineAxisSet
from .engine.axes import PuzzleFamily
from .engine.operations import (
    EnterRegion,
    ExitRegion,
    RollbackTurns,
    SplitByAxis,
    Turn,
    evaluate,
)
from .axisops import invert, keep, merge, mirror, remove, rename, rotate, same_directions
from .query import (
    angle_between,
    angles_from,
    at_angle,
    axes_of,
    group_by_nearest,
    nearest,
)

__all__ = [
    "AxisSet",
    "Puzzle",
    "puzzle",
    "split",
    "turn",
    "turned",
    "carry",
    "region",
    "inside",
    "outside",
    "merge",
    "rotate",
    "remove",
    "keep",
    "rename",
    "mirror",
    "invert",
    "same_directions",
    "angle_between",
    "at_angle",
    "angles_from",
    "group_by_nearest",
    "nearest",
    "axes_of",
    "ANGLE_TOL_DEG",
]

# 축 사이 각 판정 허용 오차(도).
# acos 는 인자가 +-1 근처일 때 오차를 sqrt(eps) ~ 1e-8 rad 까지 키우므로
# 수치 잡음보다는 넉넉하게, 실제로 구분되는 축 사이 각보다는 훨씬 작게 잡는다.
ANGLE_TOL_DEG = 1e-4


# ---------------------------------------------------------------- 축 집합


class AxisSet:
    """같은 절단 각도를 공유하는 축 묶음 (§2.1).

    집합 id 가 곧 slider 식별자다. 각도 값은 여기 저장하지 않는다 (§13).
    두 집합이 각도를 공유할 일은 없다. 공유하고 싶으면 merge 한다.
    """

    @property
    def cut(self) -> str:
        """slider 식별자. 집합 id 와 같다."""
        return self.id

    def __init__(
        self,
        id: str,
        axes: dict[str, tuple[float, float, float]] | None = None,
        extra_turns: tuple[float, ...] = (),
        name: str = "",
    ) -> None:
        self.id = id
        self.name = name or id
        self.extra_turns = tuple(float(a) for a in extra_turns)
        self._axes: list[Axis] = []
        for axis_id, normal in (axes or {}).items():
            self.add(axis_id, normal)

    def add(self, axis_id: str, normal, extra_turns=None) -> Axis:
        """축 하나를 넣는다.

        회전각은 절단 각도의 함수라 여기 저장하지 않는다 (engine.turns).
        extra_turns 는 유도가 찾지 못하는 각을 그 축에만 명시하는 자리다.
        생략하면 집합 기본값을 쓴다.
        """
        if any(a.id == axis_id for a in self._axes):
            raise ValueError(f"duplicate axis id {axis_id!r} in set {self.id!r}")
        axis = Axis.make(
            axis_id, normal, self.extra_turns if extra_turns is None else extra_turns
        )
        self._axes.append(axis)
        return axis

    # ---- 접근 ----------------------------------------------------------

    def __iter__(self):
        return iter(self._axes)

    def __len__(self) -> int:
        return len(self._axes)

    def __getitem__(self, axis_id: str) -> Axis:
        for a in self._axes:
            if a.id == axis_id:
                return a
        raise KeyError(f"no such axis: {axis_id!r} in set {self.id!r}")

    def __getattr__(self, axis_id: str) -> Axis:
        # 점 표기: faces.U
        if axis_id.startswith("_"):
            raise AttributeError(axis_id)
        try:
            return self[axis_id]
        except KeyError as exc:
            raise AttributeError(str(exc)) from exc

    def __repr__(self) -> str:
        return f"AxisSet({self.id!r}, axes={len(self._axes)})"

    def to_engine(self) -> _EngineAxisSet:
        return _EngineAxisSet(
            id=self.id,
            axes=tuple(self._axes),
            cut_angle_input=self.cut,
            name=self.name,
        )


# ------------------------------------------------------------- 프로그램


class _Recorder:
    def __init__(self) -> None:
        self.ops: list[object] = []
        self.open_turns: list[tuple[str, float, bool]] = []
        self.carries: list[tuple[str, tuple[str, ...]]] = []


_STACK: list[_Recorder] = []


def _active() -> _Recorder:
    if not _STACK:
        raise RuntimeError(
            "split / turn only work inside a with puzzle(...) block"
        )
    return _STACK[-1]


def inside(axis: Axis) -> tuple[str, float]:
    """축의 절단원 안쪽(cap)."""
    if not isinstance(axis, Axis):
        raise TypeError(f"inside() needs an Axis, got {axis!r}")
    return (axis.id, 1.0)


def outside(axis: Axis) -> tuple[str, float]:
    """축의 절단원 바깥쪽."""
    if not isinstance(axis, Axis):
        raise TypeError(f"outside() needs an Axis, got {axis!r}")
    return (axis.id, -1.0)


@contextmanager
def region(*constraints):
    """블록 안의 split 과 turn 을 이 영역으로 제한한다 (§6.3, §7.9).

    pCubes 의 Hide ... ShowAll 괄호에 대응한다. 정지 재료를 잠시 치워두고
    계산하는 구성 장치이며, 물리적 제약이 아니다.

        with region(outside(x), outside(opposite)):
            split(*at_angle(x, 90, faces))

    중첩하면 제약이 누적된다. 영역은 축을 이름으로 참조하고 축은 공간에
    고정이므로, 회전 뒤에 영역을 더해도 같은 자리를 뜻한다.
    """
    if not constraints:
        raise ValueError("region() needs at least one constraint")
    for c in constraints:
        if not (isinstance(c, tuple) and len(c) == 2 and isinstance(c[0], str)):
            raise TypeError(
                f"a region constraint must be inside(axis) or outside(axis), got {c!r}"
            )
    rec = _active()
    rec.ops.append(EnterRegion(tuple(constraints)))
    try:
        yield tuple(constraints)
    finally:
        rec.ops.append(ExitRegion())


def split(*targets):
    """축 집합, 축, 또는 그것들의 목록으로 절단 경계를 추가한다 (§6).

    axes_of 를 그대로 쓰므로 중첩까지 편다. 질의 결과를 ``*`` 없이 넣어도 되고
    목록을 섞어도 된다.

        split(faces)                        집합 전체
        split(faces.R)                      축 하나
        split(at_angle(x, 90, faces))       질의 결과를 그대로
        split(cube, rd)                     집합 여러 개
        split([pair_x, pair_y, pair_z])     축 쌍들의 목록

    **빈 결과는 거부한다.** 대상을 빠뜨린 질의(``at_angle(x, 90)`` 처럼)가 조용히
    아무것도 자르지 않고 지나가면, 완성된 것처럼 보이는 no-op 정의가 남는다.
    """
    if not targets:
        raise TypeError("split() needs a target")
    axes = axes_of(*targets)
    if not axes:
        raise TypeError(f"split() target is empty: {targets!r}")
    rec = _active()
    ops = []
    for a in axes:
        op = SplitByAxis(a.id)
        rec.ops.append(op)
        ops.append(op)
    return ops[0] if len(ops) == 1 else ops


def turn(axis: Axis, angle: float, outer: bool = False):
    """축의 절단원 한쪽을 angle(도)만큼 회전한다 (§7.1).

        outer=False   cap         0 ~ theta
        outer=True    나머지      theta ~ 180

    slice 회전은 둘의 합성이다.

        with turned(faces.U, 45, outer=True):
            with turned(faces.D, 45):
                ...              # M 슬라이스가 45도 돌아간 상태
    """
    if not isinstance(axis, Axis):
        raise TypeError(f"turn() needs an Axis, got {axis!r}")
    rec = _active()
    op = Turn(axis.id, float(angle), bool(outer))
    rec.ops.append(op)
    return op


@contextmanager
def turned(axis: Axis, angle: float, outer: bool = False):
    """블록 시작에 회전하고 블록 끝에 정확히 되돌린다.

    pCubes 의 Turn ... SplitByAxes ... Undo 매크로 관용구를 그대로 옮긴 것이다.
    rollback() 과 다르다. rollback 은 쌓인 회전을 끝에 한꺼번에 되돌리고,
    이쪽은 블록 단위로 짝을 맞춘다. 다음 축으로 넘어가기 전에 원상태여야 하는
    경우가 이쪽이다.
    """
    rec = _active()
    turn(axis, angle, outer)
    rec.open_turns.append((axis.id, angle, outer))
    try:
        yield axis
    finally:
        rec.open_turns.pop()
        turn(axis, -angle, outer)


def carry(mover: Axis, *carried):
    """mover 를 돌리면 지정한 축들도 함께 돈다고 선언한다 (§2.1).

    유도하지 않는다. 축이 어느 재료에 물려 있는지는 경계면만으로 알 수 없고,
    기하로 유도하면 조건이 절단 각도의 함수가 되어 슬라이더를 움직일 때마다
    축이 붙었다 떨어졌다 한다. 메커니즘은 그렇게 바뀌지 않는다.

    규칙은 파이썬으로 쓴다. angle_to 는 슬라이더와 무관한 정적 값이다.

        for x in outer:
            carry(x, *[a for a in inner if angle_between(x, a) < 40])

    기본값은 아무것도 실리지 않음이다.
    """
    if not isinstance(mover, Axis):
        raise TypeError(f"the first argument of carry() must be an Axis, got {mover!r}")
    ids: list[str] = []
    for target in carried:
        if isinstance(target, AxisSet):
            ids.extend(a.id for a in target)
        elif isinstance(target, Axis):
            ids.append(target.id)
        else:
            raise TypeError(
                f"carry() needs an AxisSet or an Axis, got {target!r}"
            )
    if mover.id in ids:
        raise ValueError(f"axis {mover.id!r} cannot carry itself")
    if ids:
        _active().carries.append((mover.id, tuple(ids)))


@dataclass
class Puzzle:
    """with puzzle(...) 이 만드는 빌더. 블록을 벗어나면 family 가 완성된다."""

    name: str
    axis_sets: tuple[AxisSet, ...]
    family: PuzzleFamily | None = None

    def __post_init__(self) -> None:
        self._recorder = _Recorder()
        seen: dict[str, str] = {}
        for s in self.axis_sets:
            for a in s:
                if a.id in seen:
                    raise ValueError(
                        f"axis id {a.id!r} appears in both {seen[a.id]!r} and {s.id!r}. "
                        "operations reference axes by name, so ids must be unique across sets"
                    )
                seen[a.id] = s.id

    def __enter__(self) -> "Puzzle":
        _STACK.append(self._recorder)
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        _STACK.pop()
        if exc_type is None:
            # 정의 끝에서 구성용 회전을 항상 되돌린다. cut pattern 은 기준
            # 방향에서 보여야 초기 상태와 비교가 된다. turned() 로 이미 짝을
            # 맞춘 회전은 상쇄되어 있으므로 남은 것만 되돌려진다 (§7.5).
            ops = list(self._recorder.ops)
            ops.append(RollbackTurns())
            self.family = PuzzleFamily(
                axis_sets=tuple(s.to_engine() for s in self.axis_sets),
                operations=tuple(ops),
                carries=tuple(self._recorder.carries),
            )
            self.check()
        return False

    # ---- 편의 ----------------------------------------------------------

    @property
    def operations(self) -> tuple:
        return tuple(self._recorder.ops)

    @property
    def cut_inputs(self) -> tuple[str, ...]:
        return tuple(dict.fromkeys(s.cut for s in self.axis_sets))

    def check(self) -> None:
        """실행 전 정적 검사. 참조하는 이름이 실제로 있는지 본다."""
        if self.family is None:
            return
        known_axes = {a.id for s in self.axis_sets for a in s}
        for i, op in enumerate(self.family.operations):
            if isinstance(op, SplitByAxis) and op.axis not in known_axes:
                raise ValueError(f"operation #{i}: no such axis {op.axis!r}")
            if isinstance(op, Turn) and op.axis not in known_axes:
                raise ValueError(f"operation #{i}: no such axis {op.axis!r}")
        for mover, carried in self.family.carries:
            for axis_id in (mover, *carried):
                if axis_id not in known_axes:
                    raise ValueError(f"carry declaration: no such axis {axis_id!r}")

    def evaluate(self, cut_angles: dict[str, float], **kwargs):
        if self.family is None:
            raise RuntimeError("close the with puzzle(...) block first")
        missing = set(self.cut_inputs) - set(cut_angles)
        if missing:
            raise KeyError(f"no cut angle given for: {sorted(missing)}")
        return evaluate(self.family, cut_angles, **kwargs)

    def run(self, cut_angles: dict[str, float], **kwargs) -> None:
        """vpython 뷰어를 띄운다."""
        from .render.vpython_view import run as _run

        if self.family is None:
            raise RuntimeError("close the with puzzle(...) block first")
        _run(self.family, cut_angles, **kwargs)


def puzzle(name: str, *axis_sets: AxisSet) -> Puzzle:
    if not axis_sets:
        raise ValueError("a puzzle needs at least one axis set")
    return Puzzle(name=name, axis_sets=tuple(axis_sets))
