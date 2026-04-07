import os
import json
import sys

import matplotlib.pyplot as plt

PROJECT_ROOT = os.path.dirname(__file__)
SRC_DIR = os.path.join(PROJECT_ROOT, "src")
OUTPUTS_DIR = os.path.join(PROJECT_ROOT, "outputs")

if SRC_DIR not in sys.path:
    sys.path.insert(0, SRC_DIR)

from qkd.teleportation import TeleportationMission, build_teleportation_results


os.makedirs(OUTPUTS_DIR, exist_ok=True)

teleport = TeleportationMission()
f_index, fid, res = teleport.run_teleportation()

fig, ax1 = plt.subplots(figsize=(10, 6))

ax1.set_xlabel('Teleported Quantum Frames')
ax1.set_ylabel('Teleportation Fidelity', color='blue')
ax1.plot(f_index, fid, color='blue', alpha=0.7)
ax1.axhline(y=0.67, color='red', linestyle='--', label='Classical Limit')
ax1.set_ylim(0.5, 1.0)
ax1.legend(loc='upper left')

ax2 = ax1.twinx()
ax2.set_ylabel('Remaining Entangled Resource (Kb)', color='green')
ax2.plot(f_index, res, color='green', linewidth=2)

plt.title('Mission Lana: Quantum Teleportation Link')
plt.savefig(os.path.join(OUTPUTS_DIR, 'qkd_teleportation.png'))
plt.show()

mission_results = build_teleportation_results(
    f_index,
    fid,
    res,
    plot_path="outputs/qkd_teleportation.png",
)

with open(os.path.join(OUTPUTS_DIR, 'results.json'), 'w') as f:
    json.dump(mission_results, f)

print(
    "Dashboard Updated: "
    f"Yield {mission_results['summary']['headline_key_yield']} | "
    f"Fidelity {mission_results['summary']['headline_fidelity']}"
)
