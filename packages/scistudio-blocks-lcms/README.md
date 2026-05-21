# scistudio-blocks-lcms

Phase 11 LC-MS (Liquid Chromatography - Mass Spectrometry) plugin for
SciStudio. Placeholder skeleton; implementation in progress per
`docs/specs/phase11-implementation-standards.md` section 9.4.

## ADR-043 IO format capabilities

The LC-MS IO pilot declares explicit `FormatCapability` records for low-risk
published IOBlocks. These IDs are stable workflow replay keys:

| Capability ID | Direction | Format | Extensions | Fidelity |
|---|---|---|---|---|
| `scistudio-blocks-lcms.ms_raw.mzml.load` | load | `mzml` | `.mzml` | `typed_meta`: `format`, `polarity`, `instrument`, `acquisition_date`, `sample_id` |
| `scistudio-blocks-lcms.ms_raw.mzxml.load` | load | `mzxml` | `.mzxml` | `typed_meta`: `format`, `polarity`, `instrument`, `acquisition_date`, `sample_id` |
| `scistudio-blocks-lcms.ms_raw.raw.load` | load | `raw` | `.raw` | `typed_meta`: `format`, `sample_id` |
| `scistudio-blocks-lcms.ms_raw.d.load` | load | `d` | `.d` | `typed_meta`: `format`, `sample_id` |
| `scistudio-blocks-lcms.peak_table.csv.load` | load | `csv` | `.csv` | `typed_meta`: `source`, `polarity` |
| `scistudio-blocks-lcms.peak_table.tsv.load` | load | `tsv` | `.tsv` | `typed_meta`: `source`, `polarity` |
| `scistudio-blocks-lcms.peak_table.xlsx.load` | load | `xlsx` | `.xlsx`, `.xls` | `typed_meta`: `source`, `polarity` |
| `scistudio-blocks-lcms.mid_table.csv.load` | load | `csv` | `.csv` | `typed_meta`: `tracer_atoms`, `sample_columns`, `corrected`, `correction_tool` |
| `scistudio-blocks-lcms.mid_table.tsv.load` | load | `tsv` | `.tsv` | `typed_meta`: `tracer_atoms`, `sample_columns`, `corrected`, `correction_tool` |
| `scistudio-blocks-lcms.mid_table.xlsx.load` | load | `xlsx` | `.xlsx`, `.xls` | `typed_meta`: `tracer_atoms`, `sample_columns`, `corrected`, `correction_tool` |
| `scistudio-blocks-lcms.sample_metadata.csv.load` | load | `csv` | `.csv` | `typed_meta`: `sample_id_column` |
| `scistudio-blocks-lcms.sample_metadata.tsv.load` | load | `tsv` | `.tsv` | `typed_meta`: `sample_id_column` |
| `scistudio-blocks-lcms.sample_metadata.xlsx.load` | load | `xlsx` | `.xlsx`, `.xls` | `typed_meta`: `sample_id_column` |
| `scistudio-blocks-lcms.table.csv.save` | save | `csv` | `.csv` | `pixel_only` |
| `scistudio-blocks-lcms.table.tsv.save` | save | `tsv` | `.tsv` | `pixel_only` |
| `scistudio-blocks-lcms.table.xlsx.save` | save | `xlsx` | `.xlsx` | `pixel_only` |

Raw acquisition formats are declared as one-way load capabilities. They do not
declare `roundtrip_group` because SciStudio records paths and lightweight typed
metadata while external LC-MS tools own scan-level parsing and vendor export.

<!-- TODO(#1204): Complete published-package hard-validation migration beyond this ADR-043 pilot.
  Out of scope per ADR-043 §9 and issue #1213 pilot scope.
  Followup: https://github.com/zjzcpj/SciStudio/issues/1204.
-->
