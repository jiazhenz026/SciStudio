# Running

There are exactly two ways to execute:

- **Run** executes the whole graph.
- **Run from here** restarts from one block, reusing the latest results of
  everything upstream — the restart control on a node is this.

There is deliberately no third button that "re-runs the past". Going back is
**two steps**: Restore puts that version of your project back (the History
card tells that story), and then **you** press Run. You see what came back
before anything executes, and the button you press is the same Run you
already trust — not a second door with different rules.
