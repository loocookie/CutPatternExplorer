"""렌더러에 넘길 한 프레임 분량. 설계 문서 §11.1, §11.2, §15.

호스트(브라우저 JS)와의 경계다. 파이썬은 기하가 바뀔 때만 이것을 만들고,
카메라 회전과 다시 그리기는 호스트가 한다 (§11.1).

**평탄한 배열로 넘긴다.** Pyodide 의 파이썬 -> JS 변환 비용은 객체 개수에
비례한다. `[[x, y, z], ...]` 를 넘기면 점 하나마다 배열 하나를 만들지만,
`[x, y, z, x, y, z, ...]` 하나면 숫자 열 하나를 옮기는 일이 된다. 극단적인
정의에서 27,000 점이므로 (§11.1) 차이가 크다.

폴리라인 경계는 `starts` / `counts` 로 따로 싣는다. 중첩 배열을 쓰면 평탄화의
이점이 사라진다.

렌더 객체 pool (§11) 은 여기서 필요 없다. Canvas 2D 는 즉시 모드라 매 프레임
전부 다시 그린다. `arc_id` 는 provenance 진단으로만 남는다.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field

from ..engine.axes import PuzzleFamily
from ..geometry.registry import BoundaryRegistry
from .arcs import build_arcs
from .markers import build_axis_markers

__all__ = ["Scene", "ARC", "MARKER", "build_scene"]

# 폴리라인 종류. 렌더러가 굵기와 투명도를 다르게 준다 (§11.4)
ARC = 0
MARKER = 1


@dataclass
class Scene:
    """한 프레임 분량의 기하. 전부 평탄한 수열이다."""

    # 좌표. 길이 3N. 모든 폴리라인을 이어 붙인 것
    xyz: list[float] = field(default_factory=list)
    # 폴리라인 i 는 점 starts[i] 부터 counts[i] 개
    starts: list[int] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    # 폴리라인 i 가 속한 축 집합 (axis_sets 의 인덱스). 색과 토글이 이걸 쓴다
    groups: list[int] = field(default_factory=list)
    kinds: list[int] = field(default_factory=list)
    # 축 마커 라벨. (텍스트, x, y, z, 축 집합 인덱스)
    labels: list[tuple[str, float, float, float, int]] = field(default_factory=list)
    # 인덱스 -> 축 집합 id. 토글 UI 가 이름을 여기서 얻는다
    axis_sets: list[str] = field(default_factory=list)

    @property
    def point_count(self) -> int:
        return len(self.xyz) // 3

    def polyline(self, i: int) -> list[tuple[float, float, float]]:
        """폴리라인 하나를 점 목록으로. 검사와 테스트용이다."""
        s, n = self.starts[i] * 3, self.counts[i]
        return [tuple(self.xyz[s + 3 * k : s + 3 * k + 3]) for k in range(n)]

    def add(self, points, group: int, kind: int) -> None:
        """폴리라인 하나를 평탄한 수열에 이어 붙인다."""
        self.starts.append(len(self.xyz) // 3)
        self.counts.append(len(points))
        self.groups.append(group)
        self.kinds.append(kind)
        for p in points:
            self.xyz.append(p[0])
            self.xyz.append(p[1])
            self.xyz.append(p[2])

    def __len__(self) -> int:
        return len(self.starts)

    def to_json(self, precision: int = 6) -> str:
        """정적 파일로 내보낼 때만 쓴다.

        Pyodide 경로에서는 직렬화하지 않고 리스트를 그대로 넘긴다 — JSON 을
        거치면 평탄화로 아낀 것을 문자열 파싱으로 도로 쓴다.

        좌표는 단위구 위이므로 소수 6자리면 화면 오차보다 훨씬 작다. 전자릿수로
        쓰면 파일이 두 배가 된다.
        """
        return json.dumps(
            {
                "xyz": [round(v, precision) for v in self.xyz],
                "starts": self.starts,
                "counts": self.counts,
                "groups": self.groups,
                "kinds": self.kinds,
                "labels": [list(x) for x in self.labels],
                "axisSets": self.axis_sets,
            },
            separators=(",", ":"),
        )


def build_scene(
    registry: BoundaryRegistry,
    family: PuzzleFamily,
    max_step: float = 0.03,
    markers: bool = True,
) -> Scene:
    """registry 와 정의에서 한 프레임 분량을 만든다.

    호는 절단 각도에 따라 달라지지만 마커는 축 방향만 쓰므로 변하지 않는다
    (§11.4). 그래도 같은 배열에 담는다 — 호스트가 한 번의 순회로 그린다.
    """
    scene = Scene(axis_sets=[aset.id for aset in family.axis_sets])
    index = {aid: i for i, aid in enumerate(scene.axis_sets)}

    for arc in build_arcs(registry, max_step=max_step):
        # 출처를 모르는 호는 있어서는 안 되지만, 있으면 첫 집합으로 그린다
        scene.add(arc.points, index.get(arc.provenance.origin_axis_set, 0), ARC)

    if markers:
        _add_markers(scene, family.axis_sets, index)

    return scene


def _add_markers(scene: Scene, axis_sets, index: dict[str, int]) -> None:
    for marker in build_axis_markers(axis_sets):
        group = index.get(marker.axis_set_id, 0)
        scene.add(marker.points, group, MARKER)
        x, y, z = marker.label_position
        scene.labels.append((marker.axis_id, x, y, z, group))


def build_marker_scene(axis_sets) -> Scene:
    """축 마커만 담은 장면. 편집 모드의 무대다 (§19.15).

    **절단이 없다.** 편집 모드에서 보려는 것은 축이 어디 있느냐이고, 절단은
    `Run` 을 눌러 실행 모드로 나가야 다시 그려진다 — 고치는 동안 퍼즐이 바뀌면
    무엇을 보고 있는지가 흐려진다.

    `build_scene` 과 달리 registry 도 `max_step` 도 안 받는다. 마커는 축 방향만
    쓰므로 절단 각도와 무관하다 (§11.4).
    """
    scene = Scene(axis_sets=[aset.id for aset in axis_sets])
    index = {aid: i for i, aid in enumerate(scene.axis_sets)}
    _add_markers(scene, axis_sets, index)
    return scene
