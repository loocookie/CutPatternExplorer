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
VOCAB = ROOT / "web" / "vocab.js"

# 브라우저에서 쓰지 않고 외부 의존이 있는 것
EXCLUDE = {"render/vpython_view.py"}

HEADER = (
    "// python web/bundle_engine.py 가 만든다. 손으로 고치지 않는다.\n"
    "// worker 안에서 읽으므로 window 가 아니라 globalThis 에 붙인다 (§19.5).\n"
)


def collect() -> dict[str, str]:
    """{경로: 소스} 를 모은다. 엔진과 정의 실행 층(`boot.py`)."""
    out: dict[str, str] = {}
    # 정의 실행 층. 엔진이 아니라 브라우저 글루라 web/ 에 둔다
    out["boot.py"] = (ROOT / "web" / "boot.py").read_text(encoding="utf-8")
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


def vocabulary() -> dict[str, list[str]]:
    """편집창이 미리 넣어 두는 이름들 (§19.7).

    정적 데이터다. worker 를 거쳐 가져오면 비동기, 메시지 왕복, Pyodide 의 타입
    변환이 끼어드는데 그중 하나만 어긋나도 목록이 **조용히 빈다**. 번들을 만들
    때 같은 `__all__` 에서 뽑아 두면 그 셋이 다 사라진다.
    """
    sys.path.insert(0, str(ROOT))
    import cutpattern.dsl as dsl
    from cutpattern import solids

    clash = set(dsl.__all__) & set(solids.__all__)
    if clash:
        raise RuntimeError(f"Authoring names collide: {sorted(clash)}")
    return {
        "Definition and queries": list(dsl.__all__),
        "Axis sets": list(solids.__all__),
        "Also": ["math", "S (= solids)"],
    }


def menu() -> dict[str, list[list[str]]]:
    """"축 집합 추가" 메뉴에 올릴 것 (§19.9).

    인자 없이 부를 수 있는 프리셋만 올린다. 각기둥 계열은 `n` 이 필요해서
    빠진다 — 숫자를 받는 자리를 메뉴에 만들면 그때 넣는다.

    `PLATONIC` 과 `CATALAN` 이 여기서 또 값을 한다 (§2.5). 목록을 손으로
    유지하면 프리셋을 늘렸을 때 메뉴에서 조용히 빠진다.
    """
    sys.path.insert(0, str(ROOT))
    from cutpattern import solids

    def entries(catalog):
        out = []
        for key, factory in catalog.items():
            aset = factory()
            out.append([key, "%s (%d)" % (key.replace("_", " "), len(aset))])
        return out

    return {"Platonic": entries(solids.PLATONIC), "Catalan": entries(solids.CATALAN)}


def main() -> None:
    sources = collect()
    text = render(sources)
    TARGET.write_text(text, encoding="utf-8")
    total = sum(len(s) for s in sources.values())
    print(f"  파일 {len(sources)}개  소스 {total / 1024:.0f}KB  -> {TARGET.name} {len(text) / 1024:.0f}KB")

    groups = vocabulary()
    groups_menu = menu()
    header = "// python web/bundle_engine.py 가 만든다. 손으로 고치지 않는다.\n"
    body = "globalThis.VOCAB = " + json.dumps(groups, ensure_ascii=False) + ";\n"
    body += "globalThis.MENU = " + json.dumps(groups_menu, ensure_ascii=False) + ";\n"
    VOCAB.write_text(header + body, encoding="utf-8")
    print(f"  이름 {sum(len(v) for v in groups.values())}개  -> {VOCAB.name}")
    for name in sorted(sources):
        print(f"    {name}")


if __name__ == "__main__":
    main()
