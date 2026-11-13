.text
.global iris_ownership_patterns
iris_ownership_patterns:
 vmv.v.i v8, 0
 vadd.vi v8, v8, 1
 vmv.x.s a0, v8
