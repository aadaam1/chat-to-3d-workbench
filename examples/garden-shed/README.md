# Garden shed

The worked example for timber structures: a 3 × 2 m mono-pitch shed with a
door in the front and a window in the left wall, in European sizes.

- [`shed.json`](shed.json) is the whole design: size, heights, openings and
  loads. Everything else has a default.
- `./build.sh` makes the frame, the checks and the shopping list in `out/`
  (not committed), priced from the Hungarian timber snapshot in
  `data/timber/prices/`.

```bash
examples/garden-shed/build.sh
```

Then the preview command it prints shows the shed in 3D: layers, an
exploded view, the checks and the shopping list.

This is an example, not a building plan. The checks are simple formulas, not
structural engineering, and local rules may apply.
