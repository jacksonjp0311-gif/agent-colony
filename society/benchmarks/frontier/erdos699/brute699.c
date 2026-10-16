/* Erdos #699 independent brute-force checker. Bounded evidence, not proof.
 * Shares no code with fast699.c.  Two modes:
 *   full LO HI : NO reduction. For every n in [LO,HI] and every 1<=i<j<=n/2 decide directly whether some
 *                prime p>=i (main) / p>i (strict) divides both C(n,i) and C(n,j).  Exponents of C(n,k)
 *                are tracked exactly via C(n,k)=C(n,k-1)(n-k+1)/k over all primes <= n.
 *   lite LO HI : for huge n where all pairs are infeasible: uses ONLY the prime-free-window fact (i <=
 *                n - prevprime(n)), then for EVERY j in (i,n/2] tests divisibility directly with Kummer's
 *                theorem (carry when adding j and n-j in base p), primes found by trial division and
 *                Legendre valuations. No CRT / Lucas candidate enumeration.
 * Output format identical to fast699: "STRICT n i jmin", "MAIN n i jmin", then SUMMARY.
 */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
typedef unsigned long long ull;
static int kummer_carry(ull a, ull b, ull p){ int c=0; while(a||b||c){ ull s=a%p+b%p+c; c = s>=p; if(c) return 1; a/=p; b/=p; } return 0; }
static ull leg(ull n, ull p){ ull v=0; while(n){ n/=p; v+=n; } return v; }
static int vC(ull n, ull k, ull p){ return leg(n,p)-leg(k,p)-leg(n-k,p) > 0; }
static int isprime(ull x){ if(x<2) return 0; for(ull q=2;q*q<=x;q++) if(x%q==0) return 0; return 1; }
static int full(ull LO, ull HI){
  ull M=HI; int *spf=calloc(M+1,sizeof(int)); for(ull i=2;i<=M;i++) if(!spf[i]) for(ull j=i;j<=M;j+=i) if(!spf[j]) spf[j]=(int)i;
  int *pidx=calloc(M+1,sizeof(int)); ull ns=0,nm=0;
  for(ull n=(LO<4?4:LO); n<=HI; n++){
    ull h=n/2; if(h<2) continue;
    int np=0; for(ull p=n;p>=2;p--) if(spf[p]==(int)p) pidx[p]=np++;   /* descending: idx 0 = largest prime <= n */
    int W=(np+63)/64; uint64_t *bits=calloc((size_t)(h+1)*W,8); int *ex=calloc(np,sizeof(int));
    for(ull k=1;k<=h;k++){ ull x=n-k+1; while(x>1){ int p=spf[x]; ex[pidx[p]]++; x/=p; } x=k; while(x>1){ int p=spf[x]; ex[pidx[p]]--; x/=p; }
      uint64_t *b=bits+(size_t)k*W; for(int t=0;t<np;t++) if(ex[t]>0) b[t>>6]|=1ULL<<(t&63); }
    /* count of primes >= v in the descending order = number of primes in [v,n] */
    int *ge=calloc(n+2,sizeof(int)); for(ull p=n;p>=1;p--) ge[p]=ge[p+1]+(p>=2 && spf[p]==(int)p);
    for(ull i=1;i<h;i++){
      int cge=ge[i], cgt=ge[i+1];
      long long js=-1, jm=-1; uint64_t *bi=bits+(size_t)i*W;
      for(ull j=i+1;j<=h && (js<0||jm<0);j++){
        uint64_t *bj=bits+(size_t)j*W; int okg=0, okt=0;
        for(int w=0; w*64<cge; w++){ uint64_t m=bi[w]&bj[w]; if(!m) continue;
          int lim=cge-w*64; uint64_t mg = lim>=64? m : (m & ((1ULL<<lim)-1)); if(mg) okg=1;
          int limt=cgt-w*64; if(limt>0){ uint64_t mt = limt>=64? m : (m & ((1ULL<<limt)-1)); if(mt) okt=1; }
          if(okt) break; }
        if(!okt && js<0) js=(long long)j;
        if(!okg && jm<0) jm=(long long)j;
      }
      if(js>=0){ ns++; printf("STRICT %llu %llu %lld\n",n,i,js); }
      if(jm>=0){ nm++; printf("MAIN %llu %llu %lld\n",n,i,jm); }
    }
    free(bits); free(ex); free(ge);
  }
  printf("SUMMARY mode=full lo=%llu hi=%llu strict=%llu main=%llu\n",LO,HI,ns,nm); return 0;
}
static int lite(ull LO, ull HI){
  ull ns=0,nm=0,pairs=0; ull prev=0; for(ull x=LO-1;x>=2;x--) if(isprime(x)){prev=x;break;}
  for(ull n=LO;n<=HI;n++){
    if(isprime(n)){ prev=n; continue; }
    ull d=n-prev, h=n/2;
    ull P[4096]; int np=0;
    for(ull i=1;i<=d && i<h;i++){
      ull x=n-i+1; for(ull q=2;q*q<=x;q++) if(x%q==0){ int s=0; for(int t=0;t<np;t++) if(P[t]==q) s=1; if(!s) P[np++]=q; while(x%q==0) x/=q; }
      if(x>1){ int s=0; for(int t=0;t<np;t++) if(P[t]==x) s=1; if(!s) P[np++]=x; }
      ull Sg[4096]; int ng=0, nt=0; ull St[4096];
      for(int t=0;t<np;t++) if(P[t]>=i && vC(n,i,P[t])){ Sg[ng++]=P[t]; if(P[t]>i) St[nt++]=P[t]; }
      if(i>=2 && isprime(i) && vC(n,i,i)){ int s=0; for(int t=0;t<ng;t++) if(Sg[t]==i) s=1; if(!s) Sg[ng++]=i; }
      pairs++; long long js=-1, jm=-1;
      for(ull j=i+1;j<=h && (js<0||jm<0);j++){
        int okt=0; for(int t=0;t<nt;t++) if(kummer_carry(j,n-j,St[t])){okt=1;break;}
        int okg=okt; if(!okg) for(int t=0;t<ng;t++) if(kummer_carry(j,n-j,Sg[t])){okg=1;break;}
        if(!okt && js<0) js=(long long)j;
        if(!okg && jm<0) jm=(long long)j;
      }
      if(js>=0){ ns++; printf("STRICT %llu %llu %lld\n",n,i,js); }
      if(jm>=0){ nm++; printf("MAIN %llu %llu %lld\n",n,i,jm); }
    }
  }
  printf("SUMMARY mode=lite lo=%llu hi=%llu pairs_ni=%llu strict=%llu main=%llu\n",LO,HI,pairs,ns,nm); return 0;
}
int main(int c,char**v){ if(c<4){fprintf(stderr,"usage: %s full|lite LO HI\n",v[0]);return 2;}
  ull lo=strtoull(v[2],0,10), hi=strtoull(v[3],0,10); return strcmp(v[1],"full")==0? full(lo,hi): lite(lo,hi); }
