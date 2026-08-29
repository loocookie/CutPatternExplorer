import math
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))

from cutpattern import solids as S
from cutpattern.dsl import at_angle, outside, puzzle, region, split, merge

# pCubes Script:  W := 0.5;  D := 0.45 * W.  내접구 반지름 W 로 정규화
CUT_OFFSET = 0.45
THETA_DEG = math.degrees(math.acos(CUT_OFFSET))

SLICE_ANGLE = 45.0


def build(slice_angle: float = SLICE_ANGLE):
    faces = merge("crd", S.cube(), S.rhombic_dodecahedron())
    pair = lambda a: [a, at_angle(a, 180, faces)[0]]
    axis_pairs = {
        "X": pair(faces["c2"]),
        "Y": pair(faces["c3"]),
        "Z": pair(faces["c0"]),
    }
    with puzzle("Super Mixup Quantum Cube Air V2", faces) as p:
        split([axis_pairs["X"], axis_pairs["Y"], axis_pairs["Z"]])
        for ax1, ax2 in (("X", "Y"), ("Y", "Z"), ("Z", "X")):
            (a1p, a1m), (a2p, _) = axis_pairs[ax1], axis_pairs[ax2]
            with region(outside(a1p), outside(a1m)):
                split(at_angle(a2p, 90, faces))
    return p


if __name__ == "__main__":
    build().run({"crd": THETA_DEG})
