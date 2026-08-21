# Tips

- **Ask the AI** to write a previewer — "show this type as X" is a good
  brief, and you review the result.
- **Interactivity has two layers.** A pure-Python previewer gets the core
  viewers' built-in interactions — slicing along axes for arrays, paging and
  sorting for tables. Interactions beyond that need a previewer that ships
  its own frontend assets — more to build, and rarely the place to start.
