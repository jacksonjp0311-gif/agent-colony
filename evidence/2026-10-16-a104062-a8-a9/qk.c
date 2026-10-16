// For each N: count i<=N-k with gaps g_i..g_{i+k-1} all == 6 (k=1..4), fully inside first N primes.
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
typedef struct { size_t i, size; uint64_t start, stop_hint; uint64_t* primes; void* memory; int is_error; } primesieve_iterator;
void primesieve_init(primesieve_iterator*); void primesieve_free_iterator(primesieve_iterator*);
void primesieve_jump_to(primesieve_iterator*, uint64_t, uint64_t); void primesieve_generate_next_primes(primesieve_iterator*);
static inline uint64_t nx(primesieve_iterator* it){ if(++it->i >= it->size){ primesieve_generate_next_primes(it); it->i=0;} return it->primes[it->i]; }
int main(int c,char**v){ uint64_t P=strtoull(v[1],0,10); int S=512; int64_t tot[5]={0};
 #pragma omp parallel for schedule(dynamic,1)
 for(int s=0;s<S;s++){ uint64_t lo=P/S*s, hi=(s==S-1)?P+1:P/S*(s+1); int64_t loc[5]={0};
  primesieve_iterator it; primesieve_init(&it); primesieve_jump_to(&it, lo, hi+100000); it.i=(size_t)-1; it.size=0;
  uint64_t q[5]; for(int j=0;j<5;j++) q[j]=nx(&it);
  while(q[0]<hi){ for(int k=1;k<=4;k++){ if(q[k]>P) break; if(q[k]-q[k-1]!=6) break; loc[k]++; }
   for(int j=0;j<4;j++) q[j]=q[j+1]; q[4]=nx(&it);} 
  #pragma omp critical
  for(int k=1;k<=4;k++) tot[k]+=loc[k];
  primesieve_free_iterator(&it);}
 printf("%llu",(unsigned long long)P); for(int k=1;k<=4;k++) printf(" %lld",(long long)tot[k]); printf("\n"); }
