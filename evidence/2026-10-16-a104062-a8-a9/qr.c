#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <stddef.h>
typedef struct { size_t i, size; uint64_t start, stop_hint; uint64_t* primes; void* memory; int is_error; } primesieve_iterator;
void primesieve_init(primesieve_iterator*); void primesieve_free_iterator(primesieve_iterator*);
void primesieve_jump_to(primesieve_iterator*, uint64_t, uint64_t); void primesieve_generate_next_primes(primesieve_iterator*);
static inline uint64_t nx(primesieve_iterator* it){ if(++it->i >= it->size){ primesieve_generate_next_primes(it); it->i=0;} return it->primes[it->i]; }
int main(int c,char**v){uint64_t lo=strtoull(v[1],0,10),hi=strtoull(v[2],0,10);primesieve_iterator it;primesieve_init(&it);primesieve_jump_to(&it,lo,hi+1000);it.i=(size_t)-1;it.size=0;
uint64_t a=nx(&it),b=nx(&it),d=nx(&it),e=nx(&it);long n=0,k=0;while(a<=hi){n++;if(b==a+6&&d==a+12&&e==a+18)k++;a=b;b=d;d=e;e=nx(&it);}printf("pi=%ld count=%ld\n",n,k);}
