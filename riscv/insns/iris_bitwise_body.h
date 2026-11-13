// Bitwise dataflow can establish bits without observing unrelated unknown bits.
// The caller supplies raw operands/masks and the architectural operand identity.
iris_definedness::Value<reg_t> iris_result;
if constexpr(iris_kind==0)iris_result.value=iris_left.value&iris_right.value;
else if constexpr(iris_kind==1)iris_result.value=iris_left.value|iris_right.value;
else iris_result.value=iris_left.value^iris_right.value;
for(size_t byte=0;byte<sizeof(reg_t);++byte) {
  const uint8_t a=iris_left.value>>(byte*8),b=iris_right.value>>(byte*8);
  const uint8_t ka=iris_left.known[byte],kb=iris_right.known[byte];
  if constexpr(iris_kind==0)iris_result.known[byte]=(ka&kb)|(ka&~a)|(kb&~b);
  else if constexpr(iris_kind==1)iris_result.known[byte]=(ka&kb)|(ka&a)|(kb&b);
  else iris_result.known[byte]=iris_same?0xff:ka&kb;
}
p->iris_write_xpr_transport(iris_dest,iris_result);
