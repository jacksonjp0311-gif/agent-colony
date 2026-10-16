import sys;import os;sys.path.insert(0,os.path.join(os.path.dirname(__file__),'..','..','society','benchmarks','frontier'));import frontier_impl as F
T=[20*10**n for n in range(1,8)];pi=c=0;lo=2;W=50_000_000;hits={}
while pi<T[-1]:
  d=F.prime_run_scan(lo,lo+W-1,[6,12,18],pi,c,T,engine='python');pi,c=d['pi'],d['count'];hits.update(d['terms_hit']);lo+=W
print({k:v['count'] for k,v in hits.items()},flush=True)
