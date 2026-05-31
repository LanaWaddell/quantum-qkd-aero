from qkd.teleportation import TeleportationMission, build_teleportation_results


def test_teleportation_mission_current_output_lengths():
    frames, fidelities, resources = TeleportationMission().run_teleportation()

    assert len(frames) == 1000
    assert len(fidelities) == 1000
    assert len(resources) == 1000


def test_build_teleportation_results_current_schema():
    frames = [0, 1]
    fidelities = [0.8, 0.9]
    resources = [14.99, 14.98]

    results = build_teleportation_results(frames, fidelities, resources, "outputs/example.png")

    assert results["teleportation"]["frames"] == 2
    assert results["teleportation"]["average_fidelity"] == 0.85
    assert results["summary"]["headline_key_yield"] == "14.98 Kb"
    assert results["summary"]["headline_fidelity"] == "0.850"
