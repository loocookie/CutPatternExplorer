r"""OctoCube Master 의 구성을 정십이면체에 그대로 옮긴 것.

실행:
    python examples/octododeca.py            뷰어
    python examples/octododeca.py report     진단 출력

구성
----
모든 면 X 에 대해, X 를 **원래 돌리는 각의 절반**만큼 돌리고, X 에 인접한
면들로 split 한 다음 X 를 원상복구한다. 그것이 전부다.

    정육면체    면 회전 90도  →  45도로 돌리고  인접 4면으로 split
    정십이면체  면 회전 72도  →  36도로 돌리고  인접 5면으로 split

인접한 면만 잘라도 충분한 이유는 정육면체와 같다. X 의 cap 을 가로지르는
원은 인접면의 원뿐이고, X 자신의 원은 회전 경계라 고정, 반대편 원은 X 축과
동축이라 s~=0 분기로 고정이다 (§7.2).

정십이면체에서 서로 다른 두 면축 사이각은 직선으로 보면 전부 63.4349도다.
그래서 "인접"은 at_angle(x, 63.4349) 하나로 끝난다.

절단 깊이
---------
쓸모 있는 범위는 [31.7174, 63.4349] 도다.

- 31.7174 = 63.4349 / 2. 이보다 얕으면 인접면 원이 X 의 cap 을 못 건드려
  회전해도 새 절단이 생기지 않는다. 정육면체의 45도(=90/2)에 해당한다
- 63.4349 위로 가면 절단원이 이웃 면의 중심을 넘어간다

기본값은 OctoCube 가 그 밴드 안에서 차지한 위치(40.57%)를 그대로 옮겼다.
정육면체는 [45, 90] 에서 63.2563 이므로, 정십이면체는 44.5851 도다.
slider 로 마음대로 조정하면 된다.

결과
----
면 원 12개는 그대로 남고, 새 절단원 60개가 생긴다. Ih 대칭이다.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import at_angle, puzzle, split, turned

# 정십이면체의 면 회전은 72도. 그 절반이 구성 회전이다
FACE_TURN = 72.0
TURN_ANGLE = FACE_TURN / 2.0

# 서로 다른 면축 사이각 (직선 기준). acos(1/sqrt(5))
ADJACENT_DEG = math.degrees(math.acos(1.0 / math.sqrt(5.0)))

# 쓸모 있는 범위와 기본값 (docstring 참고)
MIN_THETA_DEG = ADJACENT_DEG / 2.0
MAX_THETA_DEG = ADJACENT_DEG
OCTOCUBE_FRACTION = (63.2563 - 45.0) / (90.0 - 45.0)
THETA_DEG = MIN_THETA_DEG + OCTOCUBE_FRACTION * (MAX_THETA_DEG - MIN_THETA_DEG)


def build(turn_angle: float = TURN_ANGLE):
    faces = S.dodecahedron("dodecahedron")

    with puzzle("OctoDodeca", faces) as p:
        split(faces)
        for x in faces:
            with turned(x, turn_angle):
                split(*at_angle(x, ADJACENT_DEG, faces))
    return p


def build_family(turn_angle: float = TURN_ANGLE):
    return build(turn_angle).family


def report() -> None:
    import numpy as np

    sys.stdout.reconfigure(encoding="utf-8")
    p = build()
    reg, _log = p.evaluate({"dodecahedron": THETA_DEG})
    faces = list(p.family.axis_sets[0].axes)
    offset = math.cos(math.radians(THETA_DEG))

    def is_face(n):
        return any(
            np.allclose(n, a.normal, atol=1e-9) or np.allclose(n, -a.normal, atol=1e-9)
            for a in faces
        )

    new = [b for b in reg.non_empty() if not is_face(b.circle.n)]
    complete = sum(reg.find(a.normal, offset)[0].is_complete for a in faces)
    print(f"절단 각 {THETA_DEG:.4f}도  (범위 {MIN_THETA_DEG:.4f} ~ {MAX_THETA_DEG:.4f})")
    print(f"회전 각 {TURN_ANGLE}도  (면 회전 {FACE_TURN}도의 절반)")
    print(f"연산 {len(p.family.operations)}개")
    print(f"carrier {len(reg)}  non-empty {len(reg.non_empty())}")
    print(f"총 호 길이 {reg.total_arc_length():.4f}")
    print(f"면 원 완전 {complete}/{len(faces)}")
    print(f"새 경계 {len(new)}개  길이 "
          f"{sorted({round(b.spans.total_length(), 4) for b in new})}")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        report()
    else:
        build().run({"dodecahedron": THETA_DEG})
