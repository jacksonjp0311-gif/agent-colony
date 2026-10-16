#include <stdio.h>
#include <stdlib.h>
int main(int c,char**v){long N[8]={0,200,2000,20000,200000,2000000,20000000,200000000};
unsigned long long a[4]={0};long i=0,cnt=0;int k=1;char b[64];
while(fgets(b,64,stdin)){unsigned long long p=strtoull(b,0,10);i++;a[0]=a[1];a[1]=a[2];a[2]=a[3];a[3]=p;
 if(i>=4&&a[1]==a[0]+6&&a[2]==a[0]+12&&a[3]==a[0]+18)cnt++;
 if(i==N[k]){printf("n=%d N=%ld p(N)=%llu count=%ld\n",k,N[k],p,cnt);if(++k>7)break;}}}
