"""Mixup Plus.

실행:
    python examples/mixup_plus.py

Mixup 계열의 핵심은 슬라이스를 45도 돌리는 것이다. 우리 모델에서 슬라이스는
원시 연산이 아니라 합성이다 (§7).

    M 슬라이스를 U 축으로 45도  =  turn(U, 45, outer=True)   U cap 을 뺀 나머지
                                    turn(D, 45)              D cap 을 되돌림

두 회전 모두 경계원이 U 원과 D 원이고, 둘 다 완전하므로 합법이다. D 원은 U 축과
동축이라 첫 회전에서 자기 자신으로 가므로 두 번째 회전도 합법이다.

45도 슬라이스가 만드는 것
-------------------------
띠 안의 R/L/F/B 호가 45도 자리로 옮겨간다. 그런데 그 자리에 원래 있던 호와는
**법선 기울기가 다르다**. 방위각 22.5 의 호는 F 원(법선 방위각 90)에서 오고,
그 자리로 오는 호는 R 원(법선 방위각 0)에서 오기 때문이다. 적도에서 같은 점을
지나지만 서로 다른 원이다.

그래서 45도 상태에서는 R/L/F/B 원이 결손이고 면 회전이 불법이다. 그 어긋남이
만드는 얇은 조각을 **실제 조각으로 인정**한 것이 Mixup Plus다. 그러려면 45도
자리의 절단을 영구 절단으로 넣어야 하고, 그게 아래 블록이다.

    슬라이스를 45도 돌린 상태에서 split -> 되돌리기

되돌릴 때 새로 넣은 호가 -45도 자리로 실려 나가면서 새 절단이 된다.
OctoCube Master 와 같은 구조다.

절단 깊이
---------
**90도보다 깊게 자른다** (§2.4). 믹스업은 2x2x2 보다 안쪽으로 자른 것이고,
그래야 마주 보는 두 cap 이 겹쳐 가운데 층이 생긴다. 그 층은 코어를 데리고
돌지 않는다 — 그런 퍼즐은 코어를 구형으로 만들어 가운데 층이 그 둘레를
미끄러지게 한다.

90도 아래에서는 outer 회전이 코어를 싣고 돌아 다른 퍼즐이 된다. slider 를
90도 너머에서 움직여야 이 정의가 뜻하는 것을 본다.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import at_angle, puzzle, split, turned

SLICE_ANGLE = 45.0

# 작동점. 90도보다 깊어야 한다 (위 "절단 깊이")
THETA_MIXUP = 100.0

# 참고: 표준 3x3x3
THETA_333 = math.degrees(math.acos(1.0 / math.sqrt(3.0)))


def build(slice_angle: float = SLICE_ANGLE):
    faces = S.cube("cube", turns=(45, -45, 90, -90, 180))

    with puzzle("Mixup Plus", faces) as p:
        split(faces)
        for x in faces:
            opposite = at_angle(x, 180, faces)[0]
            # x 의 절단원을 경계로 바깥쪽 + 반대쪽 cap 되돌리기 = 슬라이스 회전
            with turned(x, slice_angle, outer=True):
                with turned(opposite, slice_angle):
                    # 어긋난 자리를 영구 절단으로 인정한다
                    split(faces)
    return p


if __name__ == "__main__":
    build().run({"cube": THETA_MIXUP})
