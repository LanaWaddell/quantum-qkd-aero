# Quantum Error Correction Threshold Report

## Summary of Findings
During our aerospace telemetry simulations, we tested a **3-qubit Repetition Code** to protect a Bell State (entangled sensors) from atmospheric interference.

### 10% Noise Analysis (Current Results)
- **Physical Error Probability ($p$):** 0.1 (10%)
- **Unprotected Error Rate:** ~18%
- **QEC Logical Error Rate:** ~32%
- **Conclusion:** **FAIL.** 10% noise is significantly above the accuracy threshold for a 3-qubit repetition code. The overhead of the extra physical qubits and gates introduced more noise than the majority-voting logic could correct.

## The "Lower Noise" Hypothesis ($p = 0.01$)
In a real-world scenario with better shielding or higher altitude, we might expect a lower physical error rate, such as **1% ($0.01$)**.

### Predicted Outcome for 1% Noise:
At $p = 0.01$, the probability of two errors in a triplet (which causes the QEC to fail) is roughly $3 \times (0.01)^2 = 0.0003$.
- **Unprotected Error Rate:** Would be roughly $2p \approx 0.02$ (2%).
- **QEC Logical Error Rate:** Would likely drop to **< 1%**.
- **Verdict:** QEC would be highly beneficial at 1% noise, as it would effectively "squash" the error rate to nearly zero, whereas at 10% it actually compounds the problem.

## Future Recommendations
- For high-interference environments (>5% noise), consider more robust codes (e.g., Surface Codes) or improve hardware fidelity before implementing QEC.
