# AppBlock example — open an image in Fiji

`OpenInFiji` ([open_in_fiji.py](open_in_fiji.py)) hands an image file to
**Fiji (ImageJ)** and waits while you work in its GUI. No macro, no scripting:
the block declares the command and the ports, and the `AppBlock` base class
runs the whole exchange for you.

## You declare, the base class runs

The striking thing about `AppBlock` is how little you write. You override a few
class attributes and **do not** write `run()`:

| You set | What it does |
|---|---|
| `app_command` | The program to launch (usually set per workflow in the parameter panel; the config field is a file browser) |
| `input_ports` | What data the block accepts |
| `output_ports` | What it returns |
| `output_patterns` | Glob(s) for the files the watcher waits for (`["*.tif", "*.tiff", "*.zip", "*.roi"]`) |

The inherited `run()` then does all of this for you:

1. **Writes inputs** into an exchange folder: `<exchange>/inputs/`.
2. **Launches the app**, after validating the command (no shell injection).
3. **Watches** `<exchange>/outputs/` for files matching `output_patterns`,
   waiting until they stop changing (so half-written files are never read).
4. **Collects** those files back into your output ports.

## The one customization

A GUI Fiji opens *files*, not folders, so the block overrides
`prepare_launch` to hand it the staged image paths directly — without this,
Fiji would open with no image. That hook is also where a *config-driven* tool
would generate its parameter file and return a custom command line; the
default (returning `None`) passes the exchange folder, which suits apps that
read the folder themselves. (The imaging package's built-in Fiji block follows
this same shape.)

## How a run goes

1. The run reaches the block, which stages the `image` input into the exchange
   folder and opens Fiji with it.
2. While Fiji is open, the block reports **paused, waiting on the app** — the
   rest of the workflow knows it is blocked on you.
3. Do the work by hand; **save the result into the outputs folder** (or into
   the directory chosen with the **Save Outputs At** parameter). The block
   packs every file matching `output_patterns` onto the `result` port.
4. Close Fiji. If you closed it without saving anything, the step is recorded
   as **cancelled**, not failed (`BlockCancelledByAppError`).

## Why `Artifact` ports here

This example uses `Artifact` (an opaque file) for both ports because Fiji
reads and writes **TIFF** natively, so passing the image file straight through
is the simplest, most honest thing. If your input is instead an `Array` (a
SciStudio image), the bridge serialises it to the exchange folder as a NumPy
`.npy` file — fine for an app that reads `.npy`, but Fiji would need a `.npy`
reader plugin. For Fiji, keep the data as image files (`Artifact`).

## What to look up

`AppBlock`, `FileExchangeBridge`, `prepare_launch`, `validate_app_command`,
and `BlockCancelledByAppError` live in `scistudio.blocks.app` — see the API
reference for the full contract.
