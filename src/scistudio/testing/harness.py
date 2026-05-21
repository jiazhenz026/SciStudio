"""BlockTestHarness -- contract validation and smoke testing for blocks.

External block developers use this harness to verify their blocks satisfy
the SciStudio block contract (ADR-025, ADR-026) without manual setup.

Typical usage in a pytest test::

    from scistudio.testing import BlockTestHarness

    def test_my_block_contract():
        harness = BlockTestHarness(MyBlock)
        errors = harness.validate_block()
        assert not errors, errors

    def test_my_block_smoke(tmp_path):
        harness = BlockTestHarness(MyBlock, work_dir=tmp_path)
        result = harness.smoke_test(inputs={"input": collection})
        assert "output" in result
"""

from __future__ import annotations

import inspect
from pathlib import Path
from typing import Any


class BlockTestHarness:
    """Test helper for validating and smoke-testing SciStudio blocks.

    Parameters
    ----------
    block_class:
        A concrete subclass of :class:`~scistudio.blocks.base.block.Block`.
    work_dir:
        Optional working directory for smoke tests.  When ``None``, a
        temporary directory is used.
    """

    def __init__(self, block_class: type, work_dir: Path | None = None) -> None:
        self.block_class = block_class
        self.work_dir = work_dir

    # ------------------------------------------------------------------
    # Contract validation
    # ------------------------------------------------------------------

    def validate_block(self) -> list[str]:
        """Validate that *block_class* satisfies the block contract.

        Checks performed:

        1. Must be a subclass of :class:`Block`.
        2. Must not be abstract.
        3. Must define ``input_ports`` as a list of :class:`InputPort`.
        4. Must define ``output_ports`` as a list of :class:`OutputPort`.
        5. Must have a ``run()`` method (concrete, not the ABC stub).
        6. Must have a non-empty ``name`` string.

        Returns a list of human-readable error strings.  An empty list
        means the block passes all contract checks.
        """
        from scistudio.blocks.base.block import Block
        from scistudio.blocks.base.ports import InputPort, OutputPort

        errors: list[str] = []
        cls = self.block_class

        # 1. Must be a Block subclass.
        if not (isinstance(cls, type) and issubclass(cls, Block)):
            errors.append(
                f"{cls!r} is not a subclass of Block. Block classes must inherit from scistudio.blocks.base.Block."
            )
            # Remaining checks depend on Block inheritance; bail early.
            return errors

        # 2. Must not be abstract.
        if inspect.isabstract(cls):
            errors.append(
                f"{cls.__name__} is abstract (has unimplemented abstract methods). "
                "Blocks registered for execution must be concrete classes."
            )

        # 3. input_ports must be a list of InputPort.
        input_ports = getattr(cls, "input_ports", None)
        if input_ports is None:
            errors.append(
                f"{cls.__name__}.input_ports is not defined. Declare input_ports as a ClassVar[list[InputPort]]."
            )
        elif not isinstance(input_ports, list):
            errors.append(f"{cls.__name__}.input_ports must be a list, got {type(input_ports).__name__}.")
        else:
            for i, port in enumerate(input_ports):
                if not isinstance(port, InputPort):
                    errors.append(f"{cls.__name__}.input_ports[{i}] is {type(port).__name__}, expected InputPort.")

        # 4. output_ports must be a list of OutputPort.
        output_ports = getattr(cls, "output_ports", None)
        if output_ports is None:
            errors.append(
                f"{cls.__name__}.output_ports is not defined. Declare output_ports as a ClassVar[list[OutputPort]]."
            )
        elif not isinstance(output_ports, list):
            errors.append(f"{cls.__name__}.output_ports must be a list, got {type(output_ports).__name__}.")
        else:
            for i, port in enumerate(output_ports):
                if not isinstance(port, OutputPort):
                    errors.append(f"{cls.__name__}.output_ports[{i}] is {type(port).__name__}, expected OutputPort.")

        # 5. Must have a concrete run() method.
        run_method = getattr(cls, "run", None)
        if run_method is None:
            errors.append(f"{cls.__name__} does not have a run() method.")

        # 6. Must have a non-empty name.
        name = getattr(cls, "name", "")
        if not name or name == "Unnamed Block":
            errors.append(f"{cls.__name__}.name is not set. Provide a descriptive ClassVar[str] name.")

        return errors

    def validate_package_info(self, info: Any) -> list[str]:
        """Validate a :class:`PackageInfo` instance.

        Checks that *info* is a ``PackageInfo`` with a non-empty ``name``
        field.  The ``description``, ``author``, and ``version`` fields
        are checked to be strings (may be empty for ``description`` and
        ``author``; ``version`` must be non-empty).

        Returns a list of human-readable error strings.
        """
        from scistudio.blocks.base.package_info import PackageInfo

        errors: list[str] = []

        if not isinstance(info, PackageInfo):
            errors.append(f"Expected PackageInfo instance, got {type(info).__name__}.")
            return errors

        if not info.name or not isinstance(info.name, str):
            errors.append("PackageInfo.name must be a non-empty string.")

        if not isinstance(info.description, str):
            errors.append(f"PackageInfo.description must be a string, got {type(info.description).__name__}.")

        if not isinstance(info.author, str):
            errors.append(f"PackageInfo.author must be a string, got {type(info.author).__name__}.")

        if not info.version or not isinstance(info.version, str):
            errors.append("PackageInfo.version must be a non-empty string.")

        return errors

    def validate_entry_point_callable(self, callable_result: Any) -> list[str]:
        """Validate the return value of a ``scistudio.blocks`` entry-point callable.

        Per ADR-025, the callable must return either:

        * ``(PackageInfo, list[type[Block]])`` -- package metadata + blocks
        * ``list[type[Block]]`` -- plain block list (backward compatible)

        This method validates the structure and each block in the list.

        Returns a list of human-readable error strings.
        """
        from scistudio.blocks.base.block import Block
        from scistudio.blocks.base.package_info import PackageInfo

        errors: list[str] = []
        info: Any = None
        block_classes: list[type] = []

        # Parse the two accepted formats.
        if isinstance(callable_result, tuple):
            if len(callable_result) != 2:
                errors.append(
                    f"Entry-point callable returned a tuple of length "
                    f"{len(callable_result)}, expected 2 (PackageInfo, list[Block])."
                )
                return errors
            first, second = callable_result
            if not isinstance(first, PackageInfo):
                errors.append(f"First element of tuple must be PackageInfo, got {type(first).__name__}.")
            else:
                info = first
            if not isinstance(second, list):
                errors.append(f"Second element of tuple must be a list of Block classes, got {type(second).__name__}.")
                return errors
            block_classes = second
        elif isinstance(callable_result, list):
            block_classes = callable_result
        else:
            errors.append(
                f"Entry-point callable must return (PackageInfo, list[Block]) "
                f"or list[Block], got {type(callable_result).__name__}."
            )
            return errors

        # Validate PackageInfo if present.
        if info is not None:
            errors.extend(self.validate_package_info(info))

        # Validate each block class.
        if not block_classes:
            errors.append("Entry-point returned an empty block list.")

        for i, cls in enumerate(block_classes):
            if not isinstance(cls, type):
                errors.append(f"Block list item [{i}] is not a class: {cls!r}.")
                continue
            if not issubclass(cls, Block):
                errors.append(f"Block list item [{i}] ({cls.__name__}) is not a subclass of Block.")
                continue
            # Validate each block's contract.
            sub_harness = BlockTestHarness(cls, work_dir=self.work_dir)
            block_errors = sub_harness.validate_block()
            for err in block_errors:
                errors.append(f"[{cls.__name__}] {err}")

        return errors

    # ------------------------------------------------------------------
    # Smoke test execution
    # ------------------------------------------------------------------

    def smoke_test(
        self,
        inputs: dict[str, Any],
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Instantiate the block, call ``run()``, and return the outputs.

        Parameters
        ----------
        inputs:
            Mapping of port name to input data.  Values should be
            :class:`Collection` instances or raw data that the block's
            ``run()`` method accepts.
        params:
            Optional parameters passed to :class:`BlockConfig`.

        Returns
        -------
        dict[str, Any]
            The output dict returned by ``block.run()``.

        Raises
        ------
        TypeError
            If the block class is not a valid Block subclass.
        Exception
            Any exception raised by the block's ``run()`` method is
            propagated to the caller for inspection.
        """
        from scistudio.blocks.base.block import Block

        cls = self.block_class
        if not (isinstance(cls, type) and issubclass(cls, Block)):
            raise TypeError(f"{cls!r} is not a subclass of Block. Cannot run smoke test.")

        config_dict: dict[str, Any] = {}
        if params:
            config_dict["params"] = params

        instance = cls(config=config_dict)
        config = instance.config
        return instance.run(inputs, config)
