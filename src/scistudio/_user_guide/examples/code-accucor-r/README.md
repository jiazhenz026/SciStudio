# CodeBlock example — run an R script (AccuCor)

[accucor.R](accucor.R) runs **AccuCor** natural-isotope correction on an LC-MS
peak table. `CodeBlock` is how you bring an existing **Python, R, or Julia**
script into a workflow without rewriting it as a Python block — ideal when the
science already lives in a language-specific package (here, the R `accucor`
package).

## How a CodeBlock works

Unlike the other base classes, you do **not** subclass anything. A `CodeBlock`
is a script plus a small **port configuration** that says what files go in and
out. SciStudio:

1. Creates an exchange folder with one sub-folder per port.
2. Writes each connected input into `inputs/<port>/` in the file format you
   declared.
3. Runs your script, telling it where the folders are via environment variables.
4. Reads each file your script left in `outputs/<port>/` back into a typed
   `DataObject`.

The script learns the folder locations from environment variables SciStudio
sets:

| Variable | Points to |
|---|---|
| `SCISTUDIO_INPUTS_DIR` | the `inputs/` folder (one sub-folder per input port) |
| `SCISTUDIO_OUTPUTS_DIR` | the `outputs/` folder (write one sub-folder per output port) |
| `SCISTUDIO_EXCHANGE_DIR` | the exchange root |
| `SCISTUDIO_SCRIPT_PATH` | this script's own path |

## The port configuration

This block declares one input and one output port. Conceptually:

| Port | Direction | Data type | Extension | Folder |
|---|---|---|---|---|
| `peaks` | input | `DataFrame` | `.csv` | `inputs/peaks/` |
| `corrected` | output | `DataFrame` | `.csv` | `outputs/corrected/` |

So the script reads its peak table from `inputs/peaks/*.csv` and writes the
corrected MID table to `outputs/corrected/mid_table.csv` — exactly what
[accucor.R](accucor.R) does. SciStudio then turns that CSV back into a
`DataFrame` on the `corrected` output port.

You set this configuration when you add the CodeBlock and point it at the script
(`script_path`), choosing the language by the script's extension (`.R`, `.Rmd`,
`.qmd` for R; `.py` for Python; and so on). The exact config model is
`CodeBlockConfig` / `PortFileConfig` in `scistudio.blocks.code` — see the API
reference.

## What AccuCor does

LC-MS isotope-tracing experiments measure metabolite peaks, but every peak
carries a background of *naturally* heavy isotopes (≈1.1% of carbon is ¹³C even
with no tracer). AccuCor subtracts that natural abundance, leaving the
tracer-derived **mass-isotopomer distribution (MID)** — the real signal that
downstream flux analysis needs.

## Why use a CodeBlock instead of a Python block

- The logic already exists in R/Julia and you do not want to port it.
- A domain package ships a validated script you want to reuse as-is.
- You are prototyping in a notebook-style language.

If the logic is small and Python-native, a `ProcessBlock` is simpler — keep
`CodeBlock` for genuinely cross-language work.
