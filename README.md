# Quantum QKD Aero

A modular simulation platform for quantum communication systems, exploring teleportation fidelity, BB84 key distribution, and channel effects (loss and noise) within a unified, extensible framework.

---

## 🔬 Overview

This project models key components of quantum communication systems:

- **Quantum Teleportation**  
  Simulates fidelity degradation and entanglement resource consumption under noise.

- **BB84 Quantum Key Distribution (QKD)**  
  Implements a minimal protocol with basis selection, sifting, and QBER calculation.

- **Channel Model**  
  Shared abstraction for:
  - photon loss  
  - bit-flip noise  
  - fidelity degradation  

The system is designed to evolve toward more realistic simulations, including atmospheric effects, adversarial models, and satellite-based communication scenarios.

---

## 🧠 Architecture

The project follows a modular structure:

```
src/qkd/
├── teleportation.py   # Teleportation simulation
├── bb84.py            # BB84 protocol simulation
├── channel.py         # Shared channel (loss + noise)
├── run.py             # Simulation entry point
```

### Core Design Principles

- **Separation of concerns**  
  Protocols, channel, and metrics are independent modules

- **Shared environment model**  
  All simulations use a unified channel abstraction

- **Reproducibility**  
  Deterministic runs via seeded randomness

- **Extensibility**  
  New protocols and channel effects can be added without restructuring

---

## ⚙️ Running the Simulation

Using the project virtual environment:

```bash
MPLBACKEND=Agg MPLCONFIGDIR=/tmp/matplotlib ./qkd_env/bin/python3 src/qkd/run.py
