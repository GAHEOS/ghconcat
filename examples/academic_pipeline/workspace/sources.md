===== notes/note_conference_summary_QIP2025.md ===== 
```markdown
# QIP 2025 – Hot-topic Session Summary

*Tokyo, 27 Jan 2025*

## 1. Boson Sampling Beyond 100 Photons

**Speaker:** Jian-Wei Pan

* Claimed 1 × 10⁻²₃ sampling hardness bound using 144-mode interferometer.
* Introduced time-domain multiplexing scheme; reduces footprint 40 ×.

## 2. Error-Corrected Photonic Qubits

**Speaker:** Stefanie Barz

* Demonstrated **[[4,2,2]]** code on dual-rail qubits with 97 % heralded fidelity.
* Cluster-state growth via fusion-II gates reached 10⁶ physical time-bins.

## 3. NV-Centre to Photon Transduction

**Speaker:** M. Atatüre

* On-chip diamond-SiN evanescent coupling, g≈30 MHz.
* Outlook: deterministic Bell-state delivery at >10 k links.

### Cross-cutting trends

* Integrated PPLN and thin-film LiNbO₃ are **everywhere**.
* Shift from bulk optics toward heterogeneous III-V + SiN platforms.
* Community rallying around **“error mitigation before error correction”** mantra.
```
===== notes/note_lab_log_2025-06-03.md ===== 
```markdown
# Lab Log – 3 Jun 2025

*Integrated Silicon Nitride Waveguides for On-Chip Entanglement*

## Objective

Test the latest Si₃N₄ waveguide batch (run #Q-0601) for loss, birefringence and two-photon interference visibility.

## Setup

| Item         | Model                                 | Notes          |
|--------------|---------------------------------------|----------------|
| Pump laser   | TOPTICA iBeam-Smart 775 nm            | 10 mW CW       |
| PPLN crystal | Period = 7.5 µm                       | Type-0 SPDC    |
| Chip mount   | Temperature-controlled (25 ± 0.01 °C) | –              |
| Detectors    | SNSPD pair, η≈80 %                    | Jitter ≈ 35 ps |

## Key results

* Propagation loss **1.3 dB ± 0.1 dB cm⁻¹** @ 1550 nm (cut-back).
* HOM dip visibility **91 %** without spectral filtering (best so far).
* No appreciable birefringence within ±0.05 nm tuning range.

> **TODO**: simulate dispersion for 3 cm spirals; schedule e-beam mask adjustments.
```
===== notes/note_review_article_highlights.md ===== 
```markdown
# Highlights – Review: *“Photonic Quantum Processors”* (Rev. Mod. Phys. 97, 015005 (2025))

| Section              | Take-away                                                                                                | Open questions                                                    |
|----------------------|----------------------------------------------------------------------------------------------------------|-------------------------------------------------------------------|
| Linear-optical gates | Deterministic CNOT remains >90 dB loss-budget dream; hybrid measurement-based approaches most promising. | Can η_det ≥ 95 % SNSPDs plus temporal multiplexing close the gap? |
| Integrated sources   | On-chip χ² micro-rings achieve 300 MHz pair rate at p-pump = 40 mW.                                      | Thermal cross-talk scaling beyond 100 sources?                    |
| Error models         | Dephasing now dominates over loss in tightly confined waveguides.                                        | Need unified benchmarking across foundries.                       |
| Applications         | Near-term advantage in photonic machine-learning inference.                                              | Energy/latency trade-off vs silicon AI accelerators.              |

### Author’s critique

The review glosses over cryo-packaging challenges and the *actual* cost of ultra-low-loss SiN (≤0.5 dB m⁻¹). Include
comparative LCA data in future work.
```
