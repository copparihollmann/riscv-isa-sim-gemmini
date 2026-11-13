module IrisBranchCompare(input io_dw, input [4:0] io_fn,
                         input [63:0] io_in1, io_in2,
                         output shuttle_cmp, rocket_cmp);
  RocketALU shuttle(.io_dw(io_dw),.io_fn(io_fn),.io_in1(io_in1),.io_in2(io_in2),
                    .io_cmp_out(shuttle_cmp),.io_out(),.io_adder_out());
  RocketALU_6 rocket(.io_dw(io_dw),.io_fn(io_fn),.io_in1(io_in1),.io_in2(io_in2),
                     .io_cmp_out(rocket_cmp),.io_out(),.io_adder_out());
endmodule
