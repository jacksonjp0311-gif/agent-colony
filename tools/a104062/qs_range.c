// Count consecutive prime quadruples p,p+6,p+12,p+18 with first prime in [lo,hi) and last prime <= P.
// Overlap rule: the iterator runs past hi to get the next 3 primes, so quadruples that cross shard
// edges are counted exactly once (by the shard that holds their first prime). Also returns #primes in [lo,hi), <=P.
// Usage: qs_range lo hi P threads
#include <primesieve.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int c, char** v) {
  uint64_t LO = strtoull(v[1], 0, 10), HI = strtoull(v[2], 0, 10), P = strtoull(v[3], 0, 10);
  int T = atoi(v[4]), S = T * 64; long long tot = 0, tp = 0;
  #pragma omp parallel for reduction(+:tot,tp) schedule(dynamic,1) num_threads(T)
  for (int s = 0; s < S; s++) {
    uint64_t lo = LO + (HI - LO) / S * s, hi = (s == S - 1) ? HI : LO + (HI - LO) / S * (s + 1);
    primesieve_iterator it; primesieve_init(&it); primesieve_jump_to(&it, lo, hi + 100000);
    uint64_t a = primesieve_next_prime(&it), b = primesieve_next_prime(&it), d = primesieve_next_prime(&it), e = primesieve_next_prime(&it);
    while (a < hi) {
      if (a <= P) tp++;
      if (e <= P && b == a + 6 && d == a + 12 && e == a + 18) tot++;
      a = b; b = d; d = e; e = primesieve_next_prime(&it);
    }
    primesieve_free_iterator(&it);
  }
  printf("{\"lo\":%llu,\"hi\":%llu,\"primes\":%lld,\"quads\":%lld}\n", (unsigned long long)LO, (unsigned long long)HI, tp, tot);
}
