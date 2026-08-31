# Cut Pattern Explorer

구면 cut pattern 엔진. 조각 모델 없이 **단위구 위의 절단 경계만** 다룬다.

퍼즐 정의를 파이썬으로 쓰면 절단 패턴이 나온다. 절단 각도는 슬라이더로 바꾼다.

- 설계와 그 근거: [`docs/design.md`](docs/design.md)
- 브라우저 판: `web/` (Pyodide + Canvas 2D)

## 돌려 보기

```
python -m http.server 8000
```

`http://localhost:8000/web/` 를 연다. Pyodide 는 `file://` 에서 뜨지 않는다.

개발용 뷰어(vpython)로 예제를 보려면:

```
python examples/octocube_master.py
```

## 정의 쓰는 법

**정의는 스크립트다.** 함수로 감싸거나 `return` 할 것 없이 `with puzzle(...)`
블록만 있으면 찾아서 쓴다.

```python
c1 = cube("Cube 1")

with puzzle("OctoCube Master", c1) as p:
    split(c1)
    for x in c1:
        with turned(x, 45):
            split(*at_angle(x, 90, c1))
```

- `import` 를 쓰지 않아도 된다. 저작 계층 이름이 미리 들어가 있다.
  전체 목록은 편집창의 **바로 쓸 수 있는 이름** 에 있다
- **축 집합마다 절단 각도 슬라이더가 하나씩** 붙는다. `puzzle(...)` 의 인자
  목록이 곧 슬라이더 목록이다
- 축 집합은 **축 집합 추가** 메뉴로 넣을 수도 있다. 메뉴는 코드를 쓴다

`examples/` 의 정의들은 import 가능한 모듈이라 `def build(): ... return p` 로
감싸여 있다. 편집창에는 그 제약이 없다.

### 이름 규칙

```
집합 id    Cube 1, Rhombic Dodecahedron 1     슬라이더에 나오는 표시용 텍스트
축 id      c1-0, rd1-3                        <집합 약자>-<축 이름>
```

약자는 집합 id 의 낱말 첫 글자와 끝 숫자에서 나온다. 그래서 같은 입체가 여러
벌 있어도 축 id 가 겹치지 않는다.

## 편집창

| | |
|---|---|
| `Tab` / `Shift+Tab` | 4칸 들여쓰기 / 내어쓰기 |
| `Enter` | 콜론으로 끝난 줄이면 한 단 더 들어간다 |
| `Esc` 다음 `Tab` | 원래대로 포커스 이동 |
| `Ctrl+Enter` | 실행 |

슬라이더의 숫자를 누르면 정확한 각도를 직접 넣을 수 있다.

**공유 링크 복사** 는 정의를 URL 에 실어 준다. 링크를 열면 편집창에 채워지지만
**자동으로 실행되지는 않는다** — 남이 쓴 코드이므로 읽고 누른다.

## 테스트

```
python -m pytest -q          # 엔진과 브라우저 쪽 파이썬
node web/syntax.test.js      # 브라우저 JS 가 파싱되는가
node web/render.test.js      # 실루엣 자르기와 그리기
node web/editor.test.js      # 들여쓰기
node web/share.test.js       # 링크 왕복
```

생성물은 `python web/bundle_engine.py` 로 다시 만든다. 낡으면 테스트가 잡는다.
