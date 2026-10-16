/* Generic consecutive-prime pattern counter (colony sieve instrument).
 * usage: sieve_helper A B MOD G1 [G2 ...] -- [C1 C2 ...]
 * Counts p in [A,B) such that p and the next len(G) primes have consecutive gaps G.
 * Prints "total N", per-residue "res r N" (p mod MOD, MOD>=1), and cumulative
 * "chk C N" for each checkpoint C (count of matches with p < C). Uses libprimesieve. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <primesieve.h>
int main(int argc, char** argv) {
  if (argc < 5) { fprintf(stderr, "usage\n"); return 2; }
  uint64_t A = strtoull(argv[1], 0, 10), B = strtoull(argv[2], 0, 10);
  uint64_t M = strtoull(argv[3], 0, 10); if (M < 1) M = 1;
  int k = 0, i = 4; uint64_t G[64]; uint64_t C[4096]; int nc = 0;
  for (; i < argc && strcmp(argv[i], "--"); i++) { if (k >= 64) return 2; G[k++] = strtoull(argv[i], 0, 10); }
  if (i < argc) for (i++; i < argc && nc < 4096; i++) C[nc++] = strtoull(argv[i], 0, 10);
  uint64_t* res = calloc(M, sizeof(uint64_t)); uint64_t* cc = calloc(nc ? nc : 1, sizeof(uint64_t));
  uint64_t W[65]; primesieve_iterator it; primesieve_init(&it);
  primesieve_jump_to(&it, A, B + 10000);
  for (int j = 0; j <= k; j++) W[j] = primesieve_next_prime(&it);
  uint64_t tot = 0;
  while (W[0] < B) {
    int ok = 1;
    for (int j = 0; j < k; j++) if (W[j + 1] - W[j] != G[j]) { ok = 0; break; }
    if (ok) { tot++; res[W[0] % M]++; for (int c = 0; c < nc; c++) if (W[0] < C[c]) cc[c]++; }
    memmove(W, W + 1, k * sizeof(uint64_t)); W[k] = primesieve_next_prime(&it);
  }
  printf("total %llu\n", (unsigned long long)tot);
  for (uint64_t r = 0; r < M; r++) if (res[r]) printf("res %llu %llu\n", (unsigned long long)r, (unsigned long long)res[r]);
  for (int c = 0; c < nc; c++) printf("chk %llu %llu\n", (unsigned long long)C[c], (unsigned long long)cc[c]);
  primesieve_free_iterator(&it); return 0;
}
