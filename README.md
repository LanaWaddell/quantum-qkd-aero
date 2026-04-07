# Mission Lana: Satellite QKD & Quantum Teleportation Simulator

A Python-based R&D sandbox for simulating satellite-to-ground Quantum Key Distribution (QKD) and Entanglement-based communication protocols.

## 📋 Project Overview
This project simulates the physical and security challenges of establishing a quantum link with a Low Earth Orbit (LEO) satellite. It accounts for atmospheric attenuation, geometric beam spreading, active eavesdropping (Eve), and quantum decoherence.

## 🚀 Key Features
* **Dynamic Pass Modeling:** Simulates a 300-second satellite pass with varying elevation angles ($10^\circ$ to $90^\circ$).
* **Link Budget Analysis:** Calculates slant range, atmospheric loss (dB), and geometric efficiency.
* **Security Protocols:** Implements BB84 with Decoy State countermeasures to mitigate intercept-resend attacks.
* **Entanglement & Teleportation:** Models Bell-inequality violations (S-parameter) and quantum teleportation fidelity over a noisy channel.
* **Weather Simulation:** Toggleable cloud-cover interference with stochastic link-blockage logic.

## 📊 Technical Results
* **Optimal Yield:** Achieved **65.8 Mb** of secure key volume under clear skies.
* **Security Thresholds:** Maintained a **QBER < 11%** despite a 10% interception rate by an adversary.
* **Quantum Fidelity:** Successfully maintained teleportation fidelity between **0.80 and 0.90**, well above the **0.67** classical limit.

## 🛠️ Installation & Usage
1. **Clone the repository:**
   ```bash
   cd Documents/Projects/Quantum-QKD-Aero
