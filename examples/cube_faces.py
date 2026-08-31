"""정적 cut pattern: 면축 하나짜리 축 집합.

실행:
    python examples/cube_faces.py

slider 로 faceCut 각도를 바꾸면 구면 경계가 실시간으로 갱신된다.
theta = 90 이면 마주보는 축이 같은 평면이 되어 원이 6개에서 3개로 줄어든다 (§4.3).
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import puzzle, split

THETA_333 = math.degrees(math.acos(1.0 / math.sqrt(3.0)))


def build():
    faces = S.cube()

    with puzzle("Cube faces", faces) as p:
        split(faces)
    return p


if __name__ == "__main__":
    build().run({"cube": THETA_333})
