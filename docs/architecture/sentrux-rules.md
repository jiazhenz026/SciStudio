# Sentrux Architecture Rules

SciStudio uses Sentrux as a lightweight architecture sensor for dependency
health, layering, and boundary checks. The executable rule file lives at
`.sentrux/rules.toml`.

## Rule Intent

The initial ruleset is deliberately conservative. It protects the project
boundaries that matter most while avoiding a sudden failure on known baseline
debt:

- `core` owns primitive data, storage, metadata, lineage, and versioning
  contracts.
- `runtime` owns workflow definitions, execution, and block contracts.
- `extensions` owns plugin packages outside the core package.
- `interfaces` owns API, CLI, AI orchestration, and provisioning entrypoints.
- `frontend` owns the React user interface.

Imports should flow from outer entrypoints toward the stable core. The
executable `order` values in `.sentrux/rules.toml` therefore place outer
surfaces first and the core last, matching the direction enforced by the
current Sentrux MCP check on this repository. The explicit boundary rules
reinforce this by preventing core and engine code from importing API, CLI, AI,
or block implementation surfaces where that would collapse ownership
boundaries.

## Baseline Constraints

The current baseline keeps `max_cycles = 5` and `max_cc = 75`, matching the
observed Sentrux scan before introducing the ruleset. This makes the rule file
useful immediately: new changes should not worsen the cycle count or exceed
the current complexity ceiling, while future work can ratchet both numbers
downward.

`no_god_files` is initially disabled because several existing registry,
scheduler, and API runtime modules are large historical files. Turn it on only
after those files are split under issue-tracked refactors.

## Tightening Path

Future architecture cleanup should tighten these constraints in small,
traceable steps:

1. Reduce `max_cycles` toward `0`.
2. Reduce `max_cc` below the current baseline as complex functions are split.
3. Enable `no_god_files = true` after large historical modules are split.
4. Add more package-specific boundaries once plugin ownership settles.

Each tightening step should go through the normal issue, change plan, branch,
test, documentation, changelog, and PR workflow.
