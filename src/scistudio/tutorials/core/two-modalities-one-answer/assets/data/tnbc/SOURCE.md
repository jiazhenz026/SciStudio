# Where this data comes from

These six files describe two triple-negative breast tumors, CID44971 and
CID4465, derived from one public dataset:

Wu, S.Z., Al-Eryani, G., Roden, D.L. et al. "A single-cell and spatially
resolved atlas of human breast cancers." *Nature Genetics* 53, 1334–1347
(2021). Spatial transcriptomics data archived at Zenodo:
<https://doi.org/10.5281/zenodo.4739739>.

Licensed under the Creative Commons Attribution 4.0 International license
(CC BY 4.0): <https://creativecommons.org/licenses/by/4.0/>.

## About the samples

Each tumor is a 10x Genomics Visium section with a matching H&E image. Every
spot carries a region label assigned by a specialist breast pathologist in
Loupe Browser, published by the authors as the `Classification` column of
their per-sample metadata.

| Sample | Subtype | Spots shipped |
|---|---|---|
| CID44971 | TNBC | 1,159 |
| CID4465 | TNBC | 1,207 |

## What was changed

### Images — `<sample>_he.jpg`

The Space Ranger `tissue_hires_image.png` (2000 px on the long edge) was
resized to 1000 px on the long edge and saved as JPEG (quality 85). No full
resolution H&E is distributed by the authors.

### Masks — `<sample>_mask.png`

**These are derived, not published.** The authors annotated spots, not
pixels; no pathologist drew these images. Each one was composed here from the
published per-spot `Classification` labels, over the slide they were drawn on:

- the H&E is drained to grayscale, so its stain cannot compete with the
  region colors laid over it;
- every annotated spot is painted as a filled disc at its own center, at the
  spot's true diameter (`spot_diameter_fullres`, scaled to the shipped image),
  in a full-strength class color at 60% opacity;
- a key naming only the classes this slide actually carries is drawn beneath
  it, which is why a mask is a little taller than its slide. Its type is set
  large and bold so it stays readable after the preview panel samples the
  picture down to 256 px.

The spots stay discrete — no smoothing, no morphological fill — so the mask
never asserts a boundary between two spots that the annotation does not
support, and the grayscale tissue stays visible in the gaps between them.

The pathologist's vocabulary is per-sample and composite
("Invasive cancer + stroma + lymphocytes"). It is folded into five classes,
each label counting towards the tissue it names first:

| Class | Color | Source labels |
|---|---|---|
| Invasive cancer | `#E41A1C` red | `Invasive cancer`, and its `+ stroma`, `+ lymphocytes`, `+ stroma + lymphocytes`, `+ adipose tissue + lymphocytes` variants; `Cancer trapped in lymphocyte aggregation` |
| DCIS | `#FF7F00` orange | `DCIS` |
| Stroma | `#377EB8` blue | `Stroma`, `Stroma + adipose tissue`, `Adipose tissue` |
| Lymphocytes | `#4DAF4A` green | `Lymphocytes`, `TLS` |
| Normal | `#989898` gray | `Normal + stroma + lymphocytes`, `Normal glands + lymphocytes`, `Normal duct` |

Spots labeled `Uncertain`, `Artefact`, `NA` or blank are not drawn and not
shipped: they name a problem with the slide, not a tissue.

### Counts — `<sample>_counts.csv`

One row per spot. `x` and `y` are the spot's center in pixels on the shipped
1000 px image, converted from Space Ranger's full-resolution coordinates with
`tissue_hires_scalef`. Rows are restricted to spots that carry one of the five
classes above, so the counts and the mask describe the same spots.

The full feature-barcode matrix (19,237 genes) was reduced to a 2,000-gene
panel: 89 canonical breast, stromal, immune, endothelial, adipose and
housekeeping markers, plus the genes ranked most variable jointly across the
sections of this dataset (dispersion rank, averaged per sample). The same
panel is used for every sample. Values are raw UMI counts, not normalized.
