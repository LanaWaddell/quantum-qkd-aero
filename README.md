# Mission Lana: Satellite QKD & Quantum Teleportation Simulator

Quantum-QKD-Aero is a Python-based R&D sandbox for satellite-to-ground QKD and teleportation experiments. The current implementation is a lightweight simulator plus a local dashboard; Phase 2 interface contracts are documented but not fully implemented yet.

## Implemented Now

- BB84 toy simulation with bit loss, bit flips, sifting, and QBER reporting.
- Teleportation mission toy simulation that writes a fidelity/resource plot.
- Local Express dashboard that reads simulator artifacts from `outputs/` with fallback to tracked root artifacts.
- Phase 2A repository foundation: packaging metadata, interface contract docs, schema recognition, reserved module names, and pytest scaffolding.

## Current Workflow

Run the simulator:

```bash
python src/qkd/run.py
```

The simulator writes:

- `outputs/results.json`
- `outputs/qkd_teleportation.png`

Launch the dashboard:

```bash
npm start
```

Then open:

```text
http://localhost:8080
```

The dashboard prefers `outputs/results.json` and `outputs/qkd_teleportation.png`, then falls back to the tracked root `results.json` and `qkd_teleportation.png`.

## Recreate The Python Environment

The current working environment was captured in `requirements.txt`.

```bash
python3 -m venv qkd_env
qkd_env/bin/python -m pip install -r requirements.txt
qkd_env/bin/python src/qkd/run.py
```

For package-style development, install the project with the optional dev extra:

```bash
python -m pip install -e ".[dev]"
pytest
```

Qiskit is optional and is not required for the default simulator:

```bash
python -m pip install -e ".[qiskit]"
```

## Active Code vs Archive

Active code lives in `src/qkd/`, with the dashboard in `dashboard.js` and Phase 2A tests in `tests/`.

`01-Gate-Noise-Archive/` is preserved archival research material. It may contain Qiskit porting candidates for future optional validation paths, including Bell-state preparation, noise-model, and measurement-count routines. Archive files are not part of the active default workflow.

Root PNGs and root `results.json` are tracked fallback/demo artifacts. Fresh simulator output is written under `outputs/`.

## Planned

`docs/INTERFACES.md` is the canonical implementation contract for Phase 2. Phase 2B is planned to add calibrated physics modules for channel state, decoy analysis, Eve strategies, teleportation fidelity, and CHSH while keeping Qiskit optional. Those Phase 2B physics features are not implemented yet.
