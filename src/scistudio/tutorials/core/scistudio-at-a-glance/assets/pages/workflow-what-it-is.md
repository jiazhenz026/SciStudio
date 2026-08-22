# Workflow

A workflow is the graph you have been building since level 1: blocks joined
by wires, data flowing from left to right.

The graph is the **recipe, not the results**. It lives as a plain file in your
project, which is what lets History version it, branches vary it, and Restore
bring it back.

Pressing **Run** walks the graph in dependency order. Every block that can run,
runs; what each one produced is there to inspect the moment it finishes.
