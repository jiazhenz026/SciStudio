"""Embedded render-harness sources for preview-side plot jobs (ADR-048).

The harness is the outer program the plot subprocess runs. It loads the
runtime-written input envelope, builds a context-free plot ``collection`` user
object, imports the user's render script, calls ``render(collection)``, and
prints a single JSON result line on stdout for the runtime to parse.

These are stored as string templates rather than importable SciStudio modules so
the subprocess only depends on the project environment's ordinary Python/R
scientific packages.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Python harness.
# ---------------------------------------------------------------------------
#
# Contract with the runtime:
#   argv: python _plot_harness.py <script_name> <entrypoint> <inputs_json>
#         <out_dir> <preferred_format> <allowed_csv> <max_input_bytes>
#   stdout: exactly one JSON line  {"ok": true, "artifacts": ["figure.svg", ...]}
#                                  {"ok": false, "error": "<message>"}

PYTHON_HARNESS = r'''"""Auto-generated plot harness (ADR-048). Do not edit; regenerated each run."""
import importlib.util
import json
import math
import sys
import traceback
from pathlib import Path
from types import MappingProxyType


SUPPORTED_TYPES = {"Array", "DataFrame", "Series", "Text", "Artifact", "CompositeData"}


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


def _normalise_ext(value):
    ext = Path(str(value)).suffix.lower().lstrip(".")
    if ext == "jpg":
        return "jpeg"
    return ext


def _check_allowed(path, allowed):
    ext = _normalise_ext(path)
    if ext not in {"svg", "pdf", "png", "jpeg"}:
        raise ValueError("unsupported output format: ." + ext)
    if allowed and ext not in allowed:
        raise ValueError("format ." + ext + " not in manifest allowed_formats")
    return ext


def _dtype_size(dtype_value):
    if dtype_value is None:
        return None
    try:
        import numpy as np

        return int(np.dtype(dtype_value).itemsize)
    except Exception:
        return None


def _shape_size(shape_value):
    if not isinstance(shape_value, (list, tuple)):
        return None
    total = 1
    try:
        for raw in shape_value:
            total *= int(raw)
    except Exception:
        return None
    return max(0, total)


def _metadata_estimated_nbytes(ref):
    md = ref.get("metadata") if isinstance(ref, dict) else None
    if not isinstance(md, dict):
        return None
    shape = md.get("shape")
    if shape is None:
        shape = md.get("array_shape")
    dtype = md.get("dtype")
    if dtype is None:
        dtype = md.get("array_dtype")
    count = _shape_size(shape)
    itemsize = _dtype_size(dtype)
    if count is None or itemsize is None:
        return None
    return count * itemsize


def _directory_size(path):
    total = 0
    for child in Path(path).rglob("*"):
        if child.is_file():
            total += child.stat().st_size
    return total


def _guard_nbytes(nbytes, limit, label):
    if nbytes is None:
        return
    if int(nbytes) > int(limit):
        raise MemoryError(
            label + " would materialize " + str(int(nbytes)) + " bytes, "
            "exceeding the plot input memory cap of " + str(int(limit)) + " bytes. "
            "Use an explicit storage-aware reader for large plot inputs."
        )


def _guard_file_or_dir(path, limit, label):
    p = Path(path)
    if p.is_file():
        _guard_nbytes(p.stat().st_size, limit, label)
    elif p.is_dir():
        _guard_nbytes(_directory_size(p), limit, label)


def _read_array(ref, limit):
    raw_path = ref.get("_path")
    if not raw_path:
        raise ValueError("Array item has no readable storage path")
    path = Path(raw_path)
    _guard_nbytes(_metadata_estimated_nbytes(ref), limit, "Array item")
    suffix = path.suffix.lower()
    backend = str(ref.get("_backend") or "").lower()
    fmt = str(ref.get("_format") or "").lower()

    import numpy as np

    if backend == "zarr" or fmt == "zarr" or suffix == ".zarr" or path.is_dir():
        import zarr

        node = zarr.open(str(path), mode="r")
        handle = node if isinstance(node, zarr.Array) else node.get("data")
        if handle is None:
            raise ValueError("Zarr Array item has no top-level array or 'data' dataset")
        shape = getattr(handle, "shape", None)
        dtype = getattr(handle, "dtype", None)
        count = _shape_size(shape)
        itemsize = _dtype_size(dtype)
        if count is not None and itemsize is not None:
            _guard_nbytes(count * itemsize, limit, "Array item")
        return np.asarray(handle[...])

    if suffix == ".npy":
        arr = np.load(path, mmap_mode="r")
        _guard_nbytes(arr.size * arr.dtype.itemsize, limit, "Array item")
        return np.asarray(arr)

    if suffix == ".npz":
        _guard_file_or_dir(path, limit, "Array item")
        loaded = np.load(path)
        first_key = loaded.files[0] if loaded.files else None
        if first_key is None:
            raise ValueError("NPZ Array item contains no arrays")
        return np.asarray(loaded[first_key])

    if suffix in {".tif", ".tiff"}:
        _guard_file_or_dir(path, limit, "Array item")
        import tifffile

        return np.asarray(tifffile.imread(str(path)))

    if suffix in {".png", ".jpeg", ".jpg"}:
        _guard_file_or_dir(path, limit, "Array item")
        from PIL import Image

        with Image.open(path) as img:
            return np.asarray(img)

    if suffix in {".csv", ".tsv", ".txt"}:
        _guard_file_or_dir(path, limit, "Array item")
        delimiter = "\t" if suffix == ".tsv" else ","
        return np.loadtxt(path, delimiter=delimiter)

    raise ValueError("unsupported Array storage for plot open(): " + path.name)


def _read_dataframe(ref, limit):
    raw_path = ref.get("_path")
    if not raw_path:
        raise ValueError("DataFrame item has no readable storage path")
    path = Path(raw_path)
    _guard_nbytes(_metadata_estimated_nbytes(ref), limit, "DataFrame item")
    _guard_file_or_dir(path, limit, "DataFrame item")
    suffix = path.suffix.lower()

    import pandas as pd

    if suffix in {".parquet", ".pq"}:
        return pd.read_parquet(path)
    if suffix in {".csv", ".txt"}:
        return pd.read_csv(path)
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t")
    if suffix == ".json":
        return pd.read_json(path)
    raise ValueError("unsupported DataFrame storage for plot open(): " + path.name)


def _read_series(ref, limit):
    value = _read_dataframe(ref, limit)
    if hasattr(value, "iloc"):
        if len(value.columns) == 0:
            raise ValueError("Series item table has no columns")
        return value.iloc[:, 0]
    raise ValueError("unsupported Series storage for plot open()")


def _read_text(ref, limit):
    raw_path = ref.get("_path")
    if not raw_path:
        raise ValueError("Text item has no readable storage path")
    path = Path(raw_path)
    _guard_file_or_dir(path, limit, "Text item")
    return path.read_text(encoding="utf-8")


def _read_artifact(ref, limit):
    raw_path = ref.get("_path")
    if not raw_path:
        raise ValueError("Artifact item has no readable storage path")
    path = Path(raw_path)
    return path


def _read_composite(ref, limit):
    md = ref.get("metadata")
    if not isinstance(md, dict):
        return {}
    slots = md.get("slots")
    if not isinstance(slots, dict):
        return {}
    result = {}
    for name, slot_ref in slots.items():
        if isinstance(slot_ref, dict):
            result[str(name)] = _PlotItem(slot_ref, limit).open()
    return result


def _open_ref(ref, limit):
    typ = ref.get("type") or "DataObject"
    if typ == "Array":
        return _read_array(ref, limit)
    if typ == "DataFrame":
        return _read_dataframe(ref, limit)
    if typ == "Series":
        return _read_series(ref, limit)
    if typ == "Text":
        return _read_text(ref, limit)
    if typ == "Artifact":
        return _read_artifact(ref, limit)
    if typ == "CompositeData":
        return _read_composite(ref, limit)
    raise ValueError("unsupported plot collection item type: " + str(typ))


def _public_metadata(ref):
    md = ref.get("metadata") if isinstance(ref, dict) else {}
    if not isinstance(md, dict):
        return {}
    return {
        str(key): value
        for key, value in md.items()
        if key not in {"backend", "format", "path", "storage_ref", "storage", "type_chain", "item_type", "slots"}
    }


class _PlotItem:
    def __init__(self, ref, max_input_bytes):
        self._ref = dict(ref)
        self._max_input_bytes = int(max_input_bytes)
        self.type = str(ref.get("type") or "DataObject")
        self.metadata = MappingProxyType(_public_metadata(ref))

    def open(self):
        return _open_ref(self._ref, self._max_input_bytes)


class _PlotItems:
    def __init__(self, refs, max_input_bytes):
        self._items = [_PlotItem(ref, max_input_bytes) for ref in refs]

    def __len__(self):
        return len(self._items)

    def __iter__(self):
        return iter(self._items)

    def __getitem__(self, index):
        return self._items[index]

    def open(self, max_items=None):
        items = self._items
        if max_items is not None:
            items = items[: int(max_items)]
        return [item.open() for item in items]

    def open_one(self):
        if not self._items:
            raise IndexError("collection is empty; cannot open_one()")
        return self._items[0].open()


class _PlotCollection:
    def __init__(self, envelope, max_input_bytes):
        collection = envelope.get("collection") if isinstance(envelope, dict) else None
        if not isinstance(collection, dict):
            collection = {"types": [], "items": []}
        refs = collection.get("items")
        if not isinstance(refs, list):
            refs = []
        types = collection.get("types")
        if not isinstance(types, list):
            types = []
        self.types = tuple(str(t) for t in types)
        self.items = _PlotItems(refs, max_input_bytes)


def _artifact_name(index, preferred):
    suffix = "jpg" if preferred == "jpeg" else preferred
    return "figure." + suffix if index == 0 else "figure_" + str(index) + "." + suffix


def _save_matplotlib_figure(fig, out_dir, preferred, allowed, index):
    _check_allowed("figure." + preferred, allowed)
    out = Path(out_dir) / _artifact_name(index, preferred)
    fmt = "jpg" if preferred == "jpeg" else preferred
    fig.savefig(out, format=fmt, bbox_inches="tight")
    try:
        import matplotlib.pyplot as plt

        plt.close(fig)
    except Exception:
        pass
    return out.name


def _collect_path(value, out_dir, allowed):
    raw = Path(value)
    candidate = raw if raw.is_absolute() else (Path(out_dir) / raw)
    resolved = candidate.resolve()
    root = Path(out_dir).resolve()
    try:
        resolved.relative_to(root)
    except ValueError as exc:
        raise PermissionError("returned artifact path escapes the plot working directory") from exc
    if not resolved.is_file():
        raise FileNotFoundError("returned artifact path does not exist: " + str(raw))
    _check_allowed(resolved, allowed)
    return resolved.name


def _collect_artifacts(value, out_dir, preferred, allowed):
    if value is None:
        raise ValueError("render(collection) must return a figure, artifact path, or list of artifacts")
    values = list(value) if isinstance(value, (list, tuple)) else [value]
    artifacts = []
    fig_index = 0
    for one in values:
        if one is None:
            raise ValueError("render(collection) returned an unsupported None artifact")
        if isinstance(one, (str, Path)):
            artifacts.append(_collect_path(one, out_dir, allowed))
            continue
        if hasattr(one, "savefig"):
            artifacts.append(_save_matplotlib_figure(one, out_dir, preferred, allowed, fig_index))
            fig_index += 1
            continue
        raise TypeError("unsupported render return value: " + type(one).__name__)
    return artifacts


def main():
    script_name = sys.argv[1]
    entrypoint = sys.argv[2]
    inputs_json = sys.argv[3]
    out_dir = sys.argv[4]
    preferred = sys.argv[5]
    allowed = [s for s in sys.argv[6].split(",") if s]
    max_input_bytes = int(sys.argv[7])
    try:
        import matplotlib

        matplotlib.use("Agg")
        envelope = json.loads(Path(inputs_json).read_text(encoding="utf-8"))
        collection = _PlotCollection(envelope, max_input_bytes)
        render = _load_render(script_name, entrypoint)
        result = render(collection)
        artifacts = _collect_artifacts(result, out_dir, preferred, allowed)
        print(json.dumps({"ok": True, "artifacts": artifacts}))
    except Exception as exc:  # noqa: BLE001 - sanitized by parent runtime
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
#                         <out_dir> <preferred_format> <allowed_csv>
#                         <max_input_bytes>
# stdout: one JSON line, same contract as the Python harness.

R_HARNESS = r"""# Auto-generated plot harness (ADR-048). Do not edit; regenerated each run.
args <- commandArgs(trailingOnly = TRUE)
script_name <- args[[1]]
entrypoint  <- args[[2]]
inputs_json <- args[[3]]
out_dir     <- args[[4]]
preferred   <- args[[5]]
allowed     <- strsplit(args[[6]], ",")[[1]]
allowed     <- allowed[nzchar(allowed)]
max_input_bytes <- as.numeric(args[[7]])

emit <- function(obj) {
  cat(jsonlite::toJSON(obj, auto_unbox = TRUE), "\n", sep = "")
}

check_format <- function(filename) {
  ext <- tolower(tools::file_ext(filename))
  if (ext == "jpg") ext <- "jpeg"
  if (!(ext %in% c("svg", "pdf", "png", "jpeg"))) {
    stop(paste0("unsupported output format: .", ext))
  }
  if (length(allowed) > 0 && !(ext %in% allowed)) {
    stop(paste0("format .", ext, " not in manifest allowed_formats"))
  }
  ext
}

guard_bytes <- function(nbytes, label) {
  if (!is.na(nbytes) && nbytes > max_input_bytes) {
    stop(paste0(
      label, " would materialize ", nbytes,
      " bytes, exceeding the plot input memory cap of ",
      max_input_bytes, " bytes. Use an explicit storage-aware reader for large plot inputs."
    ))
  }
}

guard_path <- function(path, label) {
  if (file.exists(path) && !dir.exists(path)) {
    guard_bytes(file.info(path)$size, label)
  }
}

dtype_size <- function(dtype) {
  if (is.null(dtype)) return(NA_real_)
  dtype <- tolower(as.character(dtype))
  if (grepl("float64|double|int64|uint64", dtype)) return(8)
  if (grepl("float32|single|int32|uint32", dtype)) return(4)
  if (grepl("float16|int16|uint16", dtype)) return(2)
  if (grepl("bool|int8|uint8", dtype)) return(1)
  NA_real_
}

metadata_nbytes <- function(ref) {
  md <- ref$metadata
  if (is.null(md) || !is.list(md)) return(NA_real_)
  shape <- md$shape
  if (is.null(shape)) shape <- md$array_shape
  dtype <- md$dtype
  if (is.null(dtype)) dtype <- md$array_dtype
  if (is.null(shape)) return(NA_real_)
  count <- prod(as.numeric(unlist(shape)))
  itemsize <- dtype_size(dtype)
  if (is.na(count) || is.na(itemsize)) return(NA_real_)
  count * itemsize
}

guard_ref <- function(ref, label) {
  guard_bytes(metadata_nbytes(ref), label)
}

public_metadata <- function(ref) {
  md <- ref$metadata
  if (is.null(md) || !is.list(md)) return(list())
  md$backend <- NULL
  md$format <- NULL
  md$path <- NULL
  md$storage <- NULL
  md$storage_ref <- NULL
  md$type_chain <- NULL
  md$item_type <- NULL
  md$slots <- NULL
  md
}

read_dataframe <- function(ref) {
  path <- ref$`_path`
  if (is.null(path)) stop("DataFrame item has no readable storage path")
  guard_ref(ref, "DataFrame item")
  guard_path(path, "DataFrame item")
  ext <- tolower(tools::file_ext(path))
  if (ext %in% c("csv", "txt")) return(utils::read.csv(path))
  if (ext == "tsv") return(utils::read.delim(path))
  if (ext == "json") return(as.data.frame(jsonlite::fromJSON(path)))
  if (ext %in% c("parquet", "pq") && requireNamespace("arrow", quietly = TRUE)) {
    return(as.data.frame(arrow::read_parquet(path)))
  }
  stop(paste0("unsupported DataFrame storage for plot open(): ", basename(path)))
}

read_array <- function(ref) {
  path <- ref$`_path`
  if (is.null(path)) stop("Array item has no readable storage path")
  guard_ref(ref, "Array item")
  guard_path(path, "Array item")
  ext <- tolower(tools::file_ext(path))
  if (ext %in% c("csv", "txt")) return(as.matrix(utils::read.csv(path, header = FALSE)))
  if (ext == "tsv") return(as.matrix(utils::read.delim(path, header = FALSE)))
  if (ext == "json") return(as.array(jsonlite::fromJSON(path)))
  stop(paste0("unsupported Array storage for R plot open(): ", basename(path)))
}

read_series <- function(ref) {
  df <- read_dataframe(ref)
  if (ncol(df) < 1) stop("Series item table has no columns")
  df[[1]]
}

read_text <- function(ref) {
  path <- ref$`_path`
  if (is.null(path)) stop("Text item has no readable storage path")
  guard_ref(ref, "Text item")
  guard_path(path, "Text item")
  paste(readLines(path, warn = FALSE), collapse = "\n")
}

open_ref <- function(ref) {
  typ <- ref$type
  if (is.null(typ)) typ <- "DataObject"
  if (typ == "Array") return(read_array(ref))
  if (typ == "DataFrame") return(read_dataframe(ref))
  if (typ == "Series") return(read_series(ref))
  if (typ == "Text") return(read_text(ref))
  if (typ == "Artifact") return(ref$`_path`)
  if (typ == "CompositeData") {
    slots <- ref$metadata$slots
    if (is.null(slots) || !is.list(slots)) return(list())
    opened <- list()
    for (name in names(slots)) {
      opened[[name]] <- open_ref(slots[[name]])
    }
    return(opened)
  }
  stop(paste0("unsupported plot collection item type: ", typ))
}

make_item <- function(ref) {
  item <- new.env(parent = emptyenv())
  item$type <- if (is.null(ref$type)) "DataObject" else ref$type
  item$metadata <- public_metadata(ref)
  item$open <- function() open_ref(ref)
  item
}

make_items <- function(refs) {
  items <- new.env(parent = emptyenv())
  hidden <- lapply(refs, make_item)
  items$._items <- hidden
  items$open <- function(max_items = NULL) {
    selected <- hidden
    if (!is.null(max_items)) selected <- selected[seq_len(min(as.integer(max_items), length(hidden)))]
    lapply(selected, function(item) item$open())
  }
  items$open_one <- function() {
    if (length(hidden) == 0) stop("collection is empty; cannot open_one()")
    hidden[[1]]$open()
  }
  class(items) <- "PlotItems"
  items
}

length.PlotItems <- function(x) length(x$._items)
`[[.PlotItems` <- function(x, i) x$._items[[i]]

make_collection <- function(envelope) {
  raw_collection <- envelope$collection
  if (is.null(raw_collection)) raw_collection <- list(types = character(0), items = list())
  collection <- new.env(parent = emptyenv())
  collection$types <- unlist(raw_collection$types %||% character(0), use.names = FALSE)
  collection$items <- make_items(raw_collection$items %||% list())
  collection
}

`%||%` <- function(left, right) {
  if (is.null(left)) right else left
}

safe_artifact_path <- function(path) {
  candidate <- if (grepl("^([A-Za-z]:)?[\\\\/]", path)) path else file.path(out_dir, path)
  resolved <- normalizePath(candidate, mustWork = TRUE, winslash = "/", unset = NA)
  root <- normalizePath(out_dir, mustWork = TRUE, winslash = "/", unset = NA)
  if (is.na(resolved) || !startsWith(resolved, root)) {
    stop("returned artifact path escapes the plot working directory")
  }
  check_format(resolved)
  basename(resolved)
}

save_ggplot <- function(plot, index) {
  ext <- check_format(paste0("figure.", preferred))
  suffix <- if (preferred == "jpeg") "jpg" else preferred
  filename <- if (index == 0) paste0("figure.", suffix) else paste0("figure_", index, ".", suffix)
  out <- file.path(out_dir, filename)
  ggplot2::ggsave(out, plot = plot, device = if (ext == "jpeg") "jpeg" else ext)
  basename(out)
}

collect_returned <- function(value) {
  if (is.null(value)) return(character(0))
  values <- if (is.list(value) && !inherits(value, "ggplot")) value else list(value)
  out <- character(0)
  gg_index <- 0
  for (one in values) {
    if (is.character(one) && length(one) == 1) {
      out <- c(out, safe_artifact_path(one))
    } else if (requireNamespace("ggplot2", quietly = TRUE) && inherits(one, "ggplot")) {
      out <- c(out, save_ggplot(one, gg_index))
      gg_index <- gg_index + 1
    } else if (!is.null(one)) {
      stop(paste0("unsupported render return value: ", paste(class(one), collapse = "/")))
    }
  }
  out
}

device_filename <- function() {
  suffix <- if (preferred == "jpeg") "jpg" else preferred
  paste0("figure.", suffix)
}

open_device <- function(path) {
  ext <- check_format(path)
  if (ext == "svg") grDevices::svg(path)
  else if (ext == "pdf") grDevices::pdf(path)
  else if (ext == "png") grDevices::png(path)
  else grDevices::jpeg(path)
}

result <- tryCatch({
  envelope <- jsonlite::fromJSON(inputs_json, simplifyVector = FALSE)
  collection <- make_collection(envelope)
  source(script_name, local = TRUE)
  render_fn <- get(entrypoint)

  device_file <- file.path(out_dir, device_filename())
  open_device(device_file)
  before_pages <- grDevices::dev.cur()
  rendered <- render_fn(collection)
  grDevices::dev.off()

  artifacts <- collect_returned(rendered)
  if (length(artifacts) == 0 && file.exists(device_file) && file.info(device_file)$size > 0) {
    artifacts <- basename(device_file)
  }
  if (length(artifacts) == 0) stop("render(collection) produced no plot artifact")
  list(ok = TRUE, artifacts = artifacts)
}, error = function(e) {
  while (grDevices::dev.cur() > 1) {
    try(grDevices::dev.off(), silent = TRUE)
  }
  list(ok = FALSE, error = conditionMessage(e))
})

emit(result)
if (isFALSE(result$ok)) quit(status = 1)
"""


__all__ = ["PYTHON_HARNESS", "R_HARNESS"]
