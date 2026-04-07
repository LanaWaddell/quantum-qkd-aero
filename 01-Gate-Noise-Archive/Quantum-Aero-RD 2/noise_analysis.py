import subprocess
import json
import os
from datetime import datetime

def run_simulation():
    """Runs the noisy simulation and returns the counts."""
    # Note: we need to use the virtual environment's python
    venv_python = os.path.join(os.getcwd(), "venv", "bin", "python3.13")
    script_path = os.path.join("simulations", "quantum_test.py")
    
    result = subprocess.run([venv_python, script_path], capture_output=True, text=True)
    output = result.stdout
    
    # Parse the dictionary from the output
    # Looking for: Qubit measurements (Sensor A, Sensor B):\n{'01': 96, '11': 420, '10': 84, '00': 400}
    try:
        counts_line = [line for line in output.split('\n') if line.startswith('{')][0]
        # Convert single quotes to double quotes for JSON parsing if necessary, 
        # but here we can just use eval or carefully parse. 
        # Python's str representaiton of dict can be parsed with json if we swap quotes.
        counts = json.loads(counts_line.replace("'", '"'))
        return counts
    except Exception as e:
        print(f"Error parsing simulation output: {e}")
        return None

def analyze_noise():
    print("Starting Noise Analysis...")
    
    # Perfect/Clean data baseline (Theoretical for 1000 shots)
    clean_data = {'00': 500, '11': 500, '01': 0, '10': 0}
    
    noisy_data = run_simulation()
    if not noisy_data:
        return

    # Calculate metrics
    total_shots = sum(noisy_data.values())
    clean_sync = clean_data['00'] + clean_data['11']
    noisy_sync = noisy_data.get('00', 0) + noisy_data.get('11', 0)
    noisy_errors = noisy_data.get('01', 0) + noisy_data.get('10', 0)
    
    sync_degradation = ((clean_sync - noisy_sync) / clean_sync) * 100
    
    # Log report
    log_content = [
        f"--- Aerospace Telemetry Noise Analysis Report ---",
        f"Timestamp: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
        f"Description: Comparison between theoretical 'Clean' and simulated 'Noisy' data.",
        f"Atmospheric Interference Model: 10% Bit-Flip error probability.",
        f"",
        f"Data Comparison (Shots: {total_shots}):",
        f"Full Synchronization ('00', '11'):",
        f"  Clean: {clean_sync} (100%)",
        f"  Noisy: {noisy_sync} ({noisy_sync/total_shots*100:.1f}%)",
        f"",
        f"Desynchronization Errors ('01', '10'):",
        f"  Clean: 0 (0%)",
        f"  Noisy: {noisy_errors} ({noisy_errors/total_shots*100:.1f}%)",
        f"",
        f"Conclusion:",
        f"  The interference model caused a {sync_degradation:.1f}% degradation in telemetry synchronization.",
        f"  This represents a significant risk for synchronized satellite sensor systems.",
        f"------------------------------------------------"
    ]
    
    log_path = os.path.join("logs", "noise_comparison.log")
    with open(log_path, "w") as f:
        f.write("\n".join(log_content))
    
    print(f"Analysis complete. Report saved to: {log_path}")
    print("\n".join(log_content))

if __name__ == "__main__":
    analyze_noise()
