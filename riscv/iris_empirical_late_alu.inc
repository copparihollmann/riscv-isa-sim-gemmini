// Source finite lateALU: COM retires, WB computes/writes/bypasses one edge later.
void iris_timing_adapter::empirical_late_alu_before(unsigned h,size_t id){
 auto&r=pure_[h].instructions.at(id);if(!r.late_alu||r.retired||r.squashed||r.late_before||clock_.now()!=r.com_cycle||!r.late_operands||!pure_[h].values->operands_ready(*r.late_operands))throw std::logic_error("IRIS_LATE_ALU_COM_OWNER_OR_OPERANDS");
 r.late_before=cores_[h]->get_state()->XPR.read_transport(r.uop.rd);
}
void iris_timing_adapter::empirical_late_alu_after(unsigned h,size_t id,bool retired){
 auto&r=pure_[h].instructions.at(id);if(!r.late_before)throw std::logic_error("IRIS_LATE_ALU_COM_SNAPSHOT");
 r.late_after=cores_[h]->get_state()->XPR.read_transport(r.uop.rd);cores_[h]->get_state()->XPR.write_transport(r.uop.rd,*r.late_before);
 if(!retired)throw std::runtime_error("IRIS_LATE_ALU_UNEXPECTED_PURE_TRAP");
 const auto operands=pure_[h].values->read(*r.late_operands);if(operands[0]&&operands[1]){auto op=iris::frontend::PureAluValue::decode(r.uop.expanded);if(!op||op->evaluate(r.pc,*operands[0],*operands[1])!=r.late_after->value)throw std::logic_error("IRIS_LATE_ALU_RRD_COM_VALUE_MISMATCH");}
 cpu_event(h,"late_ALU_semantic_COM",r.pc,r.uop.raw,id,"\"physical_WB\":"+std::to_string(r.com_cycle+profile_.harts[h].divider));
}
void iris_timing_adapter::empirical_late_alu_write(unsigned h,size_t id){
 auto&p=pure_[h];auto&r=p.instructions.at(id);if(!r.late_alu||!r.retired||r.squashed||!r.late_after||r.private_value_ready||clock_.now()!=r.com_cycle+profile_.harts[h].divider)throw std::logic_error("IRIS_LATE_ALU_WB_OWNER");
 const auto&v=*r.late_after;const bool known=std::all_of(v.known.begin(),v.known.end(),[](uint8_t x){return x==255;});r.private_value=known?std::optional<uint64_t>(v.value):std::nullopt;
 p.values->complete_retired_external(r.uop.rd,id,r.private_value);cores_[h]->get_state()->XPR.write_transport(r.uop.rd,v);r.private_value_ready=true;r.late_operands.reset();
 cpu_event(h,"late_ALU_physical_WB",r.pc,r.uop.raw,id,"\"value\":"+std::to_string(v.value)+",\"fully_known\":"+(known?"true":"false"));
}
