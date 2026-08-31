"""OctoCube Master — pCubes 원본 구조 그대로, `Hide` 포함.

실행:
    python examples/octocube_hide.py            뷰어
    python examples/octocube_hide.py report     진단 출력

pCubes 원본
-----------
    <Macro Name="Split">
        <Hide Axis="Ax1" Layer="0"/>            정지 재료를 잠시 치운다
        <Hide Axis="Ax1" Layer="2"/>
        <Turn Axis="Ax2" Angle="Pi/4" Layer="0"/>
        <Turn Axis="Ax2" Angle="Pi/4" Layer="2"/>
        <SplitByAxes/>                          남은 것만 자른다
        <Undo/> <Undo/> <ShowAll/>
    </Macro>
    <ExecMacro MacroName="Split" Ax1="0" Ax2="2"/>
    <ExecMacro MacroName="Split" Ax1="1" Ax2="0"/>
    <ExecMacro MacroName="Split" Ax1="2" Ax2="1"/>

Layer 0 과 2 는 Ax1 의 바깥 두 층이다. 둘을 숨기면 가운데 슬라이스만 남고,
그것이 region(outside(x), outside(x−)) 이다. Ax2 의 바깥 두 층은 같은 방향으로
45도 돌아간다.

결과
----
면 원 6개는 온전히 남고, 모서리 방향 절단원 12개가 새로 생긴다. 매달린
절단은 없다. 세 매크로의 (숨기는 축, 도는 축) 짝이 3-순환이고 회전 방향도
한쪽이라 대칭은 T 까지다. 영역 없는 근사판(octocube_master.py)은 구면
전체를 자르므로 절단이 더 많고 O 대칭이 된다.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import at_angle, outside, puzzle, region, split, turned

# pCubes Script:  W := 0.5;  D := 0.45 * W.  내접구 반지름 W 로 정규화
CUT_OFFSET = 0.45
THETA_DEG = math.degrees(math.acos(CUT_OFFSET))

SLICE_ANGLE = 45.0


def build(slice_angle: float = SLICE_ANGLE):
    faces = S.cube("cube")
    pair = lambda a: (a, at_angle(a, 180, faces)[0])
    axis_pairs = {
        "X": pair(faces["c-2"]),
        "Y": pair(faces["c-3"]),
        "Z": pair(faces["c-0"]),
    }

    with puzzle("OctoCube Master (Hide)", faces) as p:
        split(faces)
        for ax1, ax2 in (("X", "Z"), ("Y", "X"), ("Z", "Y")):
            (a1p, a1m), (a2p, a2m) = axis_pairs[ax1], axis_pairs[ax2]
            with region(outside(a1p), outside(a1m)):
                with turned(a2p, slice_angle):
                    with turned(a2m, -slice_angle):
                        split(faces)
    return p


def report() -> None:
    import numpy as np

    sys.stdout.reconfigure(encoding="utf-8")

    from cutpattern.engine.operations import SplitResult

    p = build()
    reg, log = p.evaluate({"cube": THETA_DEG})
    faces = p.axis_sets[0]
    normals = [a.normal for a in faces]

    def is_face(n):
        return any(
            np.allclose(n, f, atol=1e-9) or np.allclose(n, -f, atol=1e-9)
            for f in normals
        )

    new = [b for b in reg.non_empty() if not is_face(b.circle.n)]
    complete = sum(reg.find(a.normal, CUT_OFFSET)[0].is_complete for a in faces)
    print(f"연산 {len(p.family.operations)}개")
    print(f"carrier {len(reg)}  non-empty {len(reg.non_empty())}")
    print(f"총 호 길이 {reg.total_arc_length():.4f}")
    print(f"면 원 완전 {complete}/{len(faces)}")
    print(f"새 경계 {len(new)}개  길이 "
          f"{sorted({round(b.spans.total_length(), 4) for b in new})}")

    bad = [(r.axis_id, d) for r in log if isinstance(r, SplitResult) for d in r.dangling]
    print(f"\n매달린 끝점 {len(bad)}개")
    for axis_id, (t, c, point) in bad[:10]:
        print(f"  축 {axis_id}  t={t:.6f}  제약 {c}  점 {tuple(np.round(point, 4))}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        build().run({"cube": THETA_DEG})
