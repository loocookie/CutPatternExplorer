"""설계 문서 §8: U 45도 회전 후 R split.

실행:
    python examples/jumbling_u45.py

faceCut slider 를 움직이면
  - 얕은 각도(~20도)에서는 U cap 에 닿는 호가 없어 회전이 아무것도 옮기지 않는다
  - 3x3x3 각도(54.7356도)에서는 R/L/F/B 호가 U cap 경계에서 쪼개져 45도 돌아간다
  - 이후 split(R) 이 비어 있던 윗층 구간(pi/2)만 채운다
  - 정의가 끝나면 자동 되돌리기가 U -45 를 적용해 원래 6개 원을 복원하고,
    새로 생긴 pi/2 호 하나만 남긴다

여기서는 bare turn 이면 충분하다. 되돌린 뒤 더 할 일이 없기 때문이다.
블록마다 원상태로 만들어야 하는 경우는 turned() 를 쓴다 (octocube_master.py).
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import puzzle, split, turn

# 3x3x3 면 절단의 각반경: 평면 x = 1/sqrt(3)
THETA_333 = math.degrees(math.acos(1.0 / math.sqrt(3.0)))


def build():
    faces = S.cube("faces", turns=(45, -45, 90, -90, 180))

    # 축 id 는 방향을 말해주지 않는다 (`c0`..`c5`). 방향을 박은 id 를 두면
    # axisops.rotate 한 번에 거짓말이 되므로 (§2.2), 이름은 뜻이 있는 이 자리에서
    # 묶는다. 아래 방향은 S.cube() 를 갓 만든 상태 기준이다.
    U = faces["c3"]  # +y
    R = faces["c2"]  # +x. U 에 수직이면 대칭이라 어느 면이든 같다

    with puzzle("U45 then R split", faces) as p:
        split(faces)
        turn(U, 45)
        split(R)
        # 되돌리기는 정의 끝에서 자동
    return p


if __name__ == "__main__":
    build().run({"faces": THETA_333})
