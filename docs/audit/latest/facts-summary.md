# ADR-042 Facts Audit Summary

## 1. Change Summary

This generated report summarizes the current machine-readable facts registry.
It is intended for human review; drift checks consume the YAML facts directly.

## 2. Overall Status

- Status: `pass`
- Blocks merge: `False`
- Source hash: `c0609aed0f74ca21b724e7d9608a30413776b8393f2e88c52d8c9ff48bd84507`
- Facts file: `docs/facts/generated.yaml`
- Total facts: `1618`
- Symbol facts: `1618`

## 3. Fact Inventory

| Fact kind | Count |
|---|---:|
| `symbol` | 1618 |

## 4. Symbol Inventory

| Symbol kind | Count |
|---|---:|
| `attribute` | 779 |
| `class` | 183 |
| `function` | 493 |
| `module` | 163 |

## 5. Largest Symbol Areas

| Package | Count |
|---|---:|
| `scieasy.blocks` | 421 |
| `scieasy.api` | 391 |
| `scieasy.core` | 335 |
| `scieasy.engine` | 198 |
| `scieasy.qa` | 143 |
| `scieasy.workflow` | 58 |
| `scieasy.cli` | 27 |
| `scieasy.utils` | 26 |
| `scieasy.agent_provisioning` | 9 |
| `scieasy.testing` | 9 |
| `scieasy.ai` | 1 |

## 6. Findings

No error-severity findings.

## 7. Deferred Checks

- `fact_drift`
- `doc_drift`
- `closure`
- `signature_drift`
