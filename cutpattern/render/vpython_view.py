"""개발용 vpython 뷰어. 설계 문서 §11, §16 단계 1.

반투명 구 + 호 폴리라인 + cut-angle slider.
엔진은 이 모듈을 import 하지 않는다 (§15).
"""

from __future__ import annotations

import time

from ..engine.axes import PuzzleFamily
from ..engine.operations import Truncated, evaluate
from .arcs import build_arcs

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
        self.status = vp.wtext(text="")

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
            min=0.01,
            max=179.99,
            step=0.05,
            value=self.cut_angles[input_id],
            length=520,
            bind=on_change,
        )
        self.sliders[input_id] = slider
        self.scene.append_to_caption("\n")

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
            alive.add(arc.id)
            pts = [vp.vector(*p) for p in arc.points]
            color = vp.vector(*self.color_for(arc))
            existing = self._curves.get(arc.id)
            if existing is None:
                # retain 을 주면 안 된다. retain 은 링 버퍼 상한이라 생성 시점의
                # 점 개수로 고정되고, 나중에 더 촘촘한 tessellation 으로 갱신할 때
                # 앞쪽 점이 버려져 호가 잘린다.
                self._curves[arc.id] = vp.curve(pos=pts, color=color, radius=0.006)
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
        감지해 고화질로 다시 만든다 (§12-4).
        """
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
