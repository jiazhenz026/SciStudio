"""Embedded render-harness sources for preview-side plot jobs (ADR-048 SPEC 2).

The harness is the *outer* program the plot subprocess runs. It builds the
``context`` object (FR-014..FR-018), loads the bound collection from the
``inputs.json`` the runtime wrote, imports the user's render script, calls
``render(collection, context)``, and prints a single JSON result line on stdout
that the runtime parses.

These are stored as string templates rather than real modules so the runtime can
write them next to the user script inside the confined working directory — the
subprocess never imports SciStudio, only stdlib + (optionally) pandas/matplotlib
from the project environment.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Python harness.
# ---------------------------------------------------------------------------
#
# Contract with the runtime:
#   argv: python _plot_harness.py <script_name> <entrypoint> <inputs_json> <out_dir> <max_rows> <allowed_csv>
#   stdout: exactly one JSON line  {"ok": true, "artifacts": ["figure.svg", ...]}
#                                  {"ok": false, "error": "<sanitized message>"}
#
# The harness writes artifacts into <out_dir> (the confined working dir). The
# runtime then promotes the chosen artifact to the preview cache as current.*.

PYTHON_HARNESS = r'''"""Auto-generated plot harness (ADR-048). Do not edit; regenerated each run."""
import importlib.util
import json
import sys
import traceback
from pathlib import Path


def _load_render(script_name, entrypoint):
    spec = importlib.util.spec_from_file_location("scistudio_plot_render", script_name)
    if spec is None or spec.loader is None:
        raise ImportError("could not load render script: " + script_name)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    fn = getattr(module, entrypoint, None)
    if fn is None or not callable(fn):
        raise AttributeError("render script has no callable '" + entrypoint + "'")
    return fn


class _Collection:
    """Bounded view over the input data refs the runtime resolved."""

    def __init__(self, refs):
        self._refs = list(refs)

    @property
    def refs(self):
        return list(self._refs)

    def __len__(self):
        return len(self._refs)

    def __iter__(self):
        return iter(self._refs)


class _Context:
    def __init__(self, out_dir, max_rows, allowed_formats):
        self._out_dir = Path(out_dir)
        self._max_rows = int(max_rows)
        self._allowed = set(allowed_formats)
        self._saved = []
        import matplotlib

        matplotlib.use("Agg")
        import matplotlib.pyplot as plt

        self.plt = plt

    # --- data access (FR-017) ------------------------------------------
    def items(self, collection, max_items=None):
        refs = collection.refs if isinstance(collection, _Collection) else list(collection)
        if max_items is not None:
            refs = refs[: int(max_items)]
        return refs

    def to_dataframe(self, collection, max_rows=None):
        import pandas as pd

        cap = int(max_rows) if max_rows is not None else self._max_rows
        cap = min(cap, self._max_rows)
        refs = collection.refs if isinstance(collection, _Collection) else list(collection)
        frames = []
        remaining = cap
        for ref in refs:
            if remaining <= 0:
                break
            path = ref.get("path") if isinstance(ref, dict) else None
            if not path:
                continue
            suffix = Path(path).suffix.lower()
            if suffix in (".parquet", ".pq"):
                df = pd.read_parquet(path)
                df = df.head(remaining)
            elif suffix in (".csv", ".tsv", ".txt"):
                sep = "\t" if suffix == ".tsv" else ","
                df = pd.read_csv(path, sep=sep, nrows=remaining)
            elif suffix in (".json",):
                df = pd.read_json(path)
                df = df.head(remaining)
            else:
                continue
            frames.append(df)
            remaining -= len(df)
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True).head(cap)

    # --- saving (FR-018) -----------------------------------------------
    def _check_format(self, filename):
        ext = Path(filename).suffix.lower().lstrip(".")
        if ext == "jpg":
            ext = "jpeg"
        if ext not in {"svg", "pdf", "png", "jpeg"}:
            raise ValueError("unsupported output format: ." + ext)
        if self._allowed and ext not in self._allowed:
            raise ValueError("format ." + ext + " not in manifest allowed_formats")
        return ext

    def save_figure(self, fig, filename):
        ext = self._check_format(filename)
        out = self._out_dir / Path(filename).name
        fig.savefig(out, format=ext if ext != "jpeg" else "jpg", bbox_inches="tight")
        self.plt.close(fig)
        self._saved.append(out.name)
        return str(out)

    # Alias so Python scripts can use the same name as R's save_plot.
    def save_plot(self, fig, filename):
        return self.save_figure(fig, filename)

    @property
    def saved(self):
        return list(self._saved)


def main():
    script_name = sys.argv[1]
    entrypoint = sys.argv[2]
    inputs_json = sys.argv[3]
    out_dir = sys.argv[4]
    max_rows = sys.argv[5]
    allowed = [s for s in sys.argv[6].split(",") if s]
    try:
        refs = json.loads(Path(inputs_json).read_text(encoding="utf-8"))
        collection = _Collection(refs)
        context = _Context(out_dir, max_rows, allowed)
        render = _load_render(script_name, entrypoint)
        render(collection, context)
        artifacts = context.saved
        if not artifacts:
            # Scan the out dir for any produced image as a fallback.
            for child in sorted(Path(out_dir).iterdir()):
                if child.suffix.lower().lstrip(".") in {"svg", "pdf", "png", "jpeg", "jpg"}:
                    artifacts.append(child.name)
        print(json.dumps({"ok": True, "artifacts": artifacts}))
    except Exception as exc:  # noqa: BLE001 - sanitized below
        tb = traceback.format_exc(limit=4)
        print(json.dumps({"ok": False, "error": str(exc), "trace": tb}))
        sys.exit(1)


if __name__ == "__main__":
    main()
'''


# ---------------------------------------------------------------------------
# R harness.
# ---------------------------------------------------------------------------
#
# argv passed to Rscript: _plot_harness.R <script.R> <entrypoint> <inputs.json>
#                         <out_dir> <max_rows> <allowed_csv>
# stdout: one JSON line, same contract as the Python harness.

R_HARNESS = r"""# Auto-generated plot harness (ADR-048). Do not edit; regenerated each run.
args <- commandArgs(trailingOnly = TRUE)
script_name <- args[[1]]
entrypoint  <- args[[2]]
inputs_json <- args[[3]]
out_dir     <- args[[4]]
max_rows    <- as.integer(args[[5]])
allowed     <- strsplit(args[[6]], ",")[[1]]

emit <- function(obj) {
  cat(jsonlite::toJSON(obj, auto_unbox = TRUE), "\n", sep = "")
}

result <- tryCatch({
  refs <- jsonlite::fromJSON(inputs_json, simplifyVector = FALSE)
  saved <- character(0)

  check_format <- function(filename) {
    ext <- tolower(tools::file_ext(filename))
    if (ext == "jpg") ext <- "jpeg"
    if (!(ext %in% c("svg", "pdf", "png", "jpeg"))) stop(paste0("unsupported output format: .", ext))
    if (length(allowed) > 0 && !(ext %in% allowed)) stop(paste0("format .", ext, " not in allowed_formats"))
    ext
  }

  context <- list(
    to_dataframe = function(collection, max_rows = NULL) {
      cap <- if (is.null(max_rows)) max_rows else min(as.integer(max_rows), max_rows)
      cap <- if (is.null(cap)) get("max_rows", envir = globalenv()) else cap
      frames <- list()
      for (ref in refs) {
        path <- ref$path
        if (is.null(path)) next
        ext <- tolower(tools::file_ext(path))
        if (ext %in% c("csv", "txt")) {
          frames[[length(frames) + 1]] <- utils::read.csv(path, nrows = cap)
        } else if (ext == "tsv") {
          frames[[length(frames) + 1]] <- utils::read.delim(path, nrows = cap)
        }
      }
      if (length(frames) == 0) return(data.frame())
      df <- do.call(rbind, frames)
      utils::head(df, cap)
    },
    save_plot = function(plot, filename) {
      ext <- check_format(filename)
      out <- file.path(out_dir, basename(filename))
      if (requireNamespace("ggplot2", quietly = TRUE) && inherits(plot, "ggplot")) {
        ggplot2::ggsave(out, plot = plot, device = if (ext == "jpeg") "jpeg" else ext)
      } else {
        dev_fn <- switch(ext, svg = grDevices::svg, pdf = grDevices::pdf,
                         png = grDevices::png, jpeg = grDevices::jpeg)
        dev_fn(out)
        print(plot)
        grDevices::dev.off()
      }
      saved <<- c(saved, basename(out))
      out
    }
  )
  context$save_figure <- context$save_plot

  source(script_name, local = TRUE)
  render_fn <- get(entrypoint)
  render_fn(refs, context)
  list(ok = TRUE, artifacts = saved)
}, error = function(e) {
  list(ok = FALSE, error = conditionMessage(e))
})

emit(result)
if (isFALSE(result$ok)) quit(status = 1)
"""


__all__ = ["PYTHON_HARNESS", "R_HARNESS"]
