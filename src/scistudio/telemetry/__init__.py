"""Alpha-only telemetry helpers (#1855).

ALPHA-ONLY. This whole package exists to count active internal alpha testers
for the #1848 activation gate and is removed in beta together with the gate.
See the beta-removal checklist in docs/alpha-activation-gate.md.
"""

from scistudio.telemetry.checkin import fire_and_forget, machine_fingerprint

__all__ = ["fire_and_forget", "machine_fingerprint"]
