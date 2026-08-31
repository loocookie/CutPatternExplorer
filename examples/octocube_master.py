r"""OctoCube Master (Dayan / pCubes XML) 를 이 엔진의 DSL 로 옮긴 것.

실행:
    python examples/octocube_master.py

pCubes 원본 구조
----------------
    <Script>  W := 0.5;  D := 0.45 * W;  </Script>
    <Axes TurningAngles="Pi/4" PlaneDistances="-D; D" TurnAxesWithLayer="1">
        <Axis NormVector="1;0;0"/> <Axis NormVector="0;1;0"/> <Axis NormVector="0;0;1"/>
    </Axes>
    <Figure>
        <LoadFrom File="Figures\Cube.xml"/>
        <SplitByAxes/>
        <Macro Name="Split">
            <Hide Axis="Ax1" Layer="0"/>  <Hide Axis="Ax1" Layer="2"/>
            <Turn Axis="Ax2" Angle="Pi/4" Layer="0"/>
            <Turn Axis="Ax2" Angle="Pi/4" Layer="2"/>
            <SplitByAxes/>
            <Undo/> <Undo/> <ShowAll/>
        </Macro>
        <ExecMacro MacroName="Split" Ax1="0" Ax2="2"/>
        <ExecMacro MacroName="Split" Ax1="1" Ax2="0"/>
        <ExecMacro MacroName="Split" Ax1="2" Ax2="1"/>
        <RemoveGrayParts/>
    </Figure>

엔진으로의 매핑
---------------
축 3개 x PlaneDistances "-D; D" 는 우리 모델에서 면축 6개다 (§2.2).
    +X 축의 절단면  n·x = h     <->  PlaneDistance +D
    -X 축의 절단면 -n·x = h     <->  PlaneDistance -D
따라서 SplitByAxes 는 split(faces) 하나로 대응된다.

매크로 3개(각각 Ax2 의 layer 0 과 2 를 회전)는 면 6개 각각을 45도 회전하는
것과 같다. 그 블록이 아래 with turned(x, 45) 다.

turned() 는 블록 끝에서 정확히 -45 를 넣는다. rollback() 이 아니다. rollback 은
쌓인 회전을 끝에 한꺼번에 되돌리지만, 여기서는 다음 면으로 넘어가기 전에 매번
원상태여야 한다.

x 에 인접한 네 면만 split 해도 충분하다. x cap 을 가로지르는 원은 x 와 수직인
네 면의 원뿐이고, x 자신의 원은 회전 경계라 고정, 반대편 원은 x 축과 동축이라
s~=0 분기로 고정이기 때문이다 (§7.2). 인접 여부는 at_angle(x, 90) 으로 묻는다.

절단 깊이
---------
D = 0.45 * W 이고 W 는 정육면체의 반너비다. 내접구 반지름 W 로 정규화하면
h = D / W = 0.45, 즉 theta = acos(0.45) = 63.2563도.

가져오지 않은 pCubes 요소
-------------------------
- LoadFrom Cube.xml       : 기본 형상은 단위구로 고정 (§1)
- Macro / ExecMacro       : 파이썬 for 문이 대신한다
- Script 의 W, D          : 파이썬 변수가 대신한다
- TurnAxesWithLayer="1"   : 축은 공간에 고정된 cutter 이므로 이미 그 동작 (§2.1)
- RemoveGrayParts         : 조각 모델이 없으므로 해당 없음 (§9.4)
- Hide Axis=Ax1 Layer=0/2 : 지원하지 않는다. 원본은 이걸로 split 을 Ax1 의
  가운데 층으로 제한한다. 우리 Split 은 구면 전체에 적용되므로 결과 패턴에
  원본보다 절단이 더 많이 생긴다. 영역 제한 split 은 §6.1 의 확장 항목이다.
"""

import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import at_angle, puzzle, split, turned

TURN_ANGLE = 45.0

# pCubes Script:  W := 0.5;  D := 0.45 * W
W = 0.5
D = 0.45 * W

# 내접구 반지름 W 로 정규화
CUT_OFFSET = D / W
THETA_DEG = math.degrees(math.acos(CUT_OFFSET))


def build(turn_angle: float = TURN_ANGLE):
    faces = S.cube(turns=(45, -45, 90, -90, 180))

    with puzzle("OctoCube Master", faces) as p:
        split(faces)
        for x in faces:
            with turned(x, turn_angle):
                # x 와 수직인 네 축 = x 에 인접한 네 면
                split(*at_angle(x, 90, faces))
    return p


def build_family(turn_angle: float = TURN_ANGLE):
    return build(turn_angle).family


if __name__ == "__main__":
    build().run({"cube": THETA_DEG})
