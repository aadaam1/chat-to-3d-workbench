# Timber table

Standard timber and sheet materials with real prices, for working out what to
buy for a timber structure. There's no open dataset of timber sizes and
prices, so the workbench keeps its own: dated snapshots of real timber yards'
price lists, one region and supplier at a time.

```
prices/<region>-<supplier>-<YYYY-MM-DD>.csv        the snapshot the tools read
prices/raw/<region>-<supplier>-<YYYY-MM-DD>.txt    the price list it was made from
```

A snapshot is the supplier's public price list as read on its date, with
the page it came from. It is not an offer: prices change, so check them
with the supplier before you buy.

## Using it

```bash
.venv/bin/python tools/timber.py classify 50x100
```

```bash
.venv/bin/python tools/timber.py sections
```

```bash
.venv/bin/python tools/timber.py buy 50x100 2400 12 --variant impregnated
```

`classify` names a section (Hungarian and English); `sections` lists every
section on offer with its variants, stock lengths and price per m³; `buy`
finds the cheapest stock length for a number of cuts, counting how many cuts
fit in each length with the saw blade's width, and shows the offcuts. It adds
10% spare cuts by default, rounded up, because no timber is perfect: knots,
splits, twisted pieces and the odd miscut. Change it with `--waste 5`, or
`--waste 0` for none. The
newest snapshot for the region is used unless `--snapshot` names one.

## The library

```
library/eu.json     Europe: metric sections, 600 mm spacing, 1250 x 2500 mm sheets, grade C24
library/us.json     United States: dressed nominal lumber, 16 in on centre, 4 x 8 ft sheets, grade SPF No. 2
```

What the price snapshots can't say: what a "2x4" really measures, how many
nails or screws a joint takes, how strong the timber is. The library holds that, one
file per region, for the timber-structure tools. Everything is in
millimetres (a 2x4 is 38 x 89 mm); the `units` setting of a project only
changes how lengths are shown.

| Block | Holds |
|---|---|
| `sections` | actual thickness and width, stock lengths, usual uses (the planner picks a section for a role by these) |
| `sheets`, `cladding` | thickness, sheet size, board and cover width; a cladding may list `order_lengths_mm` (special-order lengths, used only for a board longer than the stocked ones) |
| `fasteners`, `joint_rules` | nails (size, count per kg or lb, box sizes) and structural screws (pack sizes); fasteners per joint type |
| `grades` | bending strength, stiffness and density (C24 from EN 338; SPF No. 2 from the NDS Supplement) |
| `defaults` | spacings (and `spacing_steps_mm`, the ladder the planner steps down), default item per role, loads, minimum roof pitch per covering |
| `bought` | roofing felt, drip edge, hinges, latch, door, window |
| `sources` | every source, with the date it was read; each block names its sources |

Each block names its `sources`. Anything that could not be checked against a
source that could be read is marked `"unverified": true` (or an `unverified_...`
flag) and must be checked before relying on it; `timberlib.unverified(lib)`
lists them. The EU grade is a characteristic strength and the US one an
allowable-stress design value: different bases, never to be mixed.

From Python (`tools/timberlib.py`):

```python
import timberlib
lib = timberlib.load("us")
timberlib.item(lib, "2x4")                  # the section, with its key and category
timberlib.fmt_length(2400, "imperial")      # 7' 10-1/2"
timberlib.parse_length("7' 10-1/2\"")       # mm; also 2.4 m, 240 cm, 96 in
timberlib.price_for(rows, timberlib.item(eu, "50x100"), 3000, "sawn")   # a snapshot row, or None
```

`price_for` matches by actual size and exact length and never prices a
different size: no row, no price. Tests: `.venv/bin/python -m pytest tests/test_timberlib.py`.

## Snapshot columns

| Column | Meaning |
|---|---|
| `region`, `supplier`, `read_date`, `source_url` | where and when the price was read |
| `product` | the supplier's own name for it, unchanged |
| `kind` | `lumber` (sold by the piece, one length) or `sheet` |
| `variant` | `sawn`, `planed`, `impregnated` (lumber); `sheet` |
| `species`, `grade`, `notes` | only where the supplier names them (spruce, larch, C24, dried, tongue and groove) |
| `thickness_mm`, `width_mm`, `length_mm` | as sold; sheets: thickness, then the sheet's short and long side |
| `price_net`, `price_gross`, `currency` | per piece or sheet, as listed |
| `gross_per_m3`, `gross_per_m`, `gross_per_m2` | computed, for comparing sizes and suppliers |

Sizes are the supplier's stated sizes. Planed timber is usually a few mm
smaller than its sawn name (a planed "5×10" is closer to 45×95); where the
supplier lists the planed size itself, the snapshot has it.

## Adding prices

1. Copy the supplier's price tables into a text file in `prices/raw/`: one
   product per line, name, net price and gross price separated by tabs, with
   a `## <page URL>` line above each table. Comment lines start with `#`.
   Claude can do this from the supplier's pages; a price list pasted into
   the chat works too.
2. Run the importer:

   ```bash
   .venv/bin/python tools/timber_import.py prices/raw/FILE.txt prices/FILE.csv --supplier "Name" --region hu --date YYYY-MM-DD
   ```

   It lists any line it can't read rather than guessing; fix those by hand
   or teach the importer the new format.
3. Commit both files. Old snapshots stay, so a design can say which prices
   it used.

Prices go stale and differ by yard: treat a snapshot as an estimate, check
the yard before buying, and change any number you know better.

## Snapshots

| Region | Supplier | Read | What's in it |
|---|---|---|---|
| hu | [Székely Fatelep](https://szekelyfatelep.hu/), Budapest XVI | 2026-11-10 | planks, boards, planed boards, beams and rafters, battens, OSB: 295 products |
