# AppBlock example — run a Fiji macro

`FijiMacro` ([block.py](block.py)) sends an image to **Fiji (ImageJ)**, runs the
[gaussian_blur.ijm](gaussian_blur.ijm) macro on it, and reads the result back.
`AppBlock` turns any file-based external tool into a workflow step — headless
(as here) or interactive, where the user edits the data in the app's GUI and the
block waits for them to finish.

## You declare, the base class runs

The striking thing about `AppBlock` is how little you write. You override a few
class attributes and **do not** write `run()`:

| You set | What it does |
|---|---|
| `app_command` | The program to launch (a list of command parts) |
| `input_ports` | What data the block accepts |
| `output_ports` | What it returns |
| `output_patterns` | Glob(s) for the files the app will produce (`["*.tif"]`) |

The inherited `run()` then does all of this for you:

1. **Writes inputs** into an exchange folder: `<exchange>/inputs/`.
2. **Launches the app**, appending the exchange-folder path as the final
   command argument and validating the command first (no shell injection).
3. **Watches** `<exchange>/outputs/` for files matching `output_patterns`,
   waiting until they stop changing (so half-written files are never read).
4. **Collects** those files back into your output ports.

## The data flow, concretely

```
<exchange>/
  inputs/      <- your "image" input lands here
  outputs/     <- the macro writes here; SciStudio watches for *.tif
```

The macro learns the exchange path from `getArgument()` and reads/writes the two
sub-folders — see [gaussian_blur.ijm](gaussian_blur.ijm). That contract (inputs
in, outputs out, exchange path as the last argument) is the same for any app;
only the macro/script changes.

## Why `Artifact` ports here

This example uses `Artifact` (an opaque file) for both ports because Fiji reads
and writes **TIFF** natively, so passing the image file straight through is the
simplest, most honest thing. If your input is instead an `Array` (a SciStudio
image), the bridge serialises it to the exchange folder as a NumPy `.npy` file —
fine for an app that reads `.npy`, but Fiji would need a `.npy` reader plugin.
For Fiji, keep the data as image files (`Artifact`).

## Interactive use

Drop `--headless` from `app_command` and Fiji opens its GUI. The user does the
work by hand and saves the result into `outputs/`; the block waits. If the user
closes the app without producing output, the base `run()` raises
`BlockCancelledByAppError` and the run is marked cancelled rather than failed.

## What to look up

`AppBlock`, `FileExchangeBridge`, `FileWatcher`, `validate_app_command`, and the
two exceptions live in `scistudio.blocks.app` — see the API reference for the
full contract.
