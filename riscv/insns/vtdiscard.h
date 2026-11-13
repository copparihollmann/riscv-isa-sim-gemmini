// Iris fork: preserve strict upstream matching outside --iris-vme.
require(P.VU.iris_mode || ((insn.bits() & 0xffffffff) == 0x43c06057));
require_extension(EXT_ZVTBASE);
require_vector(false);
if (!P.VU.iris_mode) {
require(STATE.sstatus->enabled(SSTATUS_MS));
require(P.VU.vstart->read() == 0);

// set mstatus.MS to Initial
STATE.mstatus->write((STATE.mstatus->read() & ~SSTATUS_MS) | (SSTATUS_MS & (SSTATUS_MS >> 1)));
// set vsstatus.MS to Initial if V=1
STATE.sstatus->write((STATE.sstatus->read() & ~SSTATUS_MS) | (SSTATUS_MS & (SSTATUS_MS >> 1)));

}

VECTOR_END;
