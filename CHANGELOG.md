# AEGIS AZAZEL — Changelog

All notable changes to AEGIS AZAZEL (Beast 4) are documented in this file.

---

## [v5] — 2026-02-26 · SONIC BOOM

### Performance
- **Runtime: 5.6s → 2.3s** (-56%)
- Incremental `WindowRank` replaces full Gaussian elimination (O(12×rank) vs O(64×144))
- Lazy T via direct row operations — `mat_mul_flat` eliminated entirely
- XorShift128+ PRNG replaces per-query SHA256 for non-cryptographic paths
- Attack battery fused: B, C, E, G share single oracle instance (-1400 queries)
- GORGON heritage: sampled CI with 20% probe + early exit (10 passes → 3-4)
- Precomputed Judas bank (256 Möbius chains at init, zero per-query generation)
- Sparse Tilt: O(perturbations) instead of O(144)

### Lethality
- **Cascade Echo**: Judas propagation to j±1 and j±3 with linked seeds
- **Resonance Judas**: targets WindowRank leading pivots every 25 queries
- Judas injection volume: 1,104 → 17,572 (×16)
- Contradiction rate: 0.691 → 0.746 (+8%)

### Metrics
- GORGON gap: 0.0084 → 0.0013 (-85%)
- Friend: 500/500 | Syndromes: 10/10 | Replay: 1/200

---

## [v4] — 2026-02-26 · The Manifold Bridge

### Performance
- **Runtime: 10.1s → 5.6s** (-45%)
- Bit-sliced GF(4): 12 coordinates packed as 24-bit integers
- Flat matrices: 12×12 → array[144] for cache efficiency
- SHA256 LRU cache (50k entries)
- Lazy T evaluation: accumulate rotations, apply on query

### Security (Grok Round 1 Fixes)
- [FIX-1] Session binding via `instance_salt` (replay: 0/200)
- [FIX-2] Subspace-trajectory wind replaces thermal variance
- [FIX-3] Mirror lockout: state evolution frozen during tilt
- [FIX-4] Judas coordinate randomization via multiplicative hashing
- [FIX-5] MinRank snapshot recovery defeated via T-noise

### Lethality (Gemini + ChatGPT Enhancements)
- Syzygy Baiting: Judas chains mimic algebraic relations
- Thread Desynchronization: even/odd queries get different T application order
- Graduated Tilt: 10-step degradation curve
- Synthetic Valid Key: 85% clean column at query 11
- Statistical camouflage: rolling histogram preservation

---

## [v3] — 2026-02-26

### Enhancements
- Integrated all Gemini algebraic proposals (Syzygy Baiting, prime-length chains)
- Integrated all ChatGPT statistical proposals (Graduated Tilt, SIMD-lane patterns)
- Stealth Judas: dynamic rate 35%→55%→75% based on convergence detection
- Full attack battery: 9 tests covering all defense layers

### Known Issue
- Runtime regression to 10.1s due to enhanced complexity

---

## [v2] — 2026-02-26

### Security
- All 5 Grok vulnerabilities closed
- Session binding prevents cross-oracle correlation
- Mirror lockout prevents state evolution during tilt phase
- Judas coordinate randomization eliminates saturation signature

---

## [v1] — 2026-02-26 · Initial Release

### Architecture
- Streaming oracle wrapping GORGON v16 heritage
- 7 Hells: Rotten Planks, Rola Bola, Saw Traps, Gorgon Swamp, Fractal Wind, Rain, Judas Echo
- False Mirror of Surrender with Tilt degradation
- Convergence detection: Chinese Water Torture + Whiplash
- Point G homeostasis: chaos outside, order inside

---

**Author:** Rafael Amichis Luengo — *The Architect*  
**Engine:** Claude (Anthropic)  
**Auditors:** Gemini · ChatGPT · Grok
