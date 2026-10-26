# Store controller admission and response completion

Selected StoreController.scala160–163 drives DMA row requests. Lines286–294
release the controller command on final request acceptance, separately from
DMACommandTracker.scala's original response counting and completion. The
controller's non-flow command FIFO exposes its next head on the following edge.
A singleton visits sending_rows before recognizing the wrapped-zero counter,
adding that actual state transition before its head releases.

`source_store_request_release=1` requires the selected final-request release law
and exact configured tracker capacity. Full/partial original unpooled packets
and ordered pooling use the existing finite readout dispatch queue. Acceptance
of all original dispatch requests releases the controller head; no data token
or transaction ACK is completed by that event. The two original DMA command
credits remain held through their existing ACK/publication completion. A third
command waits for real credit. Resources and all downstream finite queues stay
unchanged.

For unpooled commands, original local-row consumption is now the actual final
SRAM response capture. The readout pipeline retains that data under downstream
backpressure. Local rows can then be overwritten without waiting for DRAM ACK;
all original cache publication and response dependencies remain pending. Pooled
commands already retain separate local consumption and output completion.

The focused ordered-output stress checks a second command's local read before
the first command's final publication, while a third command cannot use a third
DMA credit. It also checks the original packet count and all preceding mixed
writer/pool controls. Selected source pins and measured evidence are retained
with each immutable runtime export.

## Local DMA response selection

`source_store_local_request_completion=1` additionally selects the actual
Scratchpad.scala534/747 local read-request response. Garbage pooling requests
respond at dispatch dequeue (line355). StoreController.scala193–195 returns one
original request count to DMACommandTracker. The registered `bytes_left` exposes
completion on the next edge; the registered `valid` clear exposes that same
tracker credit one edge later. Both original command credits remain finite.

Each original command retains separate local response counting, local data
consumption, and downstream writer completion custody. Local tracker completion
releases its reservation station entry; it does not complete any write ACK or
SourceD publication. A bounded live-obligation map retains every original
command's output completion and registered credit release even after completed
command history is pruned. Fence drain awaits those obligations as well as the
local command completions. StreamWriter's original transaction slots and all
readout/SourceD backpressure remain unchanged.

The stress checks the third command can begin before the first command's final
publication only after its actual final local request plus two registered edges.
All 48 original packets complete, and fence completion follows final publication.
Mixed raw/i8 writes and pooled requests (including garbage) check exact local
response/completion conservation. Pool reduction-register ownership is tied to
its original command so a later live command cannot be mistaken for an earlier
command's unfinished reduction.

Controller.scala425–440 gives execute completion first priority, load second,
and store last. Store completion settles after ordinary source events on each
edge, waits if an existing higher-priority completion milestone occupies that
edge, and permits at most one store handshake per edge. Credit reuse is one
registered edge after the successful handshake. This uses the existing execute
and load completion milestones; it does not qualify their remaining timing
abstractions or add a new completion port.
