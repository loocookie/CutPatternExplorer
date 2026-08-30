"""개발용 vpython 뷰어. 설계 문서 §11, §16 단계 1.

반투명 구 + 호 폴리라인 + cut-angle slider + 축 마커 + 축 집합 토글.
엔진은 이 모듈을 import 하지 않는다 (§15).
"""

from __future__ import annotations

import time

from ..engine.axes import PuzzleFamily
from ..engine.operations import Truncated, evaluate
from .arcs import build_arcs
from .markers import build_axis_markers

# 조작 중 / 조작 종료 후 tessellation (§12)
DRAG_STEP = 0.15
FINAL_STEP = 0.03

# 조작 중 재생성 최소 간격(초). 위젯 콜백이 평가보다 빨리 오므로 합쳐서 처리한다
MIN_REBUILD_INTERVAL = 0.05

# 축 집합별 기본 색. 같은 축 집합에서 나온 호는 같은 색으로 그린다 (§11).
# 사용자가 바꿀 수 있도록 SphereView(axis_set_colors=...) 로 덮어쓸 수 있다.
PALETTE = [
    (0.90, 0.25, 0.25),
    (0.20, 0.55, 0.95),
    (0.20, 0.75, 0.35),
    (0.95, 0.70, 0.15),
    (0.70, 0.35, 0.95),
    (0.15, 0.80, 0.78),
]

# 출처를 알 수 없는 호 (있어서는 안 되지만 방어용)
FALLBACK_COLOR = (0.45, 0.45, 0.45)

SPHERE_COLOR = (0.85, 0.87, 0.92)
SPHERE_OPACITY = 0.55

# 축 마커. 아주 작은 원을 절단 호보다 굵은 튜브로 그려 구슬처럼 보이게 한다.
#
# 크기만으로는 진짜 얕은 절단과 구분되지 않는다 — theta 를 2도로 놓을 수 있다.
# 색상은 축 집합 그대로 두어 소속을 말하게 하고, 반지름보다 굵은 선과 반투명이
# "이건 절단이 아니다" 를 말한다. 각반경(MARKER_ANGLE_DEG)이 1도라 선 굵기가
# 원 지름을 넘어서므로 고리가 아니라 점으로 읽힌다 (§11.4).
MARKER_RADIUS = 0.01
MARKER_OPACITY = 0.55
ARC_RADIUS = 0.006

# 라벨은 2D 빌보드라 구에 가려지지 않는다. 원은 뒤로 가면 흐려지는데 글자만
# 또렷하면 깨져 보이므로, 카메라 반대쪽 축의 라벨은 끈다.
LABEL_HEIGHT = 11


class SphereView:
    def __init__(
        self,
        family: PuzzleFamily,
        cut_angles: dict[str, float],
        axis_set_colors: dict[str, tuple[float, float, float]] | None = None,
        sphere_opacity: float = SPHERE_OPACITY,
    ) -> None:
        import vpython as vp

        self.vp = vp
        self.family = family
        self.cut_angles = dict(cut_angles)
        self.axis_set_colors = self._default_colors()
        if axis_set_colors:
            self.axis_set_colors.update(axis_set_colors)
        self._curves: dict[str, object] = {}
        self._marker_curves: dict[str, object] = {}
        self._marker_labels: dict[str, object] = {}
        # 꺼진 축 집합. 호와 마커를 함께 숨긴다
        self._hidden_sets: set[str] = set()
        self._show_markers = True
        self._last_forward = None
        self._last_change = 0.0
        self._last_render = 0.0
        self._dirty = False
        self._needs_final = False
        self.status = None

        self.scene = vp.canvas(
            title="Cut Pattern Explorer\n",
            width=900,
            height=700,
            background=vp.color.white,
            forward=vp.vector(-0.6, -0.4, -1),
        )
        self.sphere = vp.sphere(
            pos=vp.vector(0, 0, 0),
            radius=0.995,
            color=vp.vector(*SPHERE_COLOR),
            opacity=sphere_opacity,
        )

        self.scene.append_to_caption("\n")
        self.sliders = {}
        for input_id in family.cut_angle_inputs():
            self._make_slider(input_id)
        self._make_toggles()
        self.status = vp.wtext(text="")

        self.markers = build_axis_markers(family)
        self._draw_markers()
        self.rebuild(FINAL_STEP)

    def _default_colors(self) -> dict[str, tuple[float, float, float]]:
        """축 집합 순서대로 팔레트를 배정한다."""
        return {
            aset.id: PALETTE[i % len(PALETTE)]
            for i, aset in enumerate(self.family.axis_sets)
        }

    def color_for(self, arc) -> tuple[float, float, float]:
        """호의 색은 그 재료를 만든 split 의 축 집합이 정한다.

        Turn 으로 옮겨진 호도 출처를 물려받으므로 색이 유지된다 (§5).
        """
        return self.axis_set_colors.get(arc.provenance.origin_axis_set, FALLBACK_COLOR)

    def _make_slider(self, input_id: str) -> None:
        vp = self.vp
        label = vp.wtext(text=f"  {input_id}: {self.cut_angles[input_id]:6.2f}°  ")

        def on_change(s, input_id=input_id, label=label):
            # 위젯 콜백은 별도 스레드에서 온다. 여기서 곧바로 rebuild 하면
            # 평가 도중에 다음 콜백이 각도를 바꿔버릴 수 있다. 값만 기록하고
            # 실제 재생성은 메인 루프의 tick() 에서 한다.
            self.cut_angles[input_id] = s.value
            label.text = f"  {input_id}: {s.value:6.2f}°  "
            self._last_change = time.time()
            self._dirty = True
            self._needs_final = True

        slider = vp.slider(
            # 0 과 180 은 퇴화원이라 자를 것이 없다. 터지지는 않는다 (§14)
            min=0.0,
            max=180.0,
            step=0.05,
            value=self.cut_angles[input_id],
            length=520,
            bind=on_change,
        )
        self.sliders[input_id] = slider
        self.scene.append_to_caption("\n")

    def _make_toggles(self) -> None:
        """축 집합별 show/hide 와 마커 on/off.

        호의 출처는 이미 `provenance.origin_axis_set` 에 있고 (§5) 색을 고를 때
        쓰고 있으므로, 숨기기는 같은 값으로 거르기만 하면 된다. 엔진은 건드리지
        않는다 — 평가는 그대로 하고 그리지만 않는다.
        """
        vp = self.vp
        self.scene.append_to_caption(chr(10))

        def on_marker(cb):
            self._show_markers = cb.checked
            self._draw_markers()

        vp.checkbox(bind=on_marker, text=" 축 마커   ", checked=True)

        for aset in self.family.axis_sets:

            def on_set(cb, set_id=aset.id):
                if cb.checked:
                    self._hidden_sets.discard(set_id)
                else:
                    self._hidden_sets.add(set_id)
                self._draw_markers()
                self.rebuild(FINAL_STEP)

            vp.checkbox(bind=on_set, text=f" {aset.id}   ", checked=True)
        self.scene.append_to_caption(chr(10))

    def _draw_markers(self) -> None:
        """축 마커를 만들거나 가시성을 갱신한다.

        절단 각도와 무관하므로 (§11) 슬라이더가 움직여도 다시 만들지 않는다.
        """
        vp = self.vp
        for marker in self.markers:
            visible = self._show_markers and marker.axis_set_id not in self._hidden_sets
            curve = self._marker_curves.get(marker.id)
            if curve is None:
                color = vp.vector(
                    *self.axis_set_colors.get(marker.axis_set_id, FALLBACK_COLOR)
                )
                self._marker_curves[marker.id] = vp.curve(
                    pos=[vp.vector(*p) for p in marker.points],
                    color=color,
                    radius=MARKER_RADIUS,
                    opacity=MARKER_OPACITY,
                )
                self._marker_labels[marker.id] = vp.label(
                    pos=vp.vector(*marker.label_position),
                    text=marker.axis_id,
                    height=LABEL_HEIGHT,
                    box=False,
                    opacity=0.0,
                    color=color,
                )
            self._marker_curves[marker.id].visible = visible
            self._marker_labels[marker.id].visible = visible
        self._update_label_facing(force=True)

    def _update_label_facing(self, force: bool = False) -> None:
        """카메라 반대쪽 라벨을 끈다.

        vpython label 은 2D 빌보드라 구에 가려지지 않는다. 원은 뒤로 가면
        반투명 구에 흐려지는데 글자만 또렷하면 깨져 보인다.
        """
        if not self._show_markers:
            return
        forward = self.scene.forward
        key = (round(forward.x, 3), round(forward.y, 3), round(forward.z, 3))
        if not force and key == self._last_forward:
            return
        self._last_forward = key
        for marker in self.markers:
            if marker.axis_set_id in self._hidden_sets:
                continue
            n = marker.direction
            # 카메라가 보는 방향과의 내적. 음수면 카메라 쪽(앞)이다
            toward = n[0] * forward.x + n[1] * forward.y + n[2] * forward.z
            self._marker_labels[marker.id].visible = toward < 0.0

    def rebuild(self, max_step: float) -> None:
        """cut angle 로 family 를 다시 평가하고 호를 갱신한다 (§13).

        slider 를 움직이는 동안 family 의 Turn 이 불법이 될 수 있으므로
        truncate 정책을 쓴다. 잘린 지점은 진단으로 보여준다 (§13.1).
        """
        vp = self.vp
        # 평가 중에 콜백이 self.cut_angles 를 바꿔도 영향이 없도록 복사해 넘긴다
        registry, log = evaluate(self.family, dict(self.cut_angles), on_illegal="truncate")
        arcs = build_arcs(registry, max_step=max_step)

        alive = set()
        for arc in arcs:
            if arc.provenance.origin_axis_set in self._hidden_sets:
                continue
            alive.add(arc.id)
            pts = [vp.vector(*p) for p in arc.points]
            color = vp.vector(*self.color_for(arc))
            existing = self._curves.get(arc.id)
            if existing is None:
                # retain 을 주면 안 된다. retain 은 링 버퍼 상한이라 생성 시점의
                # 점 개수로 고정되고, 나중에 더 촘촘한 tessellation 으로 갱신할 때
                # 앞쪽 점이 버려져 호가 잘린다.
                self._curves[arc.id] = vp.curve(pos=pts, color=color, radius=ARC_RADIUS)
            else:
                # 객체 재생성 없이 좌표만 갱신 (§11 렌더 객체 pool)
                existing.clear()
                existing.append(pts)
                existing.color = color

        for arc_key in list(self._curves):
            if arc_key not in alive:
                self._curves.pop(arc_key).visible = False

        if self.status is not None:
            trunc = [r for r in log if isinstance(r, Truncated)]
            note = ""
            if trunc:
                t = trunc[0]
                note = (
                    f"  |  각도 변경으로 연산 #{t.op_index}({t.axis_id}) 이후 "
                    f"{t.remaining}개가 불가능해짐: {t.reason}"
                )
            if self._hidden_sets:
                # 숨긴 것을 "절단이 없다" 로 오독하면 회전 합법성을 잘못
                # 추론한다. 재료는 그대로 있고 그리지 않을 뿐이다
                hidden = ", ".join(sorted(self._hidden_sets))
                note += f"  |  숨긴 축 집합: {hidden} (재료는 그대로 있다)"
            newline = chr(10)
            self.status.text = (
                newline
                + f"  carrier {len(registry)}  호 {len(arcs)}  "
                + f"총 호 길이 {registry.total_arc_length():.3f}{note}"
                + newline
            )


    def tick(self, settle: float = 0.25) -> None:
        """메인 루프에서 호출한다. 재생성은 전부 여기서 일어난다.

        vpython slider 에는 release 이벤트가 없으므로, 값이 멎은 것을 시간으로
        감지해 고화질로 다시 만든다 (§12.3).

        카메라가 돌면 축 라벨의 앞뒤가 바뀌므로 매 프레임 확인한다. 방향이
        그대로면 바로 빠진다.
        """
        self._update_label_facing()
        now = time.time()
        if self._dirty and now - self._last_render >= MIN_REBUILD_INTERVAL:
            self._dirty = False
            self._last_render = now
            self.rebuild(DRAG_STEP)
        elif self._needs_final and not self._dirty and now - self._last_change > settle:
            self._needs_final = False
            self._last_render = now
            self.rebuild(FINAL_STEP)


def run(
    family: PuzzleFamily,
    cut_angles: dict[str, float],
    axis_set_colors: dict[str, tuple[float, float, float]] | None = None,
    sphere_opacity: float = SPHERE_OPACITY,
) -> None:
    import vpython as vp

    view = SphereView(family, cut_angles, axis_set_colors, sphere_opacity)
    while True:
        vp.rate(30)
        view.tick()
