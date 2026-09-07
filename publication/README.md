# Publication material

Supplementary figures generated from the synthetic exports. The clinical
application figures of the SoftwareX manuscript are documented separately in
the reproducibility supplement.

```
make_figures.py     generates this directory's five figures from tests/fixtures/synthetic/
test_figures.py     checks that they reproduce
figures/            the generated figures
```

The input data deliberately does not live here but under
`tests/fixtures/synthetic/` — the same files the test suite and
`examples/verify.sh` use. A second copy would only drift apart.

## Generating

```bash
python publication/make_figures.py
pytest publication/test_figures.py
```

No server, no database, no patient data. An installed checkout with the
numerical and plotting dependencies is required.

## The figures

| File | What it shows |
| --- | --- |
| `map_ensite.png` | EnSite X export: bipolar voltage with a low-voltage area and border zone, plus the 64 measurement points |
| `map_carto.png` | CARTO export of the same surface: activation time, late in the same area |
| `area_per_interval.png` | Area per voltage interval — the same server-side operation the area examples use |
| `scalar_histograms.png` | Value distribution for both vendors |
| `cross_vendor_delta.png` | CARTO minus EnSite X on the same surface |

## On the last figure

It is **not** a clinical difference. Both exports carry the same field; what is
shown is where the two decode paths diverge — computed with the same
`compare_maps()` operation a real map-versus-map comparison uses. The residual
is **5·10⁻⁵ mV** and is the rounding difference of the files generated here; it
is not a general accuracy limit of the vendor formats. `test_figures.py` pins
this value: a regression in either reader would shift it by orders of magnitude
and make the caption wrong.

## What this material establishes

That the processing chain runs from vendor file to analysis completely and
reproducibly, for both formats.

It does **not** establish that the field meanings are clinically correct — that
needs real exports, which are not part of this repository. See
`tests/fixtures/synthetic/README.md`.
