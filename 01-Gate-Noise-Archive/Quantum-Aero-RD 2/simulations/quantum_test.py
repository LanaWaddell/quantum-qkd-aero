from qiskit import QuantumCircuit, transpile
from qiskit_aer import Aer
from qiskit_aer.noise import NoiseModel, pauli_error

# Create a Quantum Circuit with 2 qubits and 2 classical bits
qc = QuantumCircuit(2, 2)

# Step 1: Put qubit 0 into a superposition (|0> + |1>) / sqrt(2)
qc.h(0)

# Step 2: Perform a CNOT gate with qubit 0 as control and qubit 1 as target
# This creates the Bell state (|00> + |11>) / sqrt(2)
# This entanglement represents two synchronized satellite sensors, 
# where measuring one instantly correlates with the state of the other.
qc.cx(0, 1)

# Step 3: Map the quantum measurement to the classical bits
qc.measure([0, 1], [0, 1])

# --- Noise Model Setup ---
# Set the error probability to 0.1 (simulating heavy atmospheric interference)
p_error = 0.1
# Bit-flip error is a Pauli X error
error_gate = pauli_error([('X', p_error), ('I', 1 - p_error)])

# Add errors to all single-qubit gates and two-qubit gates
noise_model = NoiseModel()
noise_model.add_all_qubit_quantum_error(error_gate, ["u1", "u2", "u3", "h"])
noise_model.add_all_qubit_quantum_error(error_gate.tensor(error_gate), ["cx"])

# Use Aer's simulator with the noise model
simulator = Aer.get_backend('qasm_simulator')

# Run and get counts
compiled_circuit = transpile(qc, simulator)
job = simulator.run(compiled_circuit, shots=1000, noise_model=noise_model)
result = job.result()
counts = result.get_counts(qc)

print("\n--- Noisy Bell State Correlation Test ---")
print(f"Simulation with {p_error*100}% Bit-Flip error (Atmospheric Interference)")
print("Qubit measurements (Sensor A, Sensor B):")
print(counts)

print("\n--- Telemetry Analysis ---")
perfect_sync = counts.get('00', 0) + counts.get('11', 0)
desync_errors = counts.get('01', 0) + counts.get('10', 0)

print(f"Synchronized Readings ('00', '11'): {perfect_sync}")
print(f"Desynchronized Errors ('01', '10'): {desync_errors}")

print("\nInterpretation:")
print("- '00' or '11': Sensors are correlated (Teleportation/Entanglement preserved).")
print("- '01' or '10': Represents a 'Bit-Flip' error due to atmospheric interference.")
print("  In an aerospace context, this means Sensor A reported a value that Sensor B did not,")
print("  indicating a telemetry mismatch or sensor failure under heavy interference.")
