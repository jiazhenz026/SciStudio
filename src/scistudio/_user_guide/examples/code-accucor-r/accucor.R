# AccuCor natural-isotope correction — a CodeBlock R script.
#
# SciStudio runs this script and exchanges data through folders it sets up.
# It tells the script where they are through environment variables:
#
#   SCISTUDIO_INPUTS_DIR   each input port has a sub-folder:  inputs/<port>/
#   SCISTUDIO_OUTPUTS_DIR  write each output port here:       outputs/<port>/
#
# This block declares one input port "peaks" (a DataFrame, .csv) and one output
# port "corrected" (a DataFrame, .csv). See README.md for the port config.

library(readr)
library(accucor)   # CRAN: natural-abundance isotope correction for LC-MS

inputs  <- Sys.getenv("SCISTUDIO_INPUTS_DIR")
outputs <- Sys.getenv("SCISTUDIO_OUTPUTS_DIR")

# --- read the input table -------------------------------------------------
# SciStudio wrote the upstream DataFrame into inputs/peaks/ as a .csv. Take the
# first file in that folder so the script does not depend on its exact name.
peaks_dir <- file.path(inputs, "peaks")
peaks_csv <- list.files(peaks_dir, pattern = "\\.csv$", full.names = TRUE)[1]
peaks <- read_csv(peaks_csv, show_col_types = FALSE)

# --- run the correction ---------------------------------------------------
# AccuCor removes the natural abundance of heavy isotopes (e.g. 13C at ~1.1%)
# from labelled-tracer peak intensities, yielding a corrected MID table
# (mass-isotopomer distribution). Adjust the resolution to your instrument.
result <- natural_abundance_correction(
  data       = peaks,
  resolution = 140000
)

# --- write the output table ----------------------------------------------
out_dir <- file.path(outputs, "corrected")
dir.create(out_dir, showWarnings = FALSE, recursive = TRUE)
write_csv(result$Corrected, file.path(out_dir, "mid_table.csv"))
