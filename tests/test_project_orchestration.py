from ai_product_factory.control_plane import MemoryControlPlaneStore
from ai_product_factory.project_orchestration import BootstrapStage, ProjectBootstrapOrchestrator


def test_enqueue_product_bootstrap_is_durable_and_model_free():
    store = MemoryControlPlaneStore()
    project = store.create_project(project_key="demo", name="Demo", repository="", project_kind="greenfield")
    result = ProjectBootstrapOrchestrator(store).enqueue("demo")
    assert result.project == project
    assert result.task.project_id == project.id
    assert result.run.task_id == result.task.id
    assert result.run.execution_route == "direct"
    assert result.stages == (BootstrapStage.DISCOVERY, BootstrapStage.SPECIFICATION, BootstrapStage.PLANNING)
    assert store.tool_usage[-1].estimated_cost == 0
    assert store.tool_usage[-1].metadata["stages"] == ["discovery", "specification", "planning"]


def test_enqueue_rejects_unknown_project():
    store = MemoryControlPlaneStore()
    try:
        ProjectBootstrapOrchestrator(store).enqueue("missing")
    except KeyError as exc:
        assert "unknown project" in str(exc)
    else:
        raise AssertionError("expected KeyError")
