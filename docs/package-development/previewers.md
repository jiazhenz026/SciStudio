# Writing a previewer

A previewer is what the user sees when they click a port carrying your type:
a spectrum plot, a dataset table, an image viewer. Core ships generic previews
(a table renders as a table); a package previewer gives **your** type a tailored
view. Previewers are optional — a type works without one — but they are where a
domain package feels finished.

We use the spectroscopy package's `Spectrum` previewer as the example.

## The shape of a previewer

A previewer has two halves that meet at a typed contract:

- **A backend provider** — a Python function that reads a *bounded* sample of the
  data and returns a `PreviewEnvelope` (the data the view needs, plus its kind).
- **A frontend view** — JavaScript/CSS assets the inspector loads to render that
  envelope (a plot, an interactive table, controls).

You declare both, plus routing metadata, in one `PreviewerSpec`. Everything you
need is in `scistudio.previewers.models` (the spec, envelope, and manifest types)
and `scistudio.previewers.data_access` (the bounded-read helpers) — the two
canonical previewer roots.

## Declare a `PreviewerSpec`

The package's `scistudio.previewers` entry point returns a list of specs:

```python
from scistudio.previewers.models import (
    FrontendManifest, OwnerKind, PreviewerSpec,
)

def get_previewers() -> list[PreviewerSpec]:
    return [
        PreviewerSpec(
            previewer_id="spectroscopy.spectrum.viewer",  # stable unique id
            owner_kind=OwnerKind.PACKAGE,
            owner_name="scistudio-blocks-spectroscopy",
            target_type="Spectrum",                       # which type this previews
            supports_collection=False,
            priority=100,                                 # higher wins ties
            capabilities=("plot", "navigate", "diagnostics", "export"),
            backend_provider=spectrum_provider,           # the function below
            frontend_manifest=_frontend_manifest("spectroscopy.spectrum.viewer"),
        ),
    ]
```

Key fields:

- **`target_type`** names the type, as a string, that this previewer renders.
  The preview router matches a port's type to the highest-`priority` previewer
  whose `target_type` it is.
- **`owner_kind` / `owner_name`** record that a package (not core) owns this, so
  the router can reason about provenance and overrides.
- **`capabilities`** advertise what the view can do (plot, table, filter,
  export…), which the inspector uses to offer the right controls.
- **`frontend_manifest`** points at the JS/CSS assets your package ships (under
  `previewers/assets/`).

## Write the backend provider

The provider turns a request into an envelope. The single most important rule:
**read bounded data, never the whole object.** Scientific data can be enormous; a
preview must stay cheap. You read through the `PreviewDataAccess` helpers on the
request, which serve a capped sample from the backend without materialising the
full object:

```python
def spectrum_provider(request) -> "PreviewEnvelope":
    ref = request  # resolve the data reference from the request
    # A Spectrum is a two-column table (lambda, intensity). Read it as true
    # (x, y) points through the bounded helper — respecting the page budget.
    sample = request.data_access.table_xy_points(
        ref, x_column="lambda", y_column="intensity",
    )
    return PreviewEnvelope(kind="SERIES", ...)   # the points + render hints
```

What this buys you:

- **`request.data_access`** is a `PreviewDataAccess` — its methods
  (`table_xy_points`, `slice`, `composite_slot_ref`, …) return only a bounded
  sample, so a 100 GB object previews as fast as a small one. Use these; do not
  call `to_memory()` in a previewer.
- **The envelope `kind`** lets the preview **degrade gracefully**. `Spectrum`
  returns `kind="SERIES"`, so if your package's viewer asset is unavailable, the
  inspector falls back to core's generic series renderer instead of failing.

## Ship the frontend assets

The `FrontendManifest` lists the JS/CSS the inspector loads to render the
envelope. Put the files under `previewers/assets/` in your package and reference
them from the manifest. The view receives the envelope your provider returned and
draws it — a line plot for a spectrum, with the navigate/export controls your
`capabilities` advertised.

The contract between provider and view is the envelope. Keep the provider doing
the *bounded reading and shaping*, and the view doing the *rendering*; that split
is what lets the same view work for any data size.

## Routing, priority, collections

- **Priority** breaks ties when more than one previewer targets a type — a
  package previewer at `priority=100` overrides a lower-priority generic one.
- **`supports_collection`** says whether the previewer handles a whole
  `Collection` on the port or a single item; set it to match what your view
  expects.

## Mark stability

Previewer specs and provider functions are public symbols too — mark them with
the `scistudio.stability` decorators against your package version, the same as
types and blocks. A previewer the user relies on is part of your contract.

## What to look up

`PreviewerSpec`, `FrontendManifest`, `OwnerKind`, the API-version constant, and
the preview-error types are in `scistudio.previewers.models`; the bounded-read
helpers are in `scistudio.previewers.data_access`. See both in the API reference
for exact fields and signatures.

## Next

[publishing.md](publishing.md) — package, version, and release it.
