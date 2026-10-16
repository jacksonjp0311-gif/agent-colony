// Sharded counter: consecutive prime quadruples (p,p+6,p+12,p+18 all consecutive primes)
// with first prime in [lo,hi) and LAST prime <= P (boundary: fully inside first N primes).
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
typedef struct { size_t i, size; uint64_t start, stop_hint; uint64_t* primes; void* memory; int is_error; } primesieve_iterator;
void primesieve_init(primesieve_iterator*); void primesieve_free_iterator(primesieve_iterator*);
void primesieve_jump_to(primesieve_iterator*, uint64_t, uint64_t); void primesieve_generate_next_primes(primesieve_iterator*);
static inline uint64_t nx(primesieve_iterator* it){ if(++it->i >= it->size){ primesieve_generate_next_primes(it); it->i=0;} return it->primes[it->i]; }
int main(int c,char**v){ uint64_t P=strtoull(v[1],0,10); int T=atoi(v[2]); int64_t tot=0, tp=0;
 #pragma omp parallel for reduction(+:tot) reduction(+:tp) schedule(dynamic,1)
 for(int s=0;s<T*64;s++){ uint64_t lo=P/(T*64)*s, hi=(s==T*64-1)?P+1:P/(T*64)*(s+1);
  primesieve_iterator it; primesieve_init(&it); primesieve_jump_to(&it, lo, hi+1000000);
  it.i = (size_t)-1; it.size=0; // ensure first nx triggers generate
  uint64_t a=nx(&it),b=nx(&it),d=nx(&it),e=nx(&it); int64_t cnt=0,np=0;
  while(a<hi){ if(e<=P && b==a+6 && d==a+12 && e==a+18) cnt++; if(a<=P) np++; a=b;b=d;d=e;e=nx(&it); }
  tot+=cnt; tp+=np; primesieve_free_iterator(&it);}
 printf("P=%llu primes_le_P=%lld count=%lld\n",(unsigned long long)P,(long long)tp,(long long)tot); }
