"""Independent integer semantics for the emitted compiler kernel's wrapping ABI."""
import struct


CASES = [
    ('positive-bias-wrap',1,1,1,0,1),
    ('negative-bias-wrap',1,1,1,1,2),
    ('matrix-accumulator-wrap',1,1,131073,2,0),
    ('four-tiles',64,64,5,3,3),
    ('clamped-edges',35,33,9,3,3),
    ('zero-reduction',3,5,0,3,3),
    ('short-reduction',7,9,3,3,0),
]


def a_value(index,hart,pattern):
    return 127-hart if pattern==0 else -128+hart if pattern==1 else -128 if pattern==2 else (index*17+hart*13)%256-128


def b_value(index,hart,pattern):
    return -128 if pattern==2 else 127 if pattern in (0,1) else (index*31+hart*7)%256-128


def bias_value(column,hart,mode):
    if mode==0:
        return 0
    positive=mode==1 or mode==3 and column%2==0
    return (2147483647-column%19-hart*3) if positive else (-2147483648+column%19+hart*3)


def checksum(values):
    result=14695981039346656037
    for value in values:
        for byte in struct.pack('<I',value):
            result=((result^byte)*1099511628211)&((1<<64)-1)
    return result


def corpus():
    cases=[]
    for number,(name,m,n,k,pattern,bias) in enumerate(CASES):
        words={}
        for hart in (0,1):
            words[str(hart)]=[(bias_value(j,hart,bias)+sum(
                a_value(q*m+i,hart,pattern)*b_value(q*n+j,hart,pattern) for q in range(k)))&0xffffffff
                for i in range(m) for j in range(n)]
        words['2']=[16+number]*4
        cases.append({'case_id':'compiler.i8.wrap.'+name,'m':m,'n':n,'k':k,'pattern':pattern,'bias':bias,
                      'expected_words':words,'expected_checksums':{h:checksum(v) for h,v in words.items()}})
    return {'schema':'iris.compiler_i8_wrapping_corpus.v1','split_id':'iris-compiler-i8-wrapping-functional-v1',
            'cases':cases,'harts_online':[0,1,2],'matrix_harts':[0,1],'regions':21,
            'hart2_role':'Concurrent ordinary RVV producer; no matrix instruction.',
            'semantics':'Signed int8 products, sum and bias modulo2^32; explicit mathematical integer oracle.',
            'calibration_usable':False}
