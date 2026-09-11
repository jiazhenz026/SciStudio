# Where this data comes from

`section_1_he.jpg`, `section_1_counts.csv`, `section_2_he.jpg` and
`section_2_counts.csv` are derived from two public 10x Genomics Visium
datasets:

- "Human Breast Cancer (Block A Section 1)", 10x Genomics —
  <https://www.10xgenomics.com/datasets/human-breast-cancer-block-a-section-1-1-standard-1-1-0>
- "Human Breast Cancer (Block A Section 2)", 10x Genomics —
  <https://www.10xgenomics.com/datasets/human-breast-cancer-block-a-section-2-1-standard-1-1-0>

Both are licensed under the Creative Commons Attribution 4.0 International
license (CC BY 4.0): <https://creativecommons.org/licenses/by/4.0/>.

## About the sample

Two serial 10 µm sections of one fresh-frozen invasive ductal carcinoma
block, H&E stained and imaged on a Nikon Ti2-E, then run on Visium Spatial
Gene Expression. Per 10x: AJCC/UICC Stage Group IIA, ER positive, PR negative,
HER2 positive.

## What was changed

- **Image.** The Space Ranger `tissue_hires_image.png` (2000 × 2000 px) was
  resized to 1000 × 1000 px and saved as JPEG (quality 85).
- **Spots.** Only spots under tissue are kept: 3,798 in section 1 and 3,987 in
  section 2. `x` and `y` are each spot's centre in pixels on the resized image,
  converted from Space Ranger's full-resolution coordinates with
  `tissue_hires_scalef`.
- **Genes.** The full feature-barcode matrix (36,601 genes) was reduced to a
  2000-gene panel shared by both sections: highly variable genes chosen
  jointly over both sections, plus canonical breast-tissue, immune and
  housekeeping markers. Values are raw UMI counts, not normalised.
