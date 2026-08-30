"""정적 프로토타입용 장면 내보내기. 설계 문서 §11.2.

Pyodide 를 붙이기 전에 렌더링만 따로 확인하려는 것이다. 둘을 한꺼번에 만들면
로딩 문제와 그리기 문제가 섞여 어느 쪽이 잘못됐는지 알기 어렵다.

    python web/export_scenes.py

`web/scenes.js` 를 만든다. 실제 배포에서는 이 파일이 필요 없다 — Pyodide 가
`build_scene` 을 직접 부르고 리스트를 그대로 넘긴다.
"""

import importlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern.render.scene import build_scene

EXAMPLES = ("octocube_master", "octocube_hide", "octododeca", "mixup_plus", "quantum")


def main() -> None:
    out = {}
    for name in EXAMPLES:
        module = importlib.import_module("examples." + name)
        puzzle = module.build()
        angles = {
            k: getattr(module, "THETA_DEG", getattr(module, "THETA_333", 60.0))
            for k in puzzle.family.cut_angle_inputs()
        }
        registry, _log = puzzle.evaluate(angles, on_illegal="truncate")
        scene = build_scene(registry, puzzle.family)
        out[name] = json.loads(scene.to_json())
        print(f"  {name:18s} 폴리라인 {len(scene):4d}  점 {scene.point_count:6d}")

    target = pathlib.Path(__file__).with_name("scenes.js")
    target.write_text(
        "// python web/export_scenes.py 가 만든다. 손으로 고치지 않는다.\n"
        "window.SCENES = " + json.dumps(out, separators=(",", ":")) + ";\n",
        encoding="utf-8",
    )
    print(f"  -> {target.name}  {target.stat().st_size / 1024:.0f}KB")


if __name__ == "__main__":
    main()
