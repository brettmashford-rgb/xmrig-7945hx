"""Exact checkpoint-local identity, independent scalar research reference. ISC."""
def signed8(value):return ((value&255)^128)-128

def project(a,pairs):
    if len(a)!=128 or len(pairs)!=128:raise ValueError('one K128 checkpoint required')
    if any(type(v)is not int or not -127<=v<=127 for v in a):raise ValueError('actual signed-byte A values required')
    coefficients=[0]*128
    for actual,(first,second)in zip(a,pairs):
        if not 0<=first<128 or not 0<=second<128:raise ValueError('invalid B basis')
        residual=actual-64;coefficients[first]+=residual;coefficients[second]-=residual
    low=[signed8(v)for v in coefficients]
    corrections=[(r,(v-low[r])//256)for r,v in enumerate(coefficients)if v!=low[r]]
    if any(not -128<=high<=127 for r,high in corrections):raise ValueError('correction outside signed-byte storage')
    return low,corrections,sum(v-64 for v in a)

def dot_from_projection(projected,uniform,pairs):
    if len(uniform)!=128 or any(not -32<=v<=31 for v in uniform):raise ValueError('B uniform rank128 required')
    low,corrections,a_sum=projected
    b_sum=sum(uniform[first]-uniform[second]for first,second in pairs)
    return sum(a*b for a,b in zip(low,uniform))+256*sum(high*uniform[r]for r,high in corrections)+64*a_sum+64*b_sum+524288
