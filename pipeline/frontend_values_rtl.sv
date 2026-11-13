module IrisPureAlu(input io_dw, input [4:0] io_fn,
                   input [63:0] io_in1, io_in2,
                   output [63:0] shuttle_out, rocket_out);
  RocketALU shuttle(.io_dw(io_dw),.io_fn(io_fn),.io_in1(io_in1),.io_in2(io_in2),
                    .io_out(shuttle_out),.io_cmp_out(),.io_adder_out());
  RocketALU_6 rocket(.io_dw(io_dw),.io_fn(io_fn),.io_in1(io_in1),.io_in2(io_in2),
                     .io_out(rocket_out),.io_cmp_out(),.io_adder_out());
endmodule
