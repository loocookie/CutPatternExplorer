# Cut Pattern Explorer

A spherical cut-pattern engine. It models **only the cut boundaries on the unit
sphere** — there are no piece models.

You write a puzzle definition in Python and get the cut pattern. Cut angles are
sliders, so a whole family of puzzles is one definition.

**[Open it in your browser](https://loocookie.github.io/CutPatternExplorer/)**
— nothing to install, and definitions run entirely on your machine.

- Design and the reasoning behind it: [`docs/design.md`](docs/design.md) (Korean)
- Browser build: `web/` (Pyodide + Canvas 2D)

## It follows pCubes

The way a puzzle is expressed here is taken wholesale from
**[pCubes](https://github.com/BMouradov/pCubes)** by Boris Mouradov. Not the
file format — the model:

- a puzzle is a set of **axes**, and a cut is a circle on the sphere given by an
  axis and a **cut angle** from it
- the only two primitives are **split by an axis** and **turn a cap by an
  angle**, and everything else is those two composed
- the `Turn … Split … Undo` idiom — turn into a position, cut there, put it back
  — is pCubes'. It is `with turned(...)` here

If you know pCubes, you already know how to think in this tool.
[The XML reference](https://github.com/BMouradov/pCubes/blob/main/Lazarus_sources/ReadMe.txt)
is worth reading; `docs/design.md` §9.4 maps its commands onto this engine one
by one, including the ones that are refused.

What is different is the representation and the authoring layer. This engine
stores **only the cut boundaries** and has no piece model, so it cannot do
anything piece-shaped (bandaging, jumbling into a physical state); in exchange a
cut angle can be a slider and a whole family of puzzles is one definition. And
the definition is a Python script rather than XML, which is why there is no
parser here and no `Script`/`Macro`/`ExecMacro` to reinvent control flow with
(§9.1).

## Running it locally

The Pyodide runtime is not in this repository (12 MB). Fetch it once:

```
python web/fetch_pyodide.py
```

It downloads five files into `web/pyodide/` and checks them against
`web/pyodide.sha256`. There is no CDN fallback on purpose: the page must load
the runtime from its own origin so that `connect-src` can be locked down. If you
skip this step the page fails loudly with a 404 rather than quietly reaching out
to a CDN.

```
python -m http.server 8000
```

Open `http://localhost:8000/web/`. Pyodide does not start from `file://`.

To view an example in the development viewer (vpython):

```
python examples/octocube_master.py
```

## Writing a definition

**A definition is a script.** No function to wrap it in, nothing to `return` —
a `with puzzle(...)` block is all it takes.

```python
c1 = cube("Cube 1")

with puzzle("OctoCube Master", c1) as p:
    split(c1)
    for x in c1:
        with turned(x, 45):
            split(*at_angle(x, 90, c1))
```

- No `import` needed. The authoring layer is already in scope; the full list is
  under **Names in scope** in the editor
- **Each axis set gets its own cut-angle slider.** The argument list of
  `puzzle(...)` is the slider list
- Axis sets can also be inserted from the **Add axis set** menu. The menu writes
  code — nothing is hidden

The definitions under `examples/` are importable modules, so they are wrapped in
`def build(): ... return p`. The editor has no such constraint.

For the full language — every function in scope, `turned`/`attach`/`region`,
the axis-picking queries, and worked examples — see
[docs/writing-definitions.md](docs/writing-definitions.md).

### Naming

```
set id      Cube 1, Rhombic Dodecahedron 1     display text, shown on the slider
axis id     c1-0, rd1-3                        <set abbreviation>-<axis name>
```

The abbreviation comes from the set id: the first letter of each word plus any
trailing number. That is what keeps axis ids unique when the same solid appears
more than once.

## The view

| | |
|---|---|
| drag | rotate (arcball) |
| wheel | zoom |
| two-finger pinch | zoom |

Zoom is centred on the sphere, from 0.4x to 8x.

## Editor

| | |
|---|---|
| `Tab` / `Shift+Tab` | indent / outdent by 4 spaces |
| `Enter` | one level deeper after a line ending in `:` |
| `Esc` then `Tab` | move focus instead of indenting |
| `Ctrl+Enter` | run |

Click the number above a slider to type an exact angle — the slider steps in
0.05°, which never lands on values like 54.7356°.

**Copy share link** puts the definition in the URL. Opening such a link fills
the editor but **does not run anything** — it is someone else's code, so you
read it and press Run.

## Tests

```
python -m pytest -q          # engine, and the Python that runs in the browser
node web/syntax.test.js      # the browser JS actually parses
node web/render.test.js      # silhouette splitting and drawing
node web/editor.test.js      # indentation
node web/share.test.js       # link round-trip
node web/revoke.test.js      # the network paths really do close
```

Generated files are rebuilt with `python web/bundle_engine.py`. Tests catch them
when they go stale.

## Note on language

Code comments and `docs/design.md` are in Korean; everything a user sees is in
English. The comments carry the reasoning behind each decision and are worth
more to a maintainer than a translation would be.

## How it was built

Written with [Claude Code](https://claude.com/claude-code), working from the
design in `docs/design.md`. That document came first and is still the source of
truth: every non-obvious decision is written down there with the reasoning that
produced it, and the code cites its section numbers.
