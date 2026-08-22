# When a run fails

Three things to know, in the order you will need them:

- A failing block does not take the run down. Everything **downstream of it
  is skipped**; independent branches complete. The canvas marks the failure.
- The **Logs tab** carries the error itself.
- After the fix, **run from here** on the failed block — everything upstream
  is reused, and the run picks up where it stopped.
