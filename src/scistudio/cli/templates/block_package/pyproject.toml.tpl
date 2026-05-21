[project]
name = "{package_name}"
version = "0.1.0"
description = "{description}"
readme = "README.md"
license = {{text = "MIT"}}
requires-python = ">=3.11"
authors = [
    {{name = "{author}"}},
]
dependencies = [
    "scieasy>=0.1.0",
]

[project.optional-dependencies]
dev = [
    "pytest>=8.0",
    "ruff>=0.11",
]

[project.entry-points."scieasy.blocks"]
{entry_point_name} = "{module_name}:get_blocks"

[build-system]
requires = ["setuptools>=68.0"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
