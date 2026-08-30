"""엔진 소스를 브라우저용 한 덩어리로 묶는다. 설계 문서 §19.

    python web/bundle_engine.py

`web/engine.js` 에 `{경로: 소스}` 객체를 만든다. 부팅할 때 Pyodide 파일 시스템에
그대로 써 넣으면 `import cutpattern` 이 된다.

**요청 하나로 끝낸다.** 파일을 개별로 받으면 목록을 따로 유지해야 하고, 그
목록이 어긋나면 브라우저에서만 터진다. 한 덩어리면 어긋날 자리가 없다.

**생성물이지만 커밋한다.** GitHub Pages 는 저장소를 그대로 서빙하므로 (§19.2)
이 파일이 없으면 배포가 조용히 깨진다. 대신 소스와 어긋나지 않는지
`tests/test_web_bundle.py` 가 검사한다.

`render/vpython_view.py` 는 뺀다. vpython 을 import 하는 유일한 파일이고
브라우저에서는 `web/render.js` 가 그 자리를 대신한다 (§11.2).
"""

import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "cutpattern"
TARGET = ROOT / "web" / "engine.js"

# 브라우저에서 쓰지 않고 외부 의존이 있는 것
EXCLUDE = {"render/vpython_view.py"}

HEADER = (
    "// python web/bundle_engine.py 가 만든다. 손으로 고치지 않는다.\n"
    "// worker 안에서 읽으므로 window 가 아니라 globalThis 에 붙인다 (§19.5).\n"
)


def collect() -> dict[str, str]:
    """{`cutpattern/...` 상대 경로: 소스} 를 모은다."""
    out: dict[str, str] = {}
    for path in sorted(PACKAGE.rglob("*.py")):
        if "__pycache__" in path.parts:
            continue
        rel = path.relative_to(PACKAGE).as_posix()
        if rel in EXCLUDE:
            continue
        out["cutpattern/" + rel] = path.read_text(encoding="utf-8")
    return out


def render(sources: dict[str, str]) -> str:
    return HEADER + "globalThis.ENGINE_SOURCES = " + json.dumps(
        sources, ensure_ascii=False, sort_keys=True, indent=0
    ) + ";\n"


def main() -> None:
    sources = collect()
    text = render(sources)
    TARGET.write_text(text, encoding="utf-8")
    total = sum(len(s) for s in sources.values())
    print(f"  파일 {len(sources)}개  소스 {total / 1024:.0f}KB  -> {TARGET.name} {len(text) / 1024:.0f}KB")
    for name in sorted(sources):
        print(f"    {name}")


if __name__ == "__main__":
    main()
