"""The read-operation table is the parameter allowlist the reference renders."""

import pytest

from scistudio.panels.reads import READ_OPERATIONS, _only
from scistudio.panels.targets import PanelError


@pytest.mark.parametrize("op", [op for op, spec in READ_OPERATIONS.items() if spec.params is not None])
def test_documented_parameters_are_accepted_and_others_refused(op):
    params = READ_OPERATIONS[op].params
    _only(dict.fromkeys(params or (), 1), op)
    with pytest.raises(PanelError) as caught:
        _only({"undocumented": 1}, op)
    assert caught.value.code == "invalid_request"


def test_table_keys_match_operation_names_and_describe_results():
    for op, spec in READ_OPERATIONS.items():
        assert spec.op == op
        assert spec.result and spec.target
