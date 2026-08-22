# Restore

You used Restore in level 1, when we broke your block. Four facts worth
keeping:

- It restores the run's **whole project tree** — workflow, block code,
  scripts — not just the workflow file. "I broke my block" is exactly the
  case it exists for.
- **It does not run anything. You press Run.** First see what came back,
  then decide.
- Before restoring it **checks two things** — are your input files still the
  ones that run used, and has the environment drifted since. Both are
  warnings; neither blocks you.
- **One thing it cannot do, and says so**: git only holds your project
  folder. SciStudio's own version, your installed packages, and Python
  itself are outside it and do not come back. And on a version that no run
  produced, it says it **cannot check** — never "all clear".
