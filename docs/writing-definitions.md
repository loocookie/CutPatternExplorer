# Writing Definitions

This is a reference for the language you write puzzle definitions in — the
Python that goes in the editor's code area. For editor mechanics (keyboard
shortcuts, sliders, share links, the two modes) see [README.md](../README.md)
and, if you want the full design rationale, [design.md](design.md) (Korean).

A definition describes a **cutting pattern on the surface of a sphere**: which
axes exist, where great circles are cut around them, and how those circles
move when parts of the puzzle turn. There is no piece model — only the visible
cut boundary.

## 1. The shape of a definition

A definition is a **script**, not a function. There is nothing to wrap it in
and nothing to `return` — a `with puzzle(...)` block is all it takes:

```python
faces = cube("faces")

with puzzle("My Puzzle", faces) as p:
    split(faces)
```

- `cube(...)` builds an axis set (§2 below).
- `puzzle(name, *axis_sets)` opens the puzzle. Its argument list is also the
  **slider list** — one cut-angle slider per axis set you pass here.
- `split(...)` and `turn(...)` are the only two operations; everything else
  (`turned`, `attach`, `region`, the queries) is sugar built from them or from
  plain Python.
- `as p` binds a `Puzzle` object. Inside the editor you never touch it
  directly — it exists mainly for the local vpython dev viewer (`p.run(...)`,
  see the top-level README), which is a separate way of running definitions
  from a terminal, not something the browser uses.

No `import` is needed. Everything below is already in scope — the editor's
**Names in scope** panel lists the exact set for the running build. Explicit
imports still work if you prefer them:

```python
from cutpattern import solids as S
from cutpattern.dsl import puzzle, split, turned
```

Examples under `examples/` in the repository are wrapped in `def build():
... return p` because they are also importable Python modules used by the
test suite. The editor has no such constraint — paste one in and delete the
`def build():` / `return p` lines, or write straight from the block.

## 2. Axis sets

An axis set is a named group of axes. Presets live in `solids`: the 5
Platonic solids (`cube`, `octahedron`, `tetrahedron`, `dodecahedron`,
`icosahedron`) and the 13 Catalan solids (`rhombic_dodecahedron`,
`pentagonal_icositetrahedron`, `triakis_octahedron`, …), all callable with no
arguments — plus `prism(n)` / `antiprism(n)` / `bipyramid(n)` /
`trapezohedron(n)`, which need a side count.

The editor's **Add axis set** menu offers the no-argument presets — the
Platonic and Catalan ones — generated straight from the same catalog this
document would otherwise have to duplicate by hand, so it never goes stale.
The `n`-family isn't in that menu (there's no slot for `n` yet); call it
directly. To see the no-argument catalog from a script:

```python
from cutpattern import solids
for key in {**solids.PLATONIC, **solids.CATALAN}:
    print(key)
```

Give a set its own display name so more than one instance can coexist:

```python
c1 = cube("Cube 1")
c2 = cube("Cube 2")
```

**Axis ids** are `<abbreviation>-<axis name>`, where the abbreviation is
derived from the set's display name (first letters of each word, plus any
trailing number):

```text
Cube 1                  -> c1   -> c1-0 .. c1-5
Rhombic Dodecahedron 1  -> rd1  -> rd1-0 .. rd1-11
```

That derivation is what keeps ids unique when the same solid appears twice —
there is no hand-maintained abbreviation table. Index a set to get one axis,
or iterate it to get all of them:

```python
c1["c1-0"]          # one axis
for x in c1: ...     # all axes in c1
```

If no preset fits, build a set directly from normals:

```python
AxisSet("Custom", axes={"top": (0, 0, 1), "bottom": (0, 0, -1)})
```

**`turns=`** declares which angles this set's axes may turn by:

```python
faces = cube("faces", turns=(45, -45, 90, -90, 180))
```

Leave it out and there is no constraint — any angle turns, like a parameter
with no type annotation. Write it and `turn()` is checked against it when the
`with puzzle(...)` block closes, so a typo fails immediately rather than
quietly drawing the wrong pattern.

**The declaration is in cap terms**, and an `outer=True` turn flips the sign.
Turning the cap by `t` leaves the same pattern as turning the outside by `−t`
(the two differ only by a rotation of the whole sphere), so declaring `-60`
is what opens up `turn(x, 60, outer=True)`. Angles are a circle: `-90` and
`270` are the same declaration. See design.md §7.11.

A list like `45, -45, 90, -90, 180` is closed under sign flip, so cap and
outer accept the same values — that is a property of that particular list,
not a rule.

## 3. The two primitive operations

Everything that changes the puzzle reduces to these two calls.

### `split(...)`

Adds a cut circle around one or more axes. It never removes existing cuts —
splitting the same axis twice is a no-op, not an error. The argument can be
an axis, an axis set, or a (possibly nested) list of either, so all of these
work:

```python
split(faces)                     # every axis in the set
split(x, y)                      # a couple of axes
split(at_angle(x, 90, faces))    # a query result, straight through
split([pair_x, pair_y])          # a list of pairs
```

An empty result is rejected rather than silently accepted — a query that
missed its target (`at_angle(x, 90)` with no set to search) would otherwise
leave behind a definition that looks finished but cuts nothing.

### `turn(axis, angle, outer=False)` / `with turned(axis, angle, outer=False):`

Rotates the material on one side of `axis`'s cut circle by `angle` degrees.
Which side rotates is controlled by `outer` — **not by the `angle` argument.**
`outer=False` turns the cap: material within that axis's own cut angle (the
slider value for its set, already fixed by an earlier `split`) — not within
the rotation amount you're passing in. `outer=True` turns everything else.

A turn is **legal only if that axis's cut circle is already a complete cut**
— nothing splits it into an arc. If it isn't, the whole operation is
rejected and nothing changes; there is no partial state to clean up. That's
why `split(...)` almost always comes before the turns that depend on it.

That legality depends on the current cut angle, so dragging a slider can make
a turn illegal; the app reports it rather than crashing. Separately, if the
axis set declared `turns=`, the angle must be one of the declared ones — that
check is static (it doesn't depend on any slider) and happens as soon as the
`with puzzle(...)` block closes.

`turn` leaves the rotation in place. `with turned(...):` does the same thing
but **rotates back at the end of the block**, so whatever you do inside —
usually another `split` — is recorded relative to the rotated state and then
carried back to where it belongs when the block closes. This is how most
interesting patterns are built: rotate to expose a new position, cut there,
undo the rotation.

```python
faces = cube("faces", turns=(45, -45, 90, -90, 180))

with puzzle("OctoCube Master", faces) as p:
    split(faces)
    for x in faces:
        with turned(x, 45):
            split(*at_angle(x, 90, faces))
```

`with turned(...):` blocks nest freely — each undoes only its own rotation,
in reverse order, when its `with` exits.

## 4. What rides along: `attach(aset, to=host)`

Axes normally stay put while cuts move around them. When a turn should carry
axes with it, what decides is **what those axes are mounted on**.

```python
inner = attach(octahedron("Inner"), to=shell)
```

Every axis set is mounted on something: the **core** by default, or another
axis set. You declare the mount; geometry decides, per turn, whether you are
in the part that moves.

- **Mounted on the core.** You move when the core moves. The core sits on the
  far side of a cut plane at distance `cos θ` from the centre, so it is in the
  outer region while `θ < 90°` — meaning an `outer=True` turn carries it, and
  a cap turn does not. At `θ ≥ 90°` **nothing carries the core**: opposing
  caps overlap, and the band where they meet slides around a spherical core
  without moving it. Mixup-family puzzles live in that range.
- **Mounted on an axis set.** You move when that set turns and your position
  falls inside the moving region — cap or outer alike. What matters is not
  which side is turning but whether you are in it.
- **Chains.** If A is mounted on B and B on the core, A follows B.

Why only half of it is declared: what a mechanism is bolted to cannot be read
off the cut boundary — an axle can pass through a layer into the core, and a
sub-mechanism can sit on a single layer. But *which layer you are currently
in* is already computable, and making you spell that out for every pair of
axes is where a hand-written list goes stale.

Carried axes are excluded from automatic turn-angle derivation (§7.7 in
design.md) — they move with their host, so there is no alignment of their own
to solve for. A turn that carries axes also cannot be conjugated (§7.10), so
it costs more to evaluate.

## 5. Regions: `inside`, `outside`, `with region(...):`

`region` limits which material a block's `split` and `turn` calls can see —
it temporarily hides everything outside the listed constraints, so turns and
splits act only on what's left, then restores it when the block exits.

```python
with region(outside(x), outside(x_opposite)):   # keep only the middle slice
    with turned(z, 45):
        with turned(z_opposite, -45):
            split(faces)
```

`inside(axis)` / `outside(axis)` each pick one side of that axis's cut
circle. **A region's boundary must already be a real cut** — you can't wall
off a region with an axis that hasn't been split yet, because the boundary
has to actually terminate somewhere.

## 6. Picking axes: queries

These are free functions, not methods on the axis set — picking axes is
inherently a relationship between sets, not something one set does alone.
All of them take a **reference first**, then the axes to search (an axis,
axis set, or nested list — same as `split`).

```python
angle_between(a, b)                          # angle in degrees between two axes
at_angle(ref, degrees, *targets, start=None) # axes at exactly that angle from ref
angles_from(ref, *targets)                   # {angle: [axes]} — see what angles exist
nearest(ref, *targets)                       # the single closest axis
group_by_nearest(ref, *targets)              # {ref-axis id: [closest axes]}
axes_of(*targets)                            # flatten axes/sets/nested lists
same_directions(a, b, tol=1e-7)              # do two sets point the same way?
```

`at_angle` returns axes in a **canonical order**: sorted counter-clockwise
around the reference, starting wherever makes the gap sequence
lexicographically smallest. Two geometrically identical rings always come
back in the same order, so `x, y, z = at_angle(...)` reliably assigns the
same axis to the same name every time. Pass `start=` to pick your own
starting axis instead (useful when you need a specific one to land first,
not just a consistent one).

`angles_from` is the tool for exploring an unfamiliar solid — call it first
to see what angles exist, then use those values with `at_angle`.

`ANGLE_TOL_DEG` (`1e-4`) is the default `tol_deg` for `at_angle` and
`angles_from` — pass your own if a solid's angles need a looser or tighter
match.

## 7. Fixing axis sets by hand

`rotate` / `mirror` / `invert` / `remove` / `keep` / `rename` / `merge` each
build and return a **new** axis set — none of them mutate the one you pass
in.

```python
c1 = rotate(cube("Cube 1"), axis=(0, 0, 1), angle=45)
c1 = mirror(cube("Cube 1"), normal=(0, 0, 1))
c1 = invert(cube("Cube 1"))
c1 = remove(cube("Cube 1"), "c1-1")
c1 = rename(cube("Cube 1"), {"c1-0": "c1-top"})
merged = merge("Combined", set_a, set_b)
```

`rotate` accepts one of three forms: `axis=` + `angle=` (an axis and a
rotation), `pairs=[(a, a2), (b, b2)]` (two direction pairs — find the
rotation that sends `a` onto `a2` and `b` onto `b2`), or `quaternion=(w, x,
y, z)`. Give exactly one. `mirror`'s `normal` has no default: an
unspecified mirror plane would be invisible in the code and impossible to
change later. `merge` takes the new id first (it's building something new,
like `puzzle`), where the others take it as a keyword (they're modifying one
thing).

The editor's **Edit…** menu on each axis set writes these calls into your
definition for you — nothing is hidden behind it, and you can write the same
calls by hand once you know the shape. `merge` is not offered in that menu
(see below); everything else is.

## 8. Worked examples

### The smallest definition

```python
faces = cube("faces")

with puzzle("Plain Cube", faces) as p:
    split(faces)
```

Six axes, six cut circles, no turns.

### OctoCube Master

```python
faces = cube("faces", turns=(45, -45, 90, -90, 180))

with puzzle("OctoCube Master", faces) as p:
    split(faces)
    for x in faces:
        with turned(x, 45):
            split(*at_angle(x, 90, faces))
```

Split all six faces, then for each one, rotate 45° and split the four axes
perpendicular to it — recorded in the rotated frame, then carried back when
`with turned` exits. That's what produces the octagonal cut pattern.

### Rose Diamond (the editor's default)

```python
o1 = octahedron("Octahedron 1")
t1 = tetrahedron("Tetrahedron 1", turns=(15, 120, 135, -120, -105))

pair = lambda a: (a, at_angle(a, 180, o1)[0])

rd1 = rhombic_dodecahedron("Rhombic Dodecahedron 1")

with puzzle("Rose Diamond", o1, rd1) as p:
    split(o1)
    for i in range(4):
        x, y = pair(nearest(t1[f"t1-{i}"], o1))
        with turned(x, 15):
            with turned(y, 15):
                split(at_angle(x, 90, rd1, start=t1[f"t1-{(i+1)%4}"])[1::2])
```

`t1` never appears in `puzzle(...)`, so it's never drawn and has no slider —
it exists purely as a **reference**, four fixed directions used only to pick
which octahedron axes to turn. That's what the axis set panel (open it with
**Edit definition**) is for: sets like this one still need to be visible and
editable even though nothing about them shows up in the cut pattern.

For each of the four reference directions: find the nearest octahedron axis
(`x`) and its antipode (`y`, 180° away), rotate both 15°. As long as the
octahedron's cut angle keeps each axis's cap short of the opposite side (true
at the default), rotating `x`'s cap doesn't touch `y`'s own cut circle, so
turning `y` afterward is independently legal too. Then split the
rhombic-dodecahedron axes 90° from `x` — six of them — ordered starting from
the *next* reference direction and keeping every other one (`[1::2]`, three
of the six).

## 9. Common pitfalls

**`'return' outside function`.** If you paste in one of the `examples/*.py`
files verbatim, you'll hit this — those are wrapped in `def build(): ...
return p` because they're also importable test fixtures. Delete the
`def build():` line, its `return p`, and dedent the body.

**Axis id prefix collisions.** `abbrev("cube1")` and `abbrev("Cube 1")` are
both `c1` — the abbreviation only looks at letters and trailing digits, not
spacing. If you name a set by hand in a way that collides with the **Add
axis set** menu's own naming (`<Preset> <N>`), the engine rejects it with an
"axis id … appears in both …" error. Give hand-named sets ids that don't look
like the menu's auto-numbered ones, or let the menu pick the name.

**The slider list is exactly `puzzle(...)`'s argument list.** An axis set
that isn't passed to `puzzle` gets no slider and isn't drawn — which is
correct and useful for reference-only sets (see Rose Diamond above), but
surprising the first time it happens because there's no error, just a
missing slider.

**Shared links don't run automatically.** Opening a `#code=` link loads the
definition into the editor but does not execute it — you read it, then press
Run. This is deliberate: opening a link should never be equivalent to
running someone else's code without a chance to look at it first.
