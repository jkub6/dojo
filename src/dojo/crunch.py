"""Self-extracting offline HTML compressor module.

Transforms UTF-8 HTML into self-extracting offline HTML using in-process Zstandard
compression and an embedded Web Worker decoder.
"""

from __future__ import annotations

import argparse
import base64
import codecs
import json
import re
import sys
import tempfile
import zlib
from pathlib import Path
from typing import TYPE_CHECKING

import zstandard as zstd

from .exceptions import (
    CrunchError,
    IncompleteUtf8HtmlError,
    InvalidUtf8HtmlError,
    SameInputOutputError,
    StreamSizeMismatchError,
)

if TYPE_CHECKING:
    from collections.abc import Callable, Iterator
    from typing import BinaryIO

TRANSPORT_BYTES = 256 * 1024
BASE91_ALPHABET = (
    'ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789!#$%&()*+,./:;-=>?@[]^_`{|}~"'
)

_BASE91_THRESHOLD = 88
_BASE91_BITS_THRESHOLD = 13
_BASE91_COUNT_13 = 13
_BASE91_COUNT_14 = 14
_BASE91_MASK_8191 = 8191
_BASE91_MASK_16383 = 16383
_BASE91_TAIL_BITS = 7
_BASE91_TAIL_VALUE = 90

# =============================================================================
# Embedded Browser JavaScript
# =============================================================================

FZSTD_DECODER_CODE = """!function(f){typeof module!='undefined'&&typeof exports=='object'?module.exports=f():typeof define!='undefined'&&define.amd?define(['fzstd',f]):(typeof self!='undefined'?self:this).fzstd=f()}(function(){var _e={};"use strict";var r=ArrayBuffer,t=Uint8Array,e=Uint16Array,n=Int16Array,a=Uint32Array,s=Int32Array,i=function(r,e,n){if(t.prototype.slice)return t.prototype.slice.call(r,e,n);(null==e||e<0)&&(e=0),(null==n||n>r.length)&&(n=r.length);var a=new t(n-e);return a.set(r.subarray(e,n)),a},o=function(r,e,n,a){if(t.prototype.fill)return t.prototype.fill.call(r,e,n,a);for((null==n||n<0)&&(n=0),(null==a||a>r.length)&&(a=r.length);n<a;++n)r[n]=e;return r},u=function(r,e,n,a){if(t.prototype.copyWithin)return t.prototype.copyWithin.call(r,e,n,a);for((null==n||n<0)&&(n=0),(null==a||a>r.length)&&(a=r.length);n<a;)r[e++]=r[n++]};_e.ZstdErrorCode={InvalidData:0,WindowSizeTooLarge:1,InvalidBlockType:2,FSEAccuracyTooHigh:3,DistanceTooFarBack:4,UnexpectedEOF:5};var h=["invalid zstd data","window size too large (>2046MB)","invalid block type","FSE accuracy too high","match distance too far back","unexpected EOF"],f=function(r,t,e){var n=Error(t||h[r]);if(n.code=r,Error.captureStackTrace&&Error.captureStackTrace(n,f),!e)throw n;return n},l=function(r,t,e){for(var n=0,a=0;n<e;++n)a|=r[t++]<<(n<<3);return a},v=function(r,t){return(r[t]|r[t+1]<<8|r[t+2]<<16|r[t+3]<<24)>>>0},c=function(r,e){var n=r[0]|r[1]<<8|r[2]<<16;if(3126568==n&&253==r[3]){var a=r[4],i=a>>5&1,o=a>>2&1,u=3&a,h=a>>6;8&a&&f(0);var c=6-i,b=3==u?4:u,y=l(r,c,b),p=h?1<<h:i,w=l(r,c+=b,p)+(1==h&&256),g=w;if(!i){var d=1<<10+(r[5]>>3);g=d+(d>>3)*(7&r[5])}g>2145386496&&f(1);var m=new t((1==e?w||g:e?0:g)+12);return m[0]=1,m[4]=4,m[8]=8,{b:c+p,y:0,l:0,d:y,w:e&&1!=e?e:m.subarray(12),e:g,o:new s(m.buffer,0,3),u:w,c:o,m:Math.min(131072,g)}}if(25481893==(n>>4|r[3]<<20))return v(r,4)+8;f(0)},b=function(r){for(var t=0;1<<t<=r;++t);return t-1},y=function(a,s,i){var o=4+(s<<3),u=5+(15&a[s]);u>i&&f(3);for(var h=1<<u,l=h,v=-1,c=-1,y=-1,p=h,w=new r(512+(h<<2)),g=new n(w,0,256),d=new e(w,0,256),m=new e(w,512,h),z=512+(h<<1),E=new t(w,z,h),k=new t(w,z+h);v<255&&l>0;){var A=b(l+1),T=o>>3,x=(1<<A+1)-1,F=(a[T]|a[T+1]<<8|a[T+2]<<16)>>(7&o)&x,S=(1<<A)-1,B=x-l-1,I=F&S;if(I<B?(o+=A,F=I):(o+=A+1,F>S&&(F-=B)),g[++v]=--F,-1==F?(l+=F,E[--p]=v):l-=F,!F)do{var U=o>>3;c=(a[U]|a[U+1]<<8)>>(7&o)&3,o+=2,v+=c}while(3==c)}(v>255||l)&&f(0);for(var D=0,M=(h>>1)+(h>>3)+3,W=h-1,O=0;O<=v;++O){var j=g[O];if(j<1)d[O]=-j;else for(y=0;y<j;++y){E[D]=O;do{D=D+M&W}while(D>=p)}}for(D&&f(0),y=0;y<h;++y){var C=d[E[y]]++,H=k[y]=u-b(C);m[y]=(C<<H)-h}return[o+7>>3,{b:u,s:E,n:k,t:m}]},p=function(r,n){var a=0,s=-1,i=new t(292),u=r[n],h=i.subarray(0,256),l=i.subarray(256,268),v=new e(i.buffer,268);if(u<128){var c=y(r,n+1,6),p=c[1],w=c[0]<<3,g=r[n+=u];g||f(0);for(var d=0,m=0,z=p.b,E=z,k=(++n<<3)-8+b(g);!((k-=z)<w);){var A=k>>3;if(h[++s]=p.s[d+=(r[A]|r[A+1]<<8)>>(7&k)&(1<<z)-1],(k-=E)<w)break;h[++s]=p.s[m+=(r[A=k>>3]|r[A+1]<<8)>>(7&k)&(1<<E)-1],z=p.n[d],d=p.t[d],E=p.n[m],m=p.t[m]}++s>255&&f(0)}else{for(s=u-127;a<s;a+=2){var T=r[++n];h[a]=T>>4,h[a+1]=15&T}++n}var x=0;for(a=0;a<s;++a)(I=h[a])>11&&f(0),x+=I&&1<<I-1;var F=b(x)+1,S=1<<F,B=S-x;for(B&B-1&&f(0),h[s++]=b(B)+1,a=0;a<s;++a){var I;++l[h[a]=(I=h[a])&&F+1-I]}var U=new t(S<<1),D=U.subarray(0,S),M=U.subarray(S);for(v[F]=0,a=F;a>0;--a){var W=v[a];o(M,a,W,v[a-1]=W+l[a]*(1<<F-a))}for(v[0]!=S&&f(0),a=0;a<s;++a){var O=h[a];if(O){var j=v[O];o(D,a,j,v[O]=j+(1<<F-O))}}return[n,{n:M,b:F,s:D}]},w=y(new t([81,16,99,140,49,198,24,99,12,33,196,24,99,102,102,134,70,146,4]),0,6)[1],g=y(new t([33,20,196,24,99,140,33,132,16,66,8,33,132,16,66,8,33,68,68,68,68,68,68,68,68,36,9]),0,6)[1],d=y(new t([32,132,16,66,102,70,68,68,68,68,36,73,2]),0,5)[1],m=function(r,t){for(var e=r.length,n=new s(e),a=0;a<e;++a)n[a]=t,t+=1<<r[a];return n},z=new t(new s([0,0,0,0,16843009,50528770,134678020,202050057,269422093]).buffer,0,36),E=m(z,0),k=new t(new s([0,0,0,0,0,0,0,0,16843009,50528770,117769220,185207048,252579084,16]).buffer,0,53),A=m(k,3),T=function(r,t,e){var n=r.length,a=t.length,s=r[n-1],i=(1<<e.b)-1,o=-e.b;s||f(0);for(var u=0,h=e.b,l=(n<<3)-8+b(s)-h,v=-1;l>o&&v<a;){var c=l>>3;t[++v]=e.s[u=(u<<h|(r[c]|r[c+1]<<8|r[c+2]<<16)>>(7&l))&i],l-=h=e.n[u]}l==o&&v+1==a||f(0)},x=function(r,t,e){var n=6,a=t.length+3>>2,s=a<<1,i=a+s;T(r.subarray(n,n+=r[0]|r[1]<<8),t.subarray(0,a),e),T(r.subarray(n,n+=r[2]|r[3]<<8),t.subarray(a,s),e),T(r.subarray(n,n+=r[4]|r[5]<<8),t.subarray(s,i),e),T(r.subarray(n),t.subarray(i),e)},F=function(r,n,a){var s,u=n.b,h=r[u],l=h>>1&3;n.l=1&h;var v=h>>3|r[u+1]<<5|r[u+2]<<13,c=(u+=3)+v;if(1==l){if(u>=r.length)return;return n.b=u+1,a?(o(a,r[u],n.y,n.y+=v),a):o(new t(v),r[u])}if(!(c>r.length)){if(0==l)return n.b=c,a?(a.set(r.subarray(u,c),n.y),n.y+=v,a):i(r,u,c);if(2==l){var m=r[u],F=3&m,S=m>>2&3,B=m>>4,I=0,U=0;F<2?1&S?B|=r[++u]<<4|(2&S&&r[++u]<<12):B=m>>3:(U=S,S<2?(B|=(63&r[++u])<<4,I=r[u]>>6|r[++u]<<2):2==S?(B|=r[++u]<<4|(3&r[++u])<<12,I=r[u]>>2|r[++u]<<6):(B|=r[++u]<<4|(63&r[++u])<<12,I=r[u]>>6|r[++u]<<2|r[++u]<<10)),++u;var D=a?a.subarray(n.y,n.y+n.m):new t(n.m),M=D.length-B;if(0==F)D.set(r.subarray(u,u+=B),M);else if(1==F)o(D,r[u++],M);else{var W=n.h;if(2==F){var O=p(r,u);I+=u-(u=O[0]),n.h=W=O[1]}else W||f(0);(U?x:T)(r.subarray(u,u+=I),D.subarray(M),W)}var j=r[u++];if(j){255==j?j=32512+(r[u++]|r[u++]<<8):j>127&&(j=j-128<<8|r[u++]);var C=r[u++];3&C&&f(0);for(var H=[g,d,w],L=2;L>-1;--L){var Z=C>>2+(L<<1)&3;if(1==Z){var q=new t([0,0,r[u++]]);H[L]={s:q.subarray(2,3),n:q.subarray(0,1),t:new e(q.buffer,0,1),b:0}}else 2==Z?(u=(s=y(r,u,9-(1&L)))[0],H[L]=s[1]):3==Z&&(n.t||f(0),H[L]=n.t[L])}var G=n.t=H,J=G[0],K=G[1],N=G[2],P=r[c-1];P||f(0);var Q=(c<<3)-8+b(P)-N.b,R=Q>>3,V=0,X=(r[R]|r[R+1]<<8)>>(7&Q)&(1<<N.b)-1,Y=(r[R=(Q-=K.b)>>3]|r[R+1]<<8)>>(7&Q)&(1<<K.b)-1,$=(r[R=(Q-=J.b)>>3]|r[R+1]<<8)>>(7&Q)&(1<<J.b)-1;for(++j;--j;){var _=N.s[X],rr=N.n[X],tr=J.s[$],er=J.n[$],nr=K.s[Y],ar=K.n[Y],sr=1<<nr,ir=sr+((r[R=(Q-=nr)>>3]|r[R+1]<<8|r[R+2]<<16|r[R+3]<<24)>>>(7&Q)&sr-1);R=(Q-=k[tr])>>3;var or=A[tr]+((r[R]|r[R+1]<<8|r[R+2]<<16)>>(7&Q)&(1<<k[tr])-1);R=(Q-=z[_])>>3;var ur=E[_]+((r[R]|r[R+1]<<8|r[R+2]<<16)>>(7&Q)&(1<<z[_])-1);if(R=(Q-=rr)>>3,X=N.t[X]+((r[R]|r[R+1]<<8)>>(7&Q)&(1<<rr)-1),R=(Q-=er)>>3,$=J.t[$]+((r[R]|r[R+1]<<8)>>(7&Q)&(1<<er)-1),R=(Q-=ar)>>3,Y=K.t[Y]+((r[R]|r[R+1]<<8)>>(7&Q)&(1<<ar)-1),ir>3)n.o[2]=n.o[1],n.o[1]=n.o[0],n.o[0]=ir-=3;else{var hr=ir-(0!=ur);hr?(ir=3==hr?n.o[0]-1:n.o[hr],hr>1&&(n.o[2]=n.o[1]),n.o[1]=n.o[0],n.o[0]=ir):ir=n.o[0]}for(L=0;L<ur;++L)D[V+L]=D[M+L];M+=ur;var fr=(V+=ur)-ir;if(fr<0){var lr=-fr,vr=n.e+fr;for(lr>or&&(lr=or),L=0;L<lr;++L)D[V+L]=n.w[vr+L];V+=lr,or-=lr,fr=0}for(L=0;L<or;++L)D[V+L]=D[fr+L];V+=or}if(V!=M)for(;M<D.length;)D[V++]=D[M++];else V=D.length;a?n.y+=V:D=i(D,0,V)}else if(a){if(n.y+=B,M)for(L=0;L<B;++L)D[L]=D[M+L]}else M&&(D=i(D,M));return n.b=c,D}f(2)}},S=function(r,e){if(1==r.length)return r[0];for(var n=new t(e),a=0,s=0;a<r.length;++a){var i=r[a];n.set(i,s),s+=i.length}return n};function B(r,t){for(var e=[],n=+!t,a=0,s=0;r.length;){var i=c(r,n||t);if("object"==typeof i){for(n?(t=null,i.w.length==i.u&&(e.push(t=i.w),s+=i.u)):(e.push(t),i.e=0);!i.l;){var o=F(r,i,t);o||f(5),t?i.e=i.y:(e.push(o),s+=o.length,u(i.w,0,o.length),i.w.set(o,i.w.length-o.length))}a=i.b+4*i.c}else a=i;r=r.subarray(a)}return S(e,s)}_e.decompress=B;var I=function(){function r(r){this.ondata=r,this.c=[],this.l=0,this.z=0}return r.prototype.push=function(r,e){if("number"==typeof this.s){var n=Math.min(r.length,this.s);r=r.subarray(n),this.s-=n}var a=r.length+this.l;if(!this.s){if(e){if(!a)return void this.ondata(new t(0),!0);a<5&&f(5)}else if(a<18)return this.c.push(r),void(this.l=a);if(this.l&&(this.c.push(r),r=S(this.c,a),this.c=[],this.l=0),"number"==typeof(this.s=c(r)))return this.push(r,e)}if("number"!=typeof this.s){if(a<(this.z||3))return e&&f(5),this.c.push(r),void(this.l=a);if(this.l&&(this.c.push(r),r=S(this.c,a),this.c=[],this.l=0),!this.z&&a<(this.z=2&r[this.s.b]?4:3+(r[this.s.b]>>3|r[this.s.b+1]<<5|r[this.s.b+2]<<13)))return e&&f(5),this.c.push(r),void(this.l=a);for(this.z=0;;){var s=F(r,this.s);if(!s){e&&f(5);var i=r.subarray(this.s.b);return this.s.b=0,this.c.push(i),void(this.l+=i.length)}if(this.ondata(s,!1),u(this.s.w,0,s.length),this.s.w.set(s,this.s.w.length-s.length),this.s.l){var o=r.subarray(this.s.b);return this.s=4*this.s.c,void this.push(o,e)}}}else e&&f(5)},r}();_e.Decompress=I;return _e});"""

JS_SHARED = """
function decodeBase91(encoded, expectedLength) {
  if (!Number.isSafeInteger(expectedLength) || expectedLength < 0) {
    throw new Error('Invalid decoded payload length');
  }
  if (encoded.length > Math.ceil(expectedLength * 16 / 13) + 1 ||
      (expectedLength && !encoded.length)) {
    throw new Error('Invalid Base91 payload length');
  }
  const alphabet = BASE91_ALPHABET;
  const table = new Int16Array(128);
  table.fill(-1);
  for (let index = 0; index < alphabet.length; ++index) {
    table[alphabet.charCodeAt(index)] = index;
  }
  const output = new Uint8Array(expectedLength);
  let accumulator = 0;
  let bits = 0;
  let pending = -1;
  let offset = 0;
  let lastValue = 0;
  let lastBits = 0;
  for (let index = 0; index < encoded.length; ++index) {
    const code = encoded.charCodeAt(index);
    const value = code < 128 ? table[code] : -1;
    if (value < 0) throw new Error('Invalid Base91 payload character');
    if (pending < 0) {
      pending = value;
      continue;
    }
    pending += value * 91;
    lastValue = pending;
    lastBits = (pending & 8191) > 88 ? 13 : 14;
    accumulator |= pending << bits;
    bits += lastBits;
    while (bits > 7) {
      if (offset === output.length) throw new Error('Base91 payload exceeds its declared length');
      output[offset++] = accumulator & 255;
      accumulator >>>= 8;
      bits -= 8;
    }
    pending = -1;
  }
  if (pending >= 0) {
    if (!bits || pending >= (1 << (8 - bits))) throw new Error('Invalid Base91 payload tail');
    if (offset === output.length) throw new Error('Base91 payload exceeds its declared length');
    output[offset++] = accumulator | (pending << bits);
  } else if (accumulator || (encoded.length && lastBits - bits <= 7 && lastValue <= 90)) {
    throw new Error('Invalid Base91 payload tail');
  }
  if (offset !== expectedLength) throw new Error('Base91 payload is truncated');
  return output;
}

function crc32(bytes) {
  const table = crc32.table || (crc32.table = Uint32Array.from({ length: 256 }, (_, value) => {
    for (let bit = 0; bit < 8; ++bit) value = (value >>> 1) ^ (0xedb88320 & -(value & 1));
    return value >>> 0;
  }));
  let crc = 0xffffffff;
  for (let index = 0; index < bytes.length; ++index) {
    crc = (crc >>> 8) ^ table[(crc ^ bytes[index]) & 255];
  }
  return (crc ^ 0xffffffff) >>> 0;
}
"""

JS_WORKER_MAIN = """
function workerMain() {
  let reply;
  const ask = (type, data = {}, transfer = []) => new Promise(resolve => {
    reply = resolve;
    self.postMessage({ type, ...data }, transfer);
  });
  self.onmessage = event => {
    if (reply) {
      const resolve = reply;
      reply = null;
      resolve(event.data);
    } else if (event.data.type === 'start') {
      run(event.data.meta).catch(error => self.postMessage({ type: 'error', message: error.message }));
    }
  };
  async function run(meta) {
    let input = new Uint8Array(0), offset = 0, received = 0, chunks = 0, decoded = 0;
    async function read(length) {
      const result = new Uint8Array(length);
      let filled = 0;
      while (filled < length) {
        if (offset === input.length) {
          const message = await ask('input');
          if (message.type !== 'input' || !message.text) throw new Error('Truncated compressed HTML.');
          const expected = Math.min(TRANSPORT_BYTES, meta.compressed - received);
          if (expected <= 0 || ++chunks > meta.chunks) throw new Error('Unexpected extra payload.');
          input = decodeBase91(message.text, expected);
          if (crc32(input) !== message.crc) throw new Error('Payload checksum mismatch. The file may be damaged.');
          offset = 0;
          received += input.length;
        }
        const count = Math.min(length - filled, input.length - offset);
        result.set(input.subarray(offset, offset + count), filled);
        filled += count;
        offset += count;
      }
      return result;
    }
    if (!self.fzstd || typeof self.fzstd.Decompress !== 'function') throw new Error('The embedded fzstd decoder is unavailable.');
    const header = await read(6);
    if (header[0] !== 40 || header[1] !== 181 || header[2] !== 47 || header[3] !== 253 ||
        (header[4] & ~4) !== 0) throw new Error('Unsupported Zstd frame header.');
    const windowBase = 2 ** (10 + (header[5] >>> 3));
    const windowSize = windowBase + windowBase / 8 * (header[5] & 7);
    if (windowSize > 2 ** meta.windowLog || windowSize > 2 ** 27) throw new Error('Zstd decoder window exceeds the configured limit.');
    let output = [];
    const decoder = new self.fzstd.Decompress(bytes => {
      if (bytes.length > 131072) throw new Error('Oversized Zstd block.');
      decoded += bytes.length;
      if (decoded > meta.size) throw new Error('Decoded HTML exceeds its declared size.');
      if (bytes.length) output.push(bytes.byteOffset === 0 && bytes.byteLength === bytes.buffer.byteLength ? bytes : bytes.slice());
    });
    async function drain() {
      if (!output.length) return;
      const batch = output;
      output = [];
      if (batch.length > 4) throw new Error('Unexpected decoder output batch.');
      const buffers = batch.map(bytes => bytes.buffer);
      const answer = await ask('output', { buffers }, buffers);
      if (answer.type !== 'ack') throw new Error('Invalid decoder acknowledgment.');
    }
    decoder.push(header, false);
    let last = false;
    while (!last) {
      const blockHeader = await read(3);
      const bits = blockHeader[0] | (blockHeader[1] << 8) | (blockHeader[2] << 16);
      last = !!(bits & 1);
      const type = (bits >>> 1) & 3;
      const size = bits >>> 3;
      if (type === 3 || size > Math.min(131072, windowSize)) throw new Error('Invalid Zstd block header.');
      const body = await read(type === 1 ? 1 : size);
      const block = new Uint8Array(3 + body.length);
      block.set(blockHeader);
      block.set(body, 3);
      decoder.push(block, false);
      await drain();
    }
    decoder.push(await read(header[4] & 4 ? 4 : 0), true);
    await drain();
    if (offset !== input.length || received !== meta.compressed || chunks !== meta.chunks || decoded !== meta.size) {
      throw new Error('Compressed HTML is truncated or has an incorrect length.');
    }
    self.postMessage({ type: 'done' });
  }
}
"""

JS_BROWSER_MAIN = """
function browserMain(meta, workerCode) {
  let worker, workerURL, finished = false, at = 0;
  let payload = Array.from(document.querySelectorAll('script[data-crunch]'));
  const decoder = new TextDecoder('utf-8', { fatal: true });
  const open = document.open.bind(document);
  const write = document.write.bind(document);
  const close = document.close.bind(document);
  const schedule = setTimeout.bind(globalThis);
  const later = globalThis.scheduler?.yield ? globalThis.scheduler.yield.bind(globalThis.scheduler) :
    () => new Promise(resolve => schedule(resolve, 0));

  const chunks = [];

  const release = () => {
    worker?.terminate();
    if (workerURL) URL.revokeObjectURL(workerURL);
    for (const element of payload) if (element) { element.textContent = ''; element.remove(); }
    payload = [];
  };

  const fail = error => {
    if (finished) return;
    finished = true;
    release();
    const message = document.createElement('pre');
    message.style.cssText = 'position:relative;z-index:999999;white-space:pre-wrap;padding:1rem;background:#fff;color:#a00';
    message.textContent = 'Unable to open compressed HTML: ' + error.message;
    (document.body || document.documentElement).append(message);
    const status = document.getElementById('crunch-status');
    if (status) status.textContent = 'Loading failed.';
    const spinner = document.querySelector('.spinner');
    if (spinner) spinner.style.display = 'none';
    console.error(error);
  };

  async function handle(message) {
    if (finished) return;

    if (message.type === 'input') {
      const element = payload[at];
      if (!element) throw new Error('Missing payload chunk.');
      const [index, checksum] = element.dataset.crunch.split(':');
      if (index !== at.toString(36)) throw new Error('Payload chunks are out of order.');
      const text = element.textContent;
      const crc = Number.parseInt(checksum, 16);
      payload[at++] = null;
      element.textContent = '';
      element.remove();
      worker.postMessage({ type: 'input', text, crc });

    } else if (message.type === 'output') {
      for (const buffer of message.buffers) {
        chunks.push(new Uint8Array(buffer));
      }
      worker.postMessage({ type: 'ack' });

    } else if (message.type === 'done') {
      if (at !== payload.length) throw new Error('Unconsumed payload chunks.');

      open();
      window.addEventListener('pagehide', release, { once: true });
      write('<!DOCTYPE html>');

      let chunkStart = performance.now();
      for (const bytes of chunks) {
        const text = decoder.decode(bytes, { stream: true });
        if (text) write(text);
        if (performance.now() - chunkStart > 16) {
          await later();
          chunkStart = performance.now();
        }
      }

      const tail = decoder.decode();
      if (tail) write(tail);

      finished = true;
      release();
      close();

    } else if (message.type === 'error') {
      throw new Error(message.message);
    }
  }

  try {
    if (payload.length !== meta.chunks) throw new Error('The compressed file is incomplete.');
    workerURL = URL.createObjectURL(new Blob([workerCode], { type: 'text/javascript' }));
    workerCode = null;
    worker = new Worker(workerURL);
    worker.onmessage = event => { handle(event.data).catch(fail); };
    worker.onerror = event => { event.preventDefault(); fail(new Error(event.message || 'Worker could not start.')); };
    worker.onmessageerror = () => fail(new Error('Could not receive decoder output.'));
    worker.postMessage({ type: 'start', meta });
  } catch (error) { fail(error); }
}
"""


def strip_js_formatting(js_code: str) -> str:
    """Remove leading whitespace and full-line comments for smaller payload injection."""
    code = re.sub(r"^\s*//[^\n]*\n", "", js_code, flags=re.MULTILINE)
    code = re.sub(r"^[ \t]+", "", code, flags=re.MULTILINE)
    return code.strip()


def encode_base91(data: bytes) -> str:
    """Encode binary bytes into chunked Base91 ASCII string."""
    alphabet = BASE91_ALPHABET
    output: list[str] = []
    append = output.append

    accumulator = 0
    bits = 0
    for byte in data:
        accumulator |= byte << bits
        bits += 8
        if bits > _BASE91_BITS_THRESHOLD:
            val = accumulator & _BASE91_MASK_8191
            count = _BASE91_COUNT_13
            if val <= _BASE91_THRESHOLD:
                val = accumulator & _BASE91_MASK_16383
                count = _BASE91_COUNT_14
            accumulator >>= count
            bits -= count
            append(alphabet[val % 91])
            append(alphabet[val // 91])

    if bits:
        append(alphabet[accumulator % 91])
        if bits > _BASE91_TAIL_BITS or accumulator > _BASE91_TAIL_VALUE:
            append(alphabet[accumulator // 91])

    return "".join(output)


def make_header() -> bytes:
    """Generate the initial HTML header displaying a lightweight loading spinner."""
    return (
        b'<!doctype html><html><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        b"<title>Loading HTML...</title><style>"
        b"body{margin:0;background:#1a1a1a}"
        b"#crunch-loader{position:fixed;top:0;left:0;right:0;bottom:0;display:flex;align-items:center;justify-content:center;padding-top:80px;color:#eee;font:16px system-ui}"
        b".spinner{position:fixed;top:calc(50% - 40px);left:calc(50% - 20px);width:40px;height:40px;border:4px solid rgba(255,255,255,0.2);border-top-color:#fff;border-radius:50%;animation:spin 1s linear infinite}"
        b"@keyframes spin{to{transform:rotate(360deg)}}"
        b"</style></head><body>"
        b'<div id="crunch-loader"><div class="spinner"></div><p id="crunch-status">Decompressing HTML...</p>'
        b"<noscript><p>JavaScript is required to open this file.</p></noscript></div>\n"
    )


def make_footer(meta: dict[str, int]) -> bytes:
    """Generate the runtime script and self-extracting bootstrap footer."""
    worker_code = (
        f"{FZSTD_DECODER_CODE}\n"
        f"const BASE91_ALPHABET={json.dumps(BASE91_ALPHABET)},TRANSPORT_BYTES={TRANSPORT_BYTES};\n"
        f"{strip_js_formatting(JS_SHARED)}\n"
        f"{strip_js_formatting(JS_WORKER_MAIN)}\n"
        "workerMain();"
    )

    runtime_js = (
        f"({strip_js_formatting(JS_BROWSER_MAIN)})({json.dumps(meta)},{json.dumps(worker_code)});"
    )
    encoded = base64.b64encode(zlib.compress(runtime_js.encode("utf-8"), level=9)).decode("ascii")

    footer_text = (
        "<script>document.addEventListener('DOMContentLoaded',()=>setTimeout(async()=>{try{"
        "if(!globalThis.DecompressionStream||!globalThis.Worker)throw Error('This file requires a modern browser with Workers and DecompressionStream.');"
        f"const b=Uint8Array.from(atob('{encoded}'),c=>c.charCodeAt(0)),s=document.createElement('script');"
        "s.textContent=await new Response(new Blob([b]).stream().pipeThrough(new DecompressionStream('deflate'))).text();"
        "document.head.append(s);s.remove()"
        "}catch(e){document.getElementById('crunch-status').textContent='Unable to open compressed HTML: '+e.message;console.error(e)}},0),{once:true})</script></body></html>"
    )
    return footer_text.encode("ascii")


def chunked_reader(file_obj: BinaryIO, chunk_size: int = 65536) -> Iterator[bytes]:
    """Yield chunks from a binary stream."""
    while True:
        chunk = file_obj.read(chunk_size)
        if not chunk:
            break
        yield chunk


def base36_encode(number: int) -> str:
    """Format an integer as base36 string."""
    if number == 0:
        return "0"
    alphabet = "0123456789abcdefghijklmnopqrstuvwxyz"
    base36 = ""
    while number:
        number, i = divmod(number, 36)
        base36 = alphabet[i] + base36
    return base36


class _ChunkBuffer:
    """Buffers compressed bytes into fixed TRANSPORT_BYTES chunks."""

    def __init__(self, emit_fn: Callable[[memoryview], bytes]) -> None:
        self.pending = bytearray(TRANSPORT_BYTES)
        self.length = 0
        self.emit_fn = emit_fn

    def feed(self, data: bytes) -> Iterator[bytes]:
        offset = 0
        while offset < len(data):
            count = min(TRANSPORT_BYTES - self.length, len(data) - offset)
            self.pending[self.length : self.length + count] = data[offset : offset + count]
            self.length += count
            offset += count
            if self.length == TRANSPORT_BYTES:
                yield self.emit_fn(memoryview(self.pending))
                self.length = 0

    def flush(self) -> Iterator[bytes]:
        if self.length > 0:
            yield self.emit_fn(memoryview(self.pending)[: self.length])
            self.length = 0


def generate_payloads(
    input_stream: BinaryIO,
    level: int = 22,
    window_log: int = 26,
    expected_size: int | None = None,
) -> Iterator[bytes]:
    """Yield compressed HTML byte chunks in streaming fashion.

    Args:
        input_stream: Binary input stream containing UTF-8 HTML.
        level: Zstandard compression level (1-22).
        window_log: Decoder window log size (10-27).
        expected_size: Optional expected byte count for integrity check.

    Yields:
        Byte chunks of the self-extracting HTML document.

    Raises:
        InvalidUtf8HtmlError: If input contains invalid UTF-8 data.
        IncompleteUtf8HtmlError: If input ends with incomplete UTF-8 bytes.
        StreamSizeMismatchError: If stream size differs from expected_size.

    """
    utf8_decoder = codecs.getincrementaldecoder("utf-8")("strict")

    params = zstd.ZstdCompressionParameters.from_level(
        level,
        window_log=window_log,
        threads=-1,
    )
    cctx = zstd.ZstdCompressor(compression_params=params)

    stats = {"size": 0, "compressed": 0, "chunks": 0, "windowLog": window_log}

    def emit_chunk(data: memoryview) -> bytes:
        index = stats["chunks"]
        stats["chunks"] += 1
        stats["compressed"] += len(data)
        crc = zlib.crc32(data) & 0xFFFFFFFF
        b91 = encode_base91(bytes(data))

        header = f'<script type="application/octet-stream" data-crunch="{base36_encode(index)}:{crc:x}">'.encode(
            "ascii"
        )
        return header + b91.encode("ascii") + b"</script>\n"

    buffer = _ChunkBuffer(emit_chunk)
    yield make_header()

    comp_obj = cctx.compressobj()

    for chunk in chunked_reader(input_stream):
        try:
            utf8_decoder.decode(chunk, final=False)
        except UnicodeDecodeError as err:
            raise InvalidUtf8HtmlError from err

        stats["size"] += len(chunk)
        compressed = comp_obj.compress(chunk)
        if compressed:
            yield from buffer.feed(compressed)

    try:
        utf8_decoder.decode(b"", final=True)
    except UnicodeDecodeError as err:
        raise IncompleteUtf8HtmlError from err

    final_compressed = comp_obj.flush()
    if final_compressed:
        yield from buffer.feed(final_compressed)

    yield from buffer.flush()

    if expected_size is not None and stats["size"] != expected_size:
        raise StreamSizeMismatchError

    yield make_footer(stats)


def _write_output_chunks(
    in_stream: BinaryIO,
    output_str: str,
    input_size: int | None,
    level: int,
    window_log: int,
) -> None:
    """Stream compressed payload chunks to stdout or atomically to a file."""
    if output_str == "-":
        for out_chunk in generate_payloads(
            in_stream, level=level, window_log=window_log, expected_size=input_size
        ):
            sys.stdout.buffer.write(out_chunk)
        sys.stdout.buffer.flush()
        return

    out_dir = Path(output_str).parent
    out_dir.mkdir(parents=True, exist_ok=True)

    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=out_dir, prefix=".crunch-html-", suffix=".tmp", delete=False
        ) as tf:
            temp_path = Path(tf.name)
            for out_chunk in generate_payloads(
                in_stream, level=level, window_log=window_log, expected_size=input_size
            ):
                tf.write(out_chunk)
        temp_path.replace(output_str)
        temp_path = None
    finally:
        if temp_path is not None and temp_path.exists():
            temp_path.unlink()


def crunch_file(
    input_target: str | Path | None = None,
    output_target: str | Path | None = None,
    level: int = 22,
    window_log: int = 26,
) -> None:
    """Compress HTML file or stdin to self-extracting HTML file or stdout.

    Args:
        input_target: Path to input HTML file, or None / '-' for stdin.
        output_target: Path to output HTML file, or None / '-' for stdout.
        level: Zstandard compression level (1-22).
        window_log: Window log size (10-27).

    Raises:
        SameInputOutputError: If input and output refer to the same file.
        FileNotFoundError: If input file does not exist.

    """
    input_str = str(input_target) if input_target is not None else "-"
    output_str = str(output_target) if output_target is not None else "-"

    if (
        output_str != "-"
        and input_str != "-"
        and Path(output_str).resolve() == Path(input_str).resolve()
    ):
        raise SameInputOutputError

    if input_str != "-":
        input_path = Path(input_str).resolve()
        if not input_path.is_file():
            msg = f"Input '{input_str}' must be a regular file."
            raise FileNotFoundError(msg)
        input_size = input_path.stat().st_size
        with input_path.open("rb") as f:
            _write_output_chunks(f, output_str, input_size, level, window_log)
    else:
        _write_output_chunks(sys.stdin.buffer, output_str, None, level, window_log)


def main(argv: list[str] | None = None) -> None:
    """CLI entrypoint for standalone crunch execution or 'python -m dojo.crunch'."""
    parser = argparse.ArgumentParser(
        prog="crunch",
        description="Stream UTF-8 HTML into self-extracting offline HTML",
        formatter_class=argparse.RawTextHelpFormatter,
        epilog=(
            'Input defaults to stdin; an explicit "-" is accepted. Output files are replaced\n'
            "atomically only after successful compression. Do not redirect stdout over input.\n\n"
            "The default is maximum compression (--level 22 --window-log 26) with multi-threading.\n"
            "Output includes its self-contained decoder and needs no external dependencies or CDN."
        ),
    )

    parser.add_argument("input", nargs="?", default="-", help='Input file ("-" for stdin)')
    parser.add_argument(
        "output_pos",
        nargs="?",
        default=argparse.SUPPRESS,
        help="Output file (positional backward compat)",
    )
    parser.add_argument(
        "-o", "--output", help='Output file (default: stdout; "-" also means stdout)'
    )
    parser.add_argument(
        "-l",
        "--level",
        type=int,
        default=22,
        choices=range(1, 23),
        metavar="1-22",
        help="Zstd level (default: 22)",
    )
    parser.add_argument(
        "--window-log",
        type=int,
        default=26,
        choices=range(10, 28),
        metavar="10-27",
        help="Decoder history: 2^N bytes (default: 26 = 64 MiB)",
    )

    args = parser.parse_args(argv)

    output_target = getattr(args, "output_pos", args.output) if args.output is None else args.output
    if output_target is None:
        output_target = "-"

    if args.input == "-" and sys.stdin.isatty():
        parser.error("Specify input HTML or pipe it on stdin. Run with --help for usage.")

    try:
        crunch_file(args.input, output_target, level=args.level, window_log=args.window_log)
    except (CrunchError, ValueError, OSError, RuntimeError) as e:
        sys.exit(f"Error: {e}")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        sys.exit(130)
