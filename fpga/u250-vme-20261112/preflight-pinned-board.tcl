set_param board.repoPaths [list {/scratch/copparihollmann/u250-vme-20261112/provenance/open-nic-board-files}]
set b [get_board_parts xilinx.com:au250:part0:1.3]
puts "PINNED_BOARD_COUNT=[llength $b]"
foreach p [list_property $b] { if {[string match -nocase *file* $p] || [string match -nocase *path* $p]} {puts "BOARD_PROPERTY_$p=[get_property $p $b]"}}
exit
