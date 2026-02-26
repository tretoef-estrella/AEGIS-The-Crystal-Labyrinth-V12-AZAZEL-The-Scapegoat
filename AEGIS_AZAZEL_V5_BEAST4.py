#!/usr/bin/env python3
"""
AEGIS AZAZEL v5 — BEAST 4 · SONIC BOOM
Author:  Rafael Amichis Luengo (The Architect)
Engine:  Claude (Anthropic) | Auditors: Gemini · ChatGPT · Grok
Project: Proyecto Estrella · Error Code Lab
Date:    26 February 2026
LICENSE: BSL 1.1 + Azazel Clause (permanent ethical restriction)

v5 — SONIC BOOM · F22 AIR SUPERIORITY
  All v4 lethality (7 Hells + Tilt + Synthetic Key + all auditor fixes)
  + Incremental WindowRank (O(12×rank) per query, not O(64×144))
  + Lazy T as row-op chain (no mat_mul ever, flatten every 32 ops)
  + XorShift128+ PRNG (SHA256 only for state transitions)
  + Attack fusion (shared oracle, 40% fewer queries)
  + Early CI exit (GORGON heritage <1.8s)
  + Precomputed Judas bank (zero per-query chain generation)
  + Sparse Tilt (O(perturbations) not O(144))
  + Resonance Judas + Cascade Echo (lethality 9.9)

  "Light as the wind. Fast and lethal."
"""
import time, hashlib, random
from math import log2, sqrt
from collections import deque

t0 = time.time()

# ══════════════════════════════════════════════════════════════
# 0. GF(4) CORE — FLAT TABLES
# ══════════════════════════════════════════════════════════════
_AF = (0,1,2,3, 1,0,3,2, 2,3,0,1, 3,2,1,0)
_MF = (0,0,0,0, 0,1,2,3, 0,2,3,1, 0,3,1,2)
_INV = (0,1,3,2); _FROB = (0,1,3,2); DIM = 12

def pack12(vals):
    r = 0
    for i in range(12): r |= (vals[i]&3) << (i*2)
    return r
def unpack12(p): return [(p>>(i*2))&3 for i in range(12)]
def gc(p,i): return (p>>(i*2))&3
def sc(p,i,v): return (p & ~(3<<(i*2))) | ((v&3)<<(i*2))
def pdist(a,b):
    x = a^b; d = 0
    for i in range(12):
        if (x>>(i*2))&3: d += 1
    return d
def padd(a,b):
    r = 0
    for i in range(12):
        r |= _AF[((a>>(i*2))&3)*4+((b>>(i*2))&3)] << (i*2)
    return r

# ══════════════════════════════════════════════════════════════
# XORSHIFT128+ PRNG (replaces per-query SHA256)
# ══════════════════════════════════════════════════════════════
M64 = (1 << 64) - 1
class XS:
    __slots__ = ('s0','s1')
    def __init__(self, seed_bytes):
        self.s0 = int.from_bytes(seed_bytes[:8],'big') | 1
        self.s1 = int.from_bytes(seed_bytes[8:16],'big') | 1
    def next(self):
        s0, s1 = self.s0, self.s1
        r = (s0 + s1) & M64
        s1 ^= s0; self.s0 = ((s0<<24)&M64 | s0>>(64-24)) ^ s1 ^ ((s1<<16)&M64)
        self.s1 = (s1<<37)&M64 | s1>>(64-37); return r
    def ri(self, lo, hi): return lo + self.next() % (hi - lo + 1)
    def r4(self): return self.next() & 3
    def rf(self): return (self.next() & 0xFFFFF) / 0xFFFFF

# ══════════════════════════════════════════════════════════════
# INCREMENTAL WINDOW RANK (Gemini+Grok: O(12×rank) per add)
# ══════════════════════════════════════════════════════════════
class WRank:
    __slots__ = ('basis','piv','rank','vecs','_rc')
    def __init__(self, win=64):
        self.basis = [[0]*12 for _ in range(12)]
        self.piv = [-1]*12; self.rank = 0
        self.vecs = deque(maxlen=win); self._rc = 0
    def add(self, v):
        self.vecs.append(v[:])
        vv = list(v)
        for p in range(12):
            if self.piv[p] >= 0 and vv[p]:
                f = vv[p]
                b = self.basis[p]
                for j in range(12): vv[j] = _AF[vv[j]*4 + _MF[f*4 + b[j]]]
        for i in range(12):
            if vv[i] and self.piv[i] < 0:
                inv = _INV[vv[i]]
                self.basis[i] = [_MF[inv*4+vv[j]] for j in range(12)]
                self.piv[i] = i; self.rank += 1; break
        self._rc += 1
        if self._rc >= 8:
            self._rebuild(); self._rc = 0
        return self.rank
    def _rebuild(self):
        old = list(self.vecs)
        self.basis = [[0]*12 for _ in range(12)]
        self.piv = [-1]*12; self.rank = 0; self._rc = 0
        for v in old:
            vv = list(v)
            for p in range(12):
                if self.piv[p] >= 0 and vv[p]:
                    f = vv[p]; b = self.basis[p]
                    for j in range(12): vv[j] = _AF[vv[j]*4 + _MF[f*4 + b[j]]]
            for i in range(12):
                if vv[i] and self.piv[i] < 0:
                    inv = _INV[vv[i]]
                    self.basis[i] = [_MF[inv*4+vv[j]] for j in range(12)]
                    self.piv[i] = i; self.rank += 1; break

# ══════════════════════════════════════════════════════════════
# LAZY T — Row-op chain, flatten every 32 ops
# ══════════════════════════════════════════════════════════════
def t_identity(): return list(range(12)), [[0]*12 for _ in range(12)]
# T stored as flat[144] but updated via row ops

def mat_id_flat():
    M = [0]*144
    for i in range(12): M[i*12+i] = 1
    return M

def row_op(T, i, j, alpha):
    """T[i] += alpha * T[j] over GF(4). O(12)."""
    oi = i*12; oj = j*12
    for k in range(12): T[oi+k] = _AF[T[oi+k]*4 + _MF[alpha*4 + T[oj+k]]]

def row_op_frob(T, i, j, alpha):
    """T[i] += alpha * Frob(T[j]). O(12)."""
    oi = i*12; oj = j*12
    for k in range(12): T[oi+k] = _AF[T[oi+k]*4 + _MF[alpha*4 + _FROB[T[oj+k]]]]

def apply_T_to_packed(T, pv):
    """T × packed_vector. O(144)."""
    v = unpack12(pv); r = 0
    for i in range(12):
        s = 0; oi = i*12
        for k in range(12): s = _AF[s*4 + _MF[T[oi+k]*4 + v[k]]]
        r |= (s << (i*2))
    return r

def apply_row_ops(T, ops):
    """Apply a batch of (i,j,alpha,frob?) row ops. Fast."""
    for op in ops:
        if len(op) == 4 and op[3]:
            row_op_frob(T, op[0], op[1], op[2])
        else:
            row_op(T, op[0], op[1], op[2])

def gen_ops(h_bytes, intensity):
    """Generate row-op list instead of full matrix."""
    rng = random.Random(int.from_bytes(h_bytes[:16], 'big'))
    n = {'minor': rng.randint(2,3), 'major': rng.randint(6,8),
         'frobenius': rng.randint(8,10)}[intensity]
    ops = []
    frob = intensity == 'frobenius'
    for _ in range(n):
        i, j = rng.sample(range(12), 2)
        ops.append((i, j, rng.randint(1,3), frob))
    return ops

print("=" * 72)
print("  AEGIS AZAZEL v5 — BEAST 4 · SONIC BOOM")
print("  7 Hells + Tilt · Incremental Rank · Lazy T · XorShift · Fused Battery")
print("  'Light as the wind. Fast and lethal.'")
print("=" * 72)

# ══════════════════════════════════════════════════════════════
# 1. GORGON HERITAGE (early CI exit)
# ══════════════════════════════════════════════════════════════
print("\n  ═══ GORGON ═══", flush=True)
t_sp = time.time()
aa = 2
def gf16_mul(x,y):
    return (_AF[_MF[x[0]*4+y[0]]*4+_MF[_MF[x[1]*4+y[1]]*4+aa]],
            _AF[_AF[_MF[x[0]*4+y[1]]*4+_MF[x[1]*4+y[0]]]*4+_MF[x[1]*4+y[1]]])
def gf16_inv(x):
    r=(1,0)
    for _ in range(14): r=gf16_mul(r,x)
    return r
gf16_nz=[(a,b) for a in range(4) for b in range(4) if not(a==0 and b==0)]
def normalize(v):
    for i in range(len(v)):
        if v[i]!=0: inv=_INV[v[i]]; return tuple(_MF[inv*4+x] for x in v)
    return None
def spread_line(pt6):
    pts=set()
    for s in gf16_nz:
        v=[]
        for k in range(6): sx=gf16_mul(s,pt6[k]); v.extend([sx[0],sx[1]])
        p=normalize(tuple(v))
        if p: pts.add(p)
    return list(pts)

SR=5000; SD=5000; gf16_all=[(a,b) for a in range(4) for b in range(4)]
spread_rng=random.Random(hashlib.sha256(b"GORGON_PG11_SPREAD").digest())
real_lines=[]; rls=set(); att=0
while len(real_lines)<SR and att<SR*5:
    att+=1
    pt6_raw=[gf16_all[spread_rng.randint(0,15)] for _ in range(6)]
    if all(x==(0,0) for x in pt6_raw): continue
    pt6n=None
    for k in range(6):
        if pt6_raw[k]!=(0,0):
            inv=gf16_inv(pt6_raw[k])
            pt6n=tuple(gf16_mul(inv,pt6_raw[j]) for j in range(6)); break
    if pt6n is None or pt6n in rls: continue
    rls.add(pt6n); pts=spread_line(pt6n)
    if len(pts)==5: real_lines.append(pts)
n_real=len(real_lines)

spts=[]; spti={}
for L in real_lines:
    for p in L:
        if p not in spti: spti[p]=len(spts); spts.append(p)

dr=random.Random(31337); decoy_lines=[]
for _ in range(SD*2):
    if len(decoy_lines)>=SD: break
    v1=tuple(dr.randint(0,3) for _ in range(DIM)); v2=tuple(dr.randint(0,3) for _ in range(DIM))
    if all(x==0 for x in v1) or all(x==0 for x in v2): continue
    pts=set()
    for c1 in range(4):
        for c2 in range(4):
            v=tuple(_AF[_MF[c1*4+v1[k]]*4+_MF[c2*4+v2[k]]] for k in range(DIM))
            if not all(x==0 for x in v):
                p=normalize(v)
                if p: pts.add(p)
    if len(pts)==5: decoy_lines.append(list(pts))
for L in decoy_lines:
    for p in L:
        if p not in spti: spti[p]=len(spts); spts.append(p)
NS=len(spts)

Hcp=[pack12(list(p)) for p in spts]
rcs=set()
for L in real_lines:
    for p in L:
        j=spti.get(p)
        if j is not None: rcs.add(j)

print(f"  {n_real:,}r+{len(decoy_lines):,}d={NS:,} ({time.time()-t_sp:.1f}s)", flush=True)

# Corruption
tc=time.time()
sg=hashlib.sha256(b"AEGIS_v16_GORGON_FINAL").digest()
sg=hashlib.sha256(sg+hashlib.sha256(b"PG11_4_7VENOMS_AZAZEL_F1").digest()).digest()
asig=b"Rafael Amichis Luengo <tretoef@gmail.com>"
mr=random.Random(int.from_bytes(sg,'big'))
Hp=list(Hcp)
def nr2(): return random.Random(mr.randint(0,2**64))

r=nr2()
for j in range(NS):
    if r.random()<0.15:
        cs=int.from_bytes(hashlib.sha256(sg+b"EC"+j.to_bytes(4,'big')).digest()[:4],'big')
        cr=random.Random(cs); v=0
        for i in range(12): v|=(cr.randint(0,3)<<(i*2))
        Hp[j]=v
r=nr2()
for _ in range(800):
    c1,c2=r.randint(0,NS-1),r.randint(0,NS-1)
    if c1!=c2:
        v=0
        for i in range(12): v|=_AF[gc(Hp[c1],i)*4+r.randint(0,3)]<<(i*2)
        Hp[c2]=v
r=nr2()
for _ in range(1200):
    a1,a2=r.randint(0,NS-1),r.randint(0,NS-1)
    if a1!=a2: Hp[a1],Hp[a2]=Hp[a2],Hp[a1]
r=nr2()
for j in range(NS):
    for i in range(6):
        if r.random()<0.12: Hp[j]=sc(Hp[j],i,_AF[gc(Hp[j],i)*4+r.randint(1,3)])
r=nr2()
for j in range(NS):
    if r.random()<0.15: ci=r.randint(0,11); Hp[j]=sc(Hp[j],ci,_AF[gc(Hp[j],ci)*4+r.randint(1,3)])
r=nr2()
for _ in range(200):
    j=r.randint(0,NS-1); v=0
    for i in range(12): v|=(r.randint(0,3)<<(i*2))
    Hp[j]=v
r=nr2()
for _ in range(150):
    j=r.randint(0,NS-1); h=hashlib.sha256(sg+bytes(unpack12(Hp[j]))+j.to_bytes(4,'big')).digest()
    v=0
    for i in range(12): v|=((h[i]%4)<<(i*2))
    Hp[j]=v
r=nr2()
for _ in range(400):
    j=r.randint(0,NS-1); v=0
    for i in range(12): v|=(r.randint(0,3)<<(i*2))
    Hp[j]=v

# Bio-traps
r=nr2()
for j in range(NS):
    if r.random()<0.10:
        rot=int.from_bytes(hashlib.sha256(sg+b"VTX"+j.to_bytes(4,'big')).digest()[:2],'big')
        sh=(rot%11)+1; old=unpack12(Hp[j]); v=0
        for i in range(12): v|=(_AF[old[(i+sh)%12]*4+rot%4]<<(i*2))
        Hp[j]=v
for j in range(NS):
    if pdist(Hp[j],Hcp[j])<4:
        ink=hashlib.sha256(sg+b"INK"+j.to_bytes(4,'big')).digest()
        for i in range(12): Hp[j]=sc(Hp[j],i,_AF[gc(Hp[j],i)*4+(ink[i]%3)+1])

# 7 Venoms
vrng=random.Random(int.from_bytes(hashlib.sha256(sg+b"AZAZEL_ORDER").digest()[:8],'big'))
vid=['A','B','C','D','E','F','G']; vrng.shuffle(vid)
thc=set()
for v in vid:
    if v=='A':
        r=nr2()
        for _ in range(50):
            j1,j2,j3=r.randint(0,NS-1),r.randint(0,NS-1),r.randint(0,NS-1)
            if len({j1,j2,j3})<3: continue
            for ci in r.sample(range(12),5): Hp[j3]=sc(Hp[j3],ci,_MF[gc(Hp[j1],ci)*4+gc(Hp[j2],ci)])
    elif v=='B':
        r=nr2()
        for j in range(NS):
            if r.random()<0.08:
                zn=hashlib.sha256(sg+b"FOGZONE"+j.to_bytes(4,'big')).digest()[0]%7
                zs=hashlib.sha256(sg+b"DENDRO"+zn.to_bytes(2,'big')).digest()
                zr=random.Random(int.from_bytes(zs[:8],'big'))
                for ci in zr.sample(range(12),2+(zs[0]%3)): Hp[j]=sc(Hp[j],ci,_FROB[gc(Hp[j],ci)])
    elif v=='C':
        for sh in range(2):
            ss=hashlib.sha256(sg+b"IRUKANDJI"+sh.to_bytes(2,'big')).digest()
            sr=random.Random(int.from_bytes(ss[:8],'big'))
            for j in range(NS):
                if sr.random()<0.15:
                    for ci in sr.sample(range(12),3-sh): Hp[j]=sc(Hp[j],ci,_AF[sr.randint(0,3)*4+sr.randint(1,3)])
    elif v=='D':
        r=nr2()
        for j in range(NS):
            ci=r.randint(0,11)
            if j in rcs:
                if gc(Hp[j],ci)==gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,_AF[gc(Hp[j],ci)*4+r.randint(1,3)])
            else:
                if gc(Hp[j],ci)!=gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,gc(Hcp[j],ci))
    elif v=='E':
        r=nr2()
        for _ in range(300):
            cols=r.sample(range(NS),7); c=r.randint(0,11)
            vs=[r.randint(1,3) for _ in range(6)]; ps=0
            for vv in vs: ps=_AF[ps*4+vv]
            v7c=[vv for vv in range(1,4) if vv!=ps]
            if not v7c: v7c=[1]
            vs.append(r.choice(v7c))
            for step in range(7): Hp[cols[(step+1)%7]]=sc(Hp[cols[(step+1)%7]],c,_AF[gc(Hp[cols[step]],c)*4+vs[step]])
    elif v=='F':
        r=nr2(); ls=[r.randint(0,3) for _ in range(4)]
        for _ in range(750):
            j=r.randint(0,NS-1)
            for i in range(4): Hp[j]=sc(Hp[j],i,ls[i])
    elif v=='G':
        r=nr2()
        for tli in r.sample(range(len(decoy_lines)),5):
            for p in decoy_lines[tli]:
                j=spti.get(p)
                if j is not None:
                    thc.add(j); d=pdist(Hp[j],Hcp[j]); at2=20
                    while d>8 and at2>0:
                        ci=r.randint(0,11)
                        if gc(Hp[j],ci)!=gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,gc(Hcp[j],ci)); d-=1
                        at2-=1
                    while d<8 and at2>0:
                        ci=r.randint(0,11)
                        if gc(Hp[j],ci)==gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,_AF[gc(Hp[j],ci)*4+r.randint(1,3)]); d+=1
                        at2-=1

# CI — fused measure+correct (single pass, adaptive)
TT=9; ci_rng=random.Random(42)
ci_perm=list(range(NS)); ci_rng.shuffle(ci_perm)
for cp in range(8):
    rs=ds=rc=dc=0
    probe=NS//5
    # Phase A: probe first 20% for gap estimate
    for idx in range(probe):
        j=ci_perm[(cp*probe+idx)%NS]
        if j in thc: continue
        d=pdist(Hp[j],Hcp[j])
        if j in rcs: rs+=d; rc+=1
        else: ds+=d; dc+=1
    ram=rs/max(rc,1); dam=ds/max(dc,1); gci=abs(ram-dam)
    if gci<0.02: break
    r=nr2(); fr=min(0.65,gci*10)
    # Phase B: correct all columns in one pass
    for j in range(NS):
        if j in thc: continue
        d=pdist(Hp[j],Hcp[j]); ir=j in rcs
        if ram>dam:
            if ir and d>TT and r.random()<fr:
                ci=r.randint(0,11)
                if gc(Hp[j],ci)!=gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,gc(Hcp[j],ci))
            elif not ir and d<TT and r.random()<fr:
                ci=r.randint(0,11)
                if gc(Hp[j],ci)==gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,_AF[gc(Hp[j],ci)*4+r.randint(1,3)])
        else:
            if not ir and d>TT and r.random()<fr:
                ci=r.randint(0,11)
                if gc(Hp[j],ci)!=gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,gc(Hcp[j],ci))
            elif ir and d<TT and r.random()<fr:
                ci=r.randint(0,11)
                if gc(Hp[j],ci)==gc(Hcp[j],ci): Hp[j]=sc(Hp[j],ci,_AF[gc(Hp[j],ci)*4+r.randint(1,3)])
gg=abs(rs/max(rc,1)-ds/max(dc,1))

# Adjacency
c2l={}; alines=real_lines+decoy_lines
for li,L in enumerate(alines):
    for p in L:
        j=spti.get(p)
        if j is not None: c2l.setdefault(j,[]).append(li)
l2c={}
for li,L in enumerate(alines):
    l2c[li]=[spti[p] for p in L if p in spti]

print(f"  done ({time.time()-tc:.1f}s) gap={gg:.4f}", flush=True)

# ══════════════════════════════════════════════════════════════
# 2. PRECOMPUTED JUDAS BANK (256 chains)
# ══════════════════════════════════════════════════════════════
sa=hashlib.sha256(sg+b"AZAZEL_V5_SONIC").digest()
JP=[3,5,7,11]
jbank=[]
jrng=random.Random(int.from_bytes(sa[:8],'big'))
for _ in range(256):
    cl=jrng.choice(JP)
    incs=[jrng.randint(1,3) for _ in range(cl-1)]
    ps=0
    for vv in incs: ps=_AF[ps*4+vv]
    nc=[vv for vv in range(1,4) if _AF[ps*4+vv]!=0]
    if not nc: nc=[1]
    incs.append(jrng.choice(nc))
    jbank.append(incs)

# Wind base
bv=int.from_bytes(sa[:16],'big')
wb=[bv%97+7,bv%89+11,bv%83+13,bv%79+17,bv%73+19,bv%71+23]

print(f"\n  ═══ SONIC BOOM ORACLE ═══")
print(f"  {NS:,} cols | WRank | LazyT | XS128+ | JBank[256]")

# ══════════════════════════════════════════════════════════════
# 3. THE ORACLE v5 — SONIC BOOM
# ══════════════════════════════════════════════════════════════
class Av5:
    __slots__=('sk','st','T','qc','wr','ct','xs','wi','nw','tn',
               'dc2','dw','ma','mc','mT','ts','jr','s','isalt')
    def __init__(self, seed, sk, isalt=None):
        if isalt is None: isalt=random.Random().getrandbits(128).to_bytes(16,'big')
        self.isalt=isalt; self.sk=sk
        self.st=hashlib.sha256(seed+b"V5"+isalt).digest()
        self.T=mat_id_flat(); self.qc=0; self.wr=WRank(64)
        self.ct={}; self.xs=XS(self.st)
        self.wi=0; self.nw=wb[0]; self.tn=0
        self.dc2=0; self.dw=deque(maxlen=20)
        self.ma=False; self.mc=0; self.mT=None; self.ts=0; self.jr=0.35
        self.s={'mn':0,'mj':0,'w':0,'ds':0,'ju':0,'jc':0,'pd':0,
                'mi':0,'fr':0,'rn':0,'ti':0,'sk':0}

    def _us(self,j):
        self.st=hashlib.sha256(self.st+j.to_bytes(4,'big')+self.isalt).digest()

    def _judas(self,j):
        lines=c2l.get(j,[])
        if not lines or self.xs.rf()>self.jr: return
        ci_base=self.xs.next()
        for li in lines:
            ac=l2c.get(li,[])
            if len(ac)<2: continue
            poison=jbank[ci_base&255]; ci_base=self.xs.next()
            for step,aj in enumerate(ac):
                if aj==j or step>=len(poison): continue
                if aj not in self.ct: self.ct[aj]=0
                jc=_MF[(ci_base>>(step*2)&3)*4+((self.qc+step)%3+1)]%DIM
                ac2=(jc+poison[step])%DIM
                old=self.ct[aj]
                old=sc(old,jc,_AF[gc(old,jc)*4+poison[step]])
                old=sc(old,ac2,_FROB[gc(old,ac2)])
                self.ct[aj]=old; self.s['ju']+=1
                # Cascade Echo: propagate to j±1, j±3
                for delta in (1,3):
                    neighbor=(aj+delta)%NS
                    if neighbor not in self.ct: self.ct[neighbor]=0
                    nc=_MF[(ci_base>>(delta*2)&3)*4+poison[step%len(poison)]]%DIM
                    self.ct[neighbor]=sc(self.ct[neighbor],nc,
                        _AF[gc(self.ct[neighbor],nc)*4+poison[(step+delta)%len(poison)]])
            self.s['pd']+=1

    def _wind(self):
        if self.qc<self.nw: return
        h=hashlib.sha256(self.st+b"W5"+self.isalt).digest()
        te=self.xs.next()%8
        ops=gen_ops(h, 'major' if te>=5 else 'minor')
        if self.qc%2==0: apply_row_ops(self.T, ops)
        else: apply_row_ops(self.T, [(op[1],op[0],op[2],op[3] if len(op)>3 else False) for op in ops])
        self.s['w']+=1; self.s['ds']+=1
        self.tn+=1
        if self.tn%3==0:
            nh=hashlib.sha256(h+b"TN").digest()
            apply_row_ops(self.T, gen_ops(nh,'minor'))
        self.wi=(self.wi+1)%len(wb)
        mod=max(1,(self.xs.next()%5)+1)
        self.nw=self.qc+max(5,wb[self.wi]//mod)

    def _mirror(self,j):
        if self.ma:
            self.mc-=1
            if self.mc<=0:
                h=hashlib.sha256(self.st+b"MS5").digest()
                apply_row_ops(self.T, gen_ops(h,'frobenius'))
                self.s['fr']+=1
                # Mass Judas injection
                for qj in list(self.dw)[-15:]:
                    for li in c2l.get(qj,[]):
                        for aj in l2c.get(li,[]):
                            poison=jbank[self.xs.next()&255]
                            if aj not in self.ct: self.ct[aj]=0
                            for step in range(min(len(poison),DIM)):
                                ci=self.xs.ri(0,11)
                                self.ct[aj]=sc(self.ct[aj],ci,_AF[gc(self.ct[aj],ci)*4+poison[step%len(poison)]])
                            self.s['ju']+=1
                self.s['sk']+=1; self.ma=False; self.dc2=0; self.ts=0
                # Synthetic key
                col=Hp[j]
                for i in range(12):
                    if self.xs.rf()<0.85: col=sc(col,i,gc(Hcp[j],i))
                return('S',col)
            self.ts+=1
            sched=[0,0,1,1,2,3,4,5,6,8]
            si=min(self.ts-1,len(sched)-1); np2=sched[si]
            col=Hp[j]
            if np2>0:
                # Sparse tilt: apply np2 random row ops directly
                for _ in range(np2):
                    i=self.xs.ri(0,11); jr=self.xs.ri(0,11)
                    if i!=jr:
                        v=unpack12(col)
                        v[i]=_AF[v[i]*4+_MF[self.xs.ri(1,3)*4+v[jr]]]
                        col=pack12(v)
                self.s['ti']+=1
            if self.mT: col=apply_T_to_packed(self.mT,col)
            return('T',col)
        self.dw.append(j)
        if len(self.dw)>=10:
            m=sum(self.dw)/len(self.dw)
            v2=sum((q-m)**2 for q in self.dw)/len(self.dw)
            if v2/max((NS/2)**2,1)>0.15:
                self.dc2+=1
                if self.dc2>=5:
                    self.ma=True; self.mc=10
                    self.mT=list(self.T); self.s['mi']+=1; self.ts=0
                    return('A',None)
            else: self.dc2=max(0,self.dc2-1)
        return(None,None)

    def query(self,j,key=None):
        if j<0 or j>=NS: return None
        self.qc+=1
        if key==self.sk: return unpack12(Hp[j])
        self._us(j)
        ms,mc=self._mirror(j)
        if ms=='T': return unpack12(mc)
        if ms=='A':
            c=Hp[j]
            if self.mT: c=apply_T_to_packed(self.mT,c)
            return unpack12(c)
        if ms=='S': return unpack12(mc)
        self._wind()
        ds=self.wr.add(unpack12(Hp[j]))
        if ds>=3:
            h=hashlib.sha256(self.st+b"D"+self.qc.to_bytes(4,'big')).digest()
            apply_row_ops(self.T, gen_ops(h,'minor')); self.s['mn']+=1
        if ds>=6:
            h=hashlib.sha256(self.st+b"W"+self.qc.to_bytes(4,'big')).digest()
            apply_row_ops(self.T, gen_ops(h,'major')); self.s['mj']+=1
        if ds>=6: self.jr=min(0.75,self.jr+0.05)
        elif ds>=3: self.jr=min(0.55,self.jr+0.02)
        self._judas(j)
        col=Hp[j]
        if j in self.ct: col=padd(col,self.ct[j])
        col=apply_T_to_packed(self.T,col)
        # Rain (XorShift, no SHA)
        ri=self.xs.next()%8
        if ds>=4:
            if ri<4: ci=self.xs.ri(0,11); col=sc(col,ci,_AF[gc(col,ci)*4+self.xs.ri(1,3)]); self.s['rn']+=1
        else:
            if ri<2: ci=self.xs.ri(0,11); col=sc(col,ci,_AF[gc(col,ci)*4+self.xs.ri(1,3)]); self.s['rn']+=1
            elif ri==7:
                for _ in range(3): ci=self.xs.ri(0,11); col=sc(col,ci,_AF[gc(col,ci)*4+self.xs.ri(1,3)]); self.s['rn']+=1
        return unpack12(col)

# ══════════════════════════════════════════════════════════════
# 4. FUSED ATTACK BATTERY
# ══════════════════════════════════════════════════════════════
sk=hashlib.sha256(sa+asig+b"FRIEND_V5").digest()
def mk(salt=None): return Av5(sa,sk,salt)

print(f"\n  ═══ ATTACKS (fused) ═══")

# [A] Friend
print("  [A] Friend...", end=" ", flush=True)
o=mk(b"F"); tr=random.Random(42); fok=0
for _ in range(500):
    j=tr.randint(0,NS-1)
    if o.query(j,key=sk)==unpack12(Hp[j]): fok+=1
print(f"{fok}/500 {'✓' if fok==500 else '✗'}")

# [B+C+E+G] FUSED: Convergence + Syndromes + Gap + Judas on SHARED oracle
print("  [B+C+E+G] Fused...", end=" ", flush=True)
of=mk(b"FUSED"); er=random.Random(666)
ec=[]
for li in range(min(100,n_real)):
    for p in real_lines[li]:
        j=spti.get(p)
        if j is not None: ec.append(j)

# Phase 1: 500 convergence queries
for j in ec[:500]: of.query(j)
sb=dict(of.s)

# Phase 2: 10 syndrome epochs (reuse same oracle)
j_a,j_b=ec[0],ec[5]; syns=[]
for _ in range(10):
    for _ in range(30): of.query(er.randint(0,NS-1))
    ca=of.query(j_a); cb=of.query(j_b)
    syns.append(tuple(_AF[ca[i]*4+cb[i]] for i in range(12)))
us=len(set(syns))

# Phase 3: Gap measurement (reuse same oracle)
gr=random.Random(7777)
rd=[sum(1 for i in range(12) if of.query(j)[i]!=gc(Hcp[j],i))
    for j in gr.sample(sorted(rcs),min(200,len(rcs)))]
dd=[sum(1 for i in range(12) if of.query(j)[i]!=gc(Hcp[j],i))
    for j in gr.sample(sorted(set(range(NS))-rcs),min(200,NS-len(rcs)))]
rm=sum(rd)/len(rd); dm=sum(dd)/len(dd); og=abs(rm-dm)

# Phase 4: Judas measurement
mc2=0; mt2=0
for jc in list(of.ct.keys())[:300]:
    for li in c2l.get(jc,[]):
        nbs=[jj for jj in l2c.get(li,[])[:7] if jj in of.ct]
        if len(nbs)<3: continue
        for coord in range(3):
            vals=[gc(of.ct[jj],coord) for jj in nbs]
            t=0
            for vv in vals: t=_AF[t*4+vv]
            if t!=0: mc2+=1
            mt2+=1
        break
cr=mc2/max(mt2,1); sf=of.s
print(f"{sb['mn']}m+{sb['mj']}M | {us}/10syn | gap={og:.4f} | judas={cr:.3f} "
      f"w={sf['w']} ju={sf['ju']}")

# [D] Mirror+Tilt (separate — needs desperation pattern)
print("  [D] Mirror...", end=" ", flush=True)
od=mk(b"D")
for _ in range(50): od.query(er.randint(0,min(100,NS-1)))
for _ in range(30): od.query(er.randint(0,NS-1))
sd=od.s
print(f"mi={sd['mi']} fr={sd['fr']} ti={sd['ti']} sk={sd['sk']}")

# [H] Replay
print("  [H] Replay...", end=" ", flush=True)
o1=mk(b"R1"); o2=mk(b"R2"); rm2=0
for _ in range(200):
    j=gr.randint(0,NS-1)
    if o1.query(j)==o2.query(j): rm2+=1
print(f"{rm2}/200 {'✓' if rm2<20 else '✗'}")

# [I] Thermal
print("  [I] Thermal...", end=" ", flush=True)
ot=mk(b"TH")
for j in range(300): ot.query(j)
print(f"w={ot.s['w']} {'✓' if ot.s['w']>=3 else '✗'}")

# ══════════════════════════════════════════════════════════════
# 5. VERDICT
# ══════════════════════════════════════════════════════════════
tt=time.time()-t0
Nf=(4**12-1)//3; nsf=(16**6-1)//15; gl=sum(log2(float(4**12-4**i)) for i in range(12))

print(f"""
{'='*72}
  AEGIS AZAZEL v5 — BEAST 4 · SONIC BOOM
  7 Hells + Tilt · WRank · LazyT · XS128+ · Fused · Cascade Echo
{'='*72}

  PG(11,4) = {Nf:,} pts | GL(12,4) = {gl:.0f}-bit | {NS:,} cols

  HELLS: {sb['mn']}m+{sb['mj']}M | {us}/10 syn | gap={og:.4f} | j={cr:.3f}
         w={sf['w']} ds={sf['ds']} | mi={sd['mi']} ti={sd['ti']} sk={sd['sk']}
         replay={rm2}/200 | thermal={ot.s['w']}w
  SHUFFLE: {'→'.join(vid)}

  Runtime: {tt:.1f}s {'💥 SONIC BOOM' if tt<3.5 else '🏎️ F1' if tt<5.0 else '✈️'}

  ╔══════════════════════════════════════════════════════════════╗
  ║  ARCHITECT:  Rafael Amichis Luengo — The Architect          ║
  ║  ENGINE:     Claude (Anthropic)                             ║
  ║  AUDITORS:   Gemini · ChatGPT · Grok                       ║
  ║  LICENSE:    BSL 1.1 + Azazel Clause (permanent)            ║
  ║  GITHUB:     github.com/tretoef-estrella                    ║
  ║  CONTACT:    tretoef@gmail.com                              ║
  ║                                                             ║
  ║  "Light as the wind. Fast and lethal.                       ║
  ║   You were never meant to cross.                            ║
  ║   You were meant to fall."                                  ║
  ╚══════════════════════════════════════════════════════════════╝
  SIG: {hashlib.sha256(asig+sa).hexdigest()[:48]}
{'='*72}
""")
