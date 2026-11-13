 // Compute the real 960-point DFT from one packed 480-point complex FFT.
 // With the original 960 roots, stride 2 indexes both PCM pairs and twiddles.
 bool transform(Complex* dest,int n,int stride,const float* src,uint32_t startUs){
   if(n>=24 && deadline(startUs))return false;
   if(n==1){*dest={src[0],src[1]};return true;}
   const int radix=n%4==0?4:n%2==0?2:n%3==0?3:5, m=n/radix;
   for(int t=0;t<radix;++t)if(!transform(dest+t*m,m,stride*radix,src+t*stride,startUs))return false;
   for(int k=0;k<m;++k){
     if(n>=120 && !(k%16) && deadline(startUs))return false;
     Complex v[5];for(int t=0;t<radix;++t)v[t]=dest[k+t*m];
     if(radix==4){
       for(int t=1;t<4;++t){
         const auto w=roots[t*k*stride];const auto x=v[t];
         v[t]={x.r*w.r-x.i*w.i,x.r*w.i+x.i*w.r};
       }
       const Complex a={v[0].r+v[2].r,v[0].i+v[2].i},b={v[0].r-v[2].r,v[0].i-v[2].i};
       const Complex c={v[1].r+v[3].r,v[1].i+v[3].i},d={v[1].r-v[3].r,v[1].i-v[3].i};
       dest[k]={a.r+c.r,a.i+c.i};dest[k+m]={b.r+d.i,b.i-d.r};
       dest[k+2*m]={a.r-c.r,a.i-c.i};dest[k+3*m]={b.r-d.i,b.i+d.r};
     }else{
       for(int j=0;j<radix;++j){
         int inc=(k+j*m)*stride,phase=0;Complex s=v[0];
         for(int t=1;t<radix;++t){phase+=inc;if(phase>=960)phase-=960;
           const auto w=roots[phase];s.r+=v[t].r*w.r-v[t].i*w.i;s.i+=v[t].r*w.i+v[t].i*w.r;}
         dest[k+j*m]=s;
       }
     }
   }
   return true;
 }
 float power(int k)const{
   const auto p=out[k],q=out[480-k],w=roots[k];
   float dr=p.r-q.r,di=p.i+q.i;
   float r=(p.r+q.r+w.r*di+w.i*dr)*.5f, i=(p.i-q.i-w.r*dr+w.i*di)*.5f;
   return r*r+i*i;
 }
