/* Erdos #699 fast checker (reduced). Bounded evidence, not proof.
 * Statement: for all 1<=i<j<=n/2 some prime p>=i divides gcd(C(n,i),C(n,j)).
 * Reduction (del Pin / MaxDKaos, erdosproblems.com/forum/thread/699, Jul 2026): if a prime q lies in
 * (n-i,n] then q>n/2>=j>i divides both, so only n composite and i <= n - prevprime(n) need checking.
 * For p>i: p | C(n,i) iff some multiple of p lies in (n-i,n] (Kummer).  For p=i prime:
 * p | C(n,p) iff floor(n/p) % p == 0 (Lucas).  p | C(n,j) iff adding j and n-j in base p carries,
 * i.e. iff some base-p digit of j exceeds that of n (Kummer/Lucas).  Every p in the strict set S
 * (primes p>i dividing C(n,i)) satisfies b_p = n mod p < i, and p∤C(n,j) forces j mod p <= b_p.  We pick
 * a prefix C of S (ordered by log p / log(b_p+1)) minimising prod(b_p+1)*ceil(n/2 / prod p), enumerate the
 * residues j mod prod(C) by CRT, lift to all j<=n/2, and test each against every prime in S (full
 * Lucas digit check) and, for the main version, against p=i when that prime divides C(n,i).  Reports: STRICT n i j (min j; version p>i) and MAIN n i j (version p>=i).
 * usage: fast699 LO HI      (checks every n in [LO,HI], HI <= 4e12)
 */
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <string.h>
#include <math.h>
typedef uint64_t u64;
#define MARGIN 4096
#define SEG (1u<<20)
#define MAXF 12
static uint32_t *sp; static int nsp;
static u64 fac[SEG+MARGIN][MAXF]; static uint8_t fc[SEG+MARGIN]; static u64 rem_[SEG+MARGIN];
static u64 N; static u64 half;
static u64 S[4096]; static int ns;            /* strict set: primes > i dividing C(n,i) */
static int extra; static u64 pi_;           /* main adds p=i */
static int nocarry(u64 j,u64 n,u64 p){ while(j){ if(j%p>n%p) return 0; j/=p; n/=p;} return 1; }
static double count_adm(u64 n,u64 p){ double c=1; while(n){ c*=(double)(n%p+1); n/=p;} return c; }
static long long strict_j, main_j; static u64 cands, total_cands; static u64 lo_i;
typedef unsigned __int128 u128;
static u64 Cp[4096], Cb[4096]; static int nc; static u128 Mk[4097];
static u64 inv_mod(u64 a,u64 m){ long long t=0,nt=1; long long r=(long long)m, nr=(long long)(a%m);
  while(nr){ long long q=r/nr, tmp=t-q*nt; t=nt; nt=tmp; tmp=r-q*nr; r=nr; nr=tmp; } if(t<0) t+=(long long)m; return (u64)t; }
static u64 invs[4096];
typedef struct { u64 p,b; double e; } PB; static PB pbv[4096];
static int cmp_pb(const void*x,const void*y){ double a=((const PB*)x)->e,b=((const PB*)y)->e; return a<b?1:(a>b?-1:(((const PB*)x)->p<((const PB*)y)->p?-1:1)); }
static void test_j(u64 j){
  if(j<=lo_i||j>half) return; cands++;
  for(int t=0;t<ns;t++) if(!nocarry(j,N,S[t])) return;
  if(strict_j<0 || (long long)j<strict_j) strict_j=(long long)j;
  if(main_j<0 && (!extra || nocarry(j,N,pi_))) main_j=(long long)j;
}
static void dfs(int k,u128 x){   /* x = residue mod Mk[k] */
  if(k==nc){ for(u128 j=x; j<=half; j+=Mk[nc]) test_j((u64)j); return; }
  u64 p=Cp[k]; u64 xm=(u64)(x%p);
  for(u64 e=0;e<=Cb[k];e++){ u64 t=(u64)(((u128)((e+p-xm)%p)*invs[k])%p); dfs(k+1, x+Mk[k]*t); }
}
static void search(void){
  /* order S by efficiency log p / log(b+1) desc (b=0 first) */
  static u64 B[4096];
  for(int t=0;t<ns;t++){ pbv[t].p=S[t]; pbv[t].b=N%S[t]; pbv[t].e = pbv[t].b==0? 1e300 : log((double)S[t])/log((double)pbv[t].b+1); }
  qsort(pbv,ns,sizeof(PB),cmp_pb);
  for(int t=0;t<ns;t++){ S[t]=pbv[t].p; B[t]=pbv[t].b; }
  double best=1e300; int bk=0; double prodb=1; long double M=1;
  for(int k=0;k<=ns;k++){
    long double lifts = M>half? 1 : ((long double)half/M+1);
    double cost=prodb*(double)lifts; if(cost<best){best=cost;bk=k;}
    if(k==ns || M>half) break; prodb*=(double)(B[k]+1); M*=S[k];
  }
  nc=bk; Mk[0]=1; for(int k=0;k<nc;k++){ Cp[k]=S[k]; Cb[k]=B[k]; invs[k]=inv_mod((u64)(Mk[k]%Cp[k]),Cp[k]); Mk[k+1]=Mk[k]*Cp[k]; }
  cands=0; dfs(0,0); total_cands+=cands;
}
int main(int argc,char**argv){
  if(argc<3){fprintf(stderr,"usage: %s LO HI\n",argv[0]);return 2;}
  u64 LO=strtoull(argv[1],0,10), HI=strtoull(argv[2],0,10); if(LO<4) LO=4;
  u64 r=(u64)sqrtl((long double)HI)+2; char*c=calloc(r+1,1); sp=malloc(sizeof(uint32_t)*(r+1));
  for(u64 i=2;i<=r;i++) if(!c[i]){ sp[nsp++]=i; for(u64 j=i*i;j<=r;j+=i) c[j]=1; } free(c);
  u64 nmain=0,nstrict=0,maxgap=0,ncomp=0,npairs=0; u64 gapn=0;
  for(u64 base=LO; base<=HI; base+=SEG){
    u64 top=base+SEG-1; if(top>HI) top=HI;
    u64 L = base>MARGIN+2? base-MARGIN : 2; u64 W=top-L+1;
    for(u64 x=0;x<W;x++){ fc[x]=0; rem_[x]=L+x; }
    for(int t=0;t<nsp;t++){ u64 p=sp[t]; if(p*p>top) break; u64 s=(L+p-1)/p*p;
      for(u64 x=s;x<=top;x+=p){ u64 k=x-L; fac[k][fc[k]++]=p; while(rem_[k]%p==0) rem_[k]/=p; } }
    for(u64 x=0;x<W;x++) if(rem_[x]>1) fac[x][fc[x]++]=rem_[x];
    /* previous prime before base */
    long long prev=-1; for(u64 x=base-L; x-- >0;) if(fc[x]==1&&fac[x][0]==L+x){prev=(long long)(L+x);break;}
    if(prev<0 && base>MARGIN){ fprintf(stderr,"ERROR no prime in margin below %llu\n",(unsigned long long)base); return 3; }
    for(u64 n=base;n<=top;n++){
      u64 k=n-L; if(fc[k]==1&&fac[k][0]==n){ prev=(long long)n; continue; }
      ncomp++; u64 d=n-(u64)prev; if(d>maxgap){maxgap=d;gapn=n;}
      if(d>=MARGIN){ fprintf(stderr,"ERROR gap exceeds margin\n"); return 3; }
      N=n; half=n/2; u64 W2[4096]; int nw=0;
      for(u64 i=1;i<=d && i<half;i++){   /* need i<j<=n/2 */
        u64 x=n-i+1-L;                  /* add element n-i+1 to window */
        for(int f=0;f<fc[x];f++){ u64 p=fac[x][f]; int seen=0; for(int t=0;t<nw;t++) if(W2[t]==p){seen=1;break;} if(!seen&&nw<4096) W2[nw++]=p; }
        if(nw>=4096){ fprintf(stderr,"ERROR window prime overflow\n"); return 3; }
        ns=0; for(int t=0;t<nw;t++) if(W2[t]>i) S[ns++]=W2[t];
        extra=0; pi_=i; if(i>=2){ int isp=1; for(u64 q=2;q*q<=i;q++) if(i%q==0){isp=0;break;} if(isp && (n/i)%i==0) extra=1; }
        npairs++; strict_j=-1; main_j=-1; lo_i=i;
        if(ns==0){ /* no strict prime: every j in (i,n/2] fails strict; main needs only p=i */
          strict_j=(long long)(i+1);
          if(!extra) main_j=(long long)(i+1);
          else { for(u64 j=i+1;j<=half;j++) if(nocarry(j,n,i)){ main_j=(long long)j; break; } }
        } else search();
        if(strict_j>=0){ nstrict++; printf("STRICT %llu %llu %lld\n",(unsigned long long)n,(unsigned long long)i,strict_j); }
        if(main_j>=0){ nmain++; printf("MAIN %llu %llu %lld\n",(unsigned long long)n,(unsigned long long)i,main_j); }
      }
    }
  }
  printf("SUMMARY lo=%llu hi=%llu composites=%llu pairs_ni=%llu candidates=%llu maxgap=%llu at=%llu strict=%llu main=%llu\n",
    (unsigned long long)LO,(unsigned long long)HI,(unsigned long long)ncomp,(unsigned long long)npairs,(unsigned long long)total_cands,
    (unsigned long long)maxgap,(unsigned long long)gapn,(unsigned long long)nstrict,(unsigned long long)nmain);
  return 0;
}
