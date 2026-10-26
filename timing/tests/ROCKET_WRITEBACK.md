# Scalar Rocket writeback arbitration

`test_rocket_writeback.cpp` checks RocketCore.scala763–825 and1007–1015,
plus Multiplier.scala161–183. The single original divider response retains
its PC, bits, destination and observed operands while valid is blocked.
Normal `wb_reg_valid && wb_ctrl.wxd` blocks the long-latency arbiter even
when normal `wb_wen` would be false. An integer D-cache replay overrides
that arbiter; otherwise priority is divider, RoCC, vector. Successful late
writeback supplies the same-edge scoreboard clear/bypass. MulDiv becomes
request-ready on the following edge, after its done-state response fires.

This component consumes actual WB/replayed-memory events. The existing
observer does not yet supply those through a finite scalar pipeline, so it
still reports divider response-ready as assumed immediate. An ALU forwarding
timestamp cannot supply a normal register-file WB event. This component
does not alter any frozen runtime or claim timing coverage by itself.
