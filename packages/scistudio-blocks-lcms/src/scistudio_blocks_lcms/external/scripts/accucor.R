# Default AccuCor driver shipped with scieasy-blocks-lcms.
# Upstream package: https://github.com/lparsons/accucor (v0.3.1)
# License: MIT (see project-level third-party notices handled by packaging work).
#
# Invoked by CodeBlock's R runner with:
#   inputs$peak_table      -- path to PeakTable CSV
#   inputs$sample_metadata -- path to SampleMetadata CSV
#   params$tracer_formula  -- tracer atom, e.g. "C13"
#   params$resolution      -- mass spec resolution
# and must return:
#   list(mid_table = "/absolute/path/to/output.csv")

run_accucor <- function(inputs, params) {
  if (!requireNamespace("accucor", quietly = TRUE)) {
    stop("AccuCor is not installed. Run install.packages('accucor').")
  }

  peak_df <- utils::read.csv(inputs$peak_table, check.names = FALSE)
  meta_df <- utils::read.csv(inputs$sample_metadata, check.names = FALSE)
  invisible(meta_df)

  tracer <- if (!is.null(params$tracer_formula)) params$tracer_formula else "C13"
  resolution <- if (!is.null(params$resolution)) params$resolution else 120000

  corrected <- accucor::natural_abundance_correction(
    peak_df,
    tracer = tracer,
    resolution = resolution
  )

  out_path <- tempfile(fileext = ".csv")
  utils::write.csv(corrected$Normalized, out_path, row.names = FALSE)
  list(mid_table = out_path)
}
