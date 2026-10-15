# Trusted simulator tooling

This directory owns the public functional-model packaging, primitive-command
observer and pinned device facts for this simulator's accelerator extension.
No compiler, instruction-selection passes, workload schedules or generated OOT
implementation belongs here. Reusable packaging and calibration machinery lives
in Merlin's standalone `merlin-timing` package.

These sources, vendor headers and selfcheck fixtures are operator build inputs.
Phase 1 receives runtime endpoints through its broker, without access to these
source directories or to the handwritten compiler. Phase 2 loads its timing
provider and pricing artifact explicitly. Unknown timing stays unknown; no
synthetic test, archived instruction count or functional run qualifies cycles.

Keep functional-extension sources unchanged, bounded source custody, explicit
ABI/configuration selections and the no-FSM compiler policy independent. Build
products go in the task's `.tmp/` or caller-selected build directory.
