// Second, independent pass: primesieve_generate_primes (array API, not the iterator) over 10^9-wide blocks
// in parallel; each block generates [x, x+B+20000] so windows starting in [x, x+B) see their next primes.
// Counts runs of k consecutive gaps of 6 (k=1..3) that START in [lo,hi) and END <= P. Usage: qk_range lo hi P
#include <primesieve.h>
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
int main(int c, char** v) {
  uint64_t LO = strtoull(v[1], 0, 10), HI = strtoull(v[2], 0, 10), P = strtoull(v[3], 0, 10);
  const uint64_t B = 1000000000ULL; long long nb = (long long)((HI - LO + B - 1) / B);
  long long k1 = 0, k2 = 0, k3 = 0, np = 0;
  #pragma omp parallel for reduction(+:k1,k2,k3,np) schedule(dynamic,1)
  for (long long j = 0; j < nb; j++) {
    uint64_t x = LO + (uint64_t)j * B, end = x + B < HI ? x + B : HI; size_t n;
    uint64_t* p = (uint64_t*)primesieve_generate_primes(x, end + 20000, &n, UINT64_PRIMES);
    for (size_t i = 0; i + 3 < n && p[i] < end; i++) {
      if (p[i] <= P) np++;
      if (p[i+1] <= P && p[i+1] - p[i] == 6) { k1++;
        if (p[i+2] <= P && p[i+2] - p[i+1] == 6) { k2++;
          if (p[i+3] <= P && p[i+3] - p[i+2] == 6) k3++; } }
    }
    primesieve_free(p);
  }
  printf("{\"lo\":%llu,\"hi\":%llu,\"primes\":%lld,\"k1\":%lld,\"k2\":%lld,\"quads\":%lld}\n",
         (unsigned long long)LO, (unsigned long long)HI, np, k1, k2, k3);
}
