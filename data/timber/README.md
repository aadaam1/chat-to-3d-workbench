# Timber table

Standard timber and sheet materials with real prices, for working out what to
buy for a timber structure. There's no open dataset of timber sizes and
prices, so the workbench keeps its own: dated snapshots of real timber yards'
price lists, one region and supplier at a time.

```
prices/<region>-<supplier>-<YYYY-MM-DD>.csv        the snapshot the tools read
prices/raw/<region>-<supplier>-<YYYY-MM-DD>.tsv    the price list it was made from (older ones: .txt)
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

(`timber.py` and the shopping list differ on prices: `timber.py` reads one snapshot, the
region's most complete lumber list (the one with the most lumber rows). A shopping list, `PRICES=hu tools/build_frame.sh <project>` or
`tools/bom.py --prices hu`, reads the newest snapshot of **every** supplier in the region.
See "Several suppliers" below.)

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
| `variant_aliases` | which snapshot variants may price a library variant (US: a `sawn` member takes a `planed` row, since dimension lumber is sold dressed) |
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
| `kind` | `lumber` (sold by the piece, one length; deck and cladding boards too), `sheet`, `fastener` or `bought` |
| `item` | the library key (`nail-framing`, `ground-screw-76x1000`, `roofing-felt`); required for `fastener` and `bought`, optional for timber (matched by size anyway) |
| `variant` | `sawn`, `planed`, `impregnated` (lumber); `sheet` |
| `species`, `grade`, `notes` | only where the supplier names them (spruce, larch, C24, dried, tongue and groove) |
| `thickness_mm`, `width_mm`, `length_mm` | as sold; sheets: thickness, then the sheet's short and long side |
| `unit`, `pack_qty` | what one price buys: `piece`, `box` (nails: `pack_qty` is the box's weight in kg, in lb for the US), `pack` (screws, bolts: the count), `roll` (felt: the m² it covers), `m2`, `m`, `kg`; for `piece` of a trim, `pack_qty` is its length in m |
| `price_net`, `price_gross`, `currency` | per unit (piece, sheet, box, pack, roll, m, m²), as listed. US: both are the shelf price, **before sales tax** |
| `gross_per_m3`, `gross_per_m`, `gross_per_m2` | computed, for comparing sizes and suppliers |

Snapshots made before `item`, `unit` and `pack_qty` existed lack those columns; they
load with them blank and price timber and sheets as before.

Sizes are the supplier's stated sizes. Planed timber is usually a few mm
smaller than its sawn name (a planed "5×10" is closer to 45×95); where the
supplier lists the planed size itself, the snapshot has it.

## Several suppliers per region

`PRICES=hu tools/build_frame.sh <project>` (or `bom.py --prices hu`) uses the newest snapshot
of **each** supplier in the region (where a later read covers only some of a supplier's pages, the
older snapshot of that supplier still supplies the products the newer one doesn't list; each row
keeps its read date); `PRICES=hu:<supplier-slug>` (the part of the file name between
the region and the date, `szekely-fatelep`) uses one supplier only. `--snapshot <csv>` still
prices from one file. The Czech Republic (`cz`, CZK) uses the `eu` library, the US (`us`, USD) the
`us` one. One region is one currency: snapshots of different currencies are never added together.

Each shopping-list line is priced by the supplier that sells **all of it** cheapest:

- Timber and cladding: the plan is made on that supplier's own stock lengths (each is priced at its
  own length), and the cheapest complete plan across suppliers wins. A supplier that lacks a length
  the plan needs is not a candidate, it simply plans on the lengths it has.
- Sheets: the cheapest price for the sheet.
- Nails: the supplier's boxes of that item (`unit` `box`); the cheapest combination of boxes that
  covers the weight (with the spare). Screws and bolts: its packs; the cheapest combination
  covering the count. The line then shows that supplier's pack sizes, not the library's.
- Felt: by the roll (`pack_qty` m² per roll) or by the m², whichever is cheaper for the area; drip
  edge and ridge cap by the metre or in pieces of `pack_qty` m; the rest by the piece.
- Where one supplier lists an item several times (sizes, finishes), the cheapest combination of
  whole packs that covers the need is used, whatever the finish: the note and the product name
  say what is bought.
- A ground screw's price includes its post bracket, so the `post-base-u` line of a priced ground
  screw is free. Doors, windows and concrete footings are not priced (they depend on choices).
- A line no supplier prices in full is left out of the total: "no price", and the total says
  "partial: no price for ...".

Each line records its supplier in `bom.json`; `bom.md`, the cut list (a `supplier` column) and
the site pack show it, and the header lists every supplier used with its read date.

## Adding prices

**A TSV price list** (several suppliers, any kind of item) is a tab-separated file in `prices/raw/`
named `<region>-<supplier-slug>-<YYYY-MM-DD>.tsv`: `# key: value` header lines (`supplier`,
`region`, `read_date`, `currency`, `prices`: `gross (incl. 21% VAT)` or `before sales tax`), then a header
row and one row per product, with the columns `source_url product kind item variant species grade
thickness_mm width_mm length_mm unit pack_qty price_net price_gross notes`. Only a price read on
the supplier's own page, with that page as `source_url`. Fill the price the page shows (the importer
computes the other from the VAT rate; with no rate in the header, a gross price alone is kept and the net left blank), with a decimal point and no thousands separators.
A board or sheet priced per m² or per m (`unit` `m2` or `m`) becomes the price of one piece of the stated size, with a note saying so.

```bash
.venv/bin/python tools/timber_import.py data/timber/prices/raw/FILE.tsv data/timber/prices/FILE.csv
```

**A Hungarian-style text list** (older format): one product per line, name, net price and gross
price separated by tabs, with a `## <page URL>` line above each table, comment lines starting
with `#`. Claude can do this from the supplier's pages; a price list pasted into the chat works
too.

```bash
.venv/bin/python tools/timber_import.py prices/raw/FILE.txt prices/FILE.csv --supplier "Name" --region hu --date YYYY-MM-DD
```

Either way the importer lists any line it can't read rather than guessing; fix those by hand
or teach the importer the new format. Commit both files. Old snapshots stay, so a design can say
which prices it used; only the newest of each supplier is used for new lists.

Prices go stale and differ by yard: treat a snapshot as an estimate, check
the yard before buying, and change any number you know better.

## Snapshots

| Region | Supplier | Read | What's in it |
|---|---|---|---|
| hu | [Székely Fatelep](https://szekelyfatelep.hu/), Budapest XVI | 2026-11-10 | planks, boards, planed boards, beams and rafters, battens, OSB: 295 products |
| hu | [Larex Fatelep](https://www.fatelep.hu/), Budapest | 2026-11-17 | planed boards, deck and cladding boards, battens, beams (50 products), OSB (4), nails, screws and bolts (12), joist hangers, post bases, felt (9) |
| hu | [Praktiker Hungary](https://www.praktiker.hu/) | 2026-11-17 | boards, battens, posts and deck boards (14), OSB (3), nails, screws and bolts (7), felt, trims, hinges, latch, joist hangers, post base (12) |
| hu | [Székely Fatelep](https://szekelyfatelep.hu/), Budapest XVI (a second read: pages the 2026-11-10 read lacks) | 2026-11-17 | cladding and deck boards (7), screws and bolts (5), ground screws and post bases (9); the 2026-11-10 timber stays in use |
| hu | [Drevotta Talajcsavar](https://talajcsavar.hu/) | 2026-11-17 | ground screws and U post brackets (5); no sections |
| cz (CZK, `eu` library) | [Hornbach Czech Republic](https://www.hornbach.cz/) | 2026-11-17 | sawn, impregnated and planed timber, deck boards (84), OSB (4), nails, screws and bolts (12), felt, trims, hinges, latch, joist hangers, post bases (15); online prices; sheets priced per m² on the page, turned into the price of a 1250 × 2500 sheet |
| us (USD, before sales tax) | [Menards](https://www.menards.com/) | 2026-11-17 | dimension lumber 1×4 to 6×6, deck boards (72), OSB (4), nails, deck and structural screws, bolts (14), felt, trims, hinges, latch, hangers, post caps and bases, pier blocks (13); online prices, no store selected, rebates not deducted |
