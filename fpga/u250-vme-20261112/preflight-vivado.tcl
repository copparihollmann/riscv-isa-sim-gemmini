set_param general.maxThreads 2
puts "VIVADO_VERSION=[version -short]"
puts "U250_PARTS=[llength [get_parts -quiet xcu250-figd2104-2L-e]]"
puts "U250_BOARD_13=[llength [get_board_parts -quiet xilinx.com:au250:part0:1.3]]"
exit
