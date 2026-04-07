from qiskit import QuantumCircuit, transpile
from qiskit_aer import Aer
from qiskit_aer.noise import NoiseModel, pauli_error
from collections import Counter

# 6 physical qubits (3 per logical qubit), 6 classical bits for measurement
qc = QuantumCircuit(6, 6)

# --- Encoding Process ---
# 1. Create Bell State on data qubits (q0 and q3)
qc.h(0)
qc.cx(0, 3)

# 2. Encode data q0 -> (q0, q1, q2) using repetition code
qc.cx(0, 1)
qc.cx(0, 2)

# 3. Encode data q3 -> (q3, q4, q5) using repetition code
qc.cx(3, 4)
qc.cx(3, 5)

# Step 4: Map all physical qubits to classical bits
qc.measure(range(6), range(6))

# --- Noise Model ---
# 10% bit-flip error probability (same as quantum_test.py)
p_error = 0.1
error_gate = pauli_error([('X', p_error), ('I', 1 - p_error)])
noise_model = NoiseModel()

# Applying noise to the basic gates
noise_model.add_all_qubit_quantum_error(error_gate, ["u1", "u2", "u3", "h"])
noise_model.add_all_qubit_quantum_error(error_gate.tensor(error_gate), ["cx"])

# --- Simulation ---
simulator = Aer.get_backend('qasm_simulator')
compiled_circuit = transpile(qc, simulator)
job = simulator.run(compiled_circuit, shots=1000, noise_model=noise_model)
result = job.result()
counts = result.get_counts(qc)

# --- Majority Vote Decoding ---
def decode_majority(bitstring):
    """
    Decodes the 6-bit physical measurement into a 2-bit logical state.
    Qiskit bitstring order: q5 q4 q3 q2 q1 q0
    """
    # Convert to list of ints for easier indexing
    bits = [int(b) for b in bitstring]
    # L1 (Logical Qubit 1) = q0, q1, q2 (Indices 5, 4, 3 in string)
    l1_group = [bits[5], bits[4], bits[3]]
    l1_val = 1 if sum(l1_group) >= 2 else 0
    
    # L2 (Logical Qubit 2) = q3, q4, q5 (Indices 2, 1, 0 in string)
    l2_group = [bits[2], bits[1], bits[0]]
    l2_val = 1 if sum(l2_group) >= 2 else 0
    
    return f"{l1_val}{l2_val}"

decoded_counts = Counter()
for bitstring, count in counts.items():
    logical_state = decode_majority(bitstring)
    decoded_counts[logical_state] += count

print("\n--- QEC Repetition Code Correlation Test ---")
print(f"Simulation with {p_error*100}% Bit-Flip error (Atmospheric Interference)")
print(f"Decoding Method: Majority Vote (3-to-1 Logical Mapping)")
print("\nDecoded Logical Counts (L1, L2):")
print(dict(decoded_counts))

print("\n--- Telemetry Analysis ---")
perfect_sync = decoded_counts['00'] + decoded_counts['11']
desync_errors = decoded_counts['01'] + decoded_counts['10']

print(f"Logical Synchronized Readings ('00', '11'): {perfect_sync}")
print(f"Logical Desynchronized Errors ('01', '10'): {desync_errors}")

print("\nInterpretation:")
print("- The Repetition Code protects against single bit-flip errors per triplet.")
print("- If 0 or 1 bit-flips occur in a group of 3, the logical value is preserved.")
print("- Comparing to unprotected results, the '01' and '10' error rates should be significantly lower.")
