from lmola.workflows.catalog import WORKFLOW_CATALOG, WorkflowContract, validate_workflow_contracts


def test_all_workflows_have_valid_contracts() -> None:
    for wf_id, entry in WORKFLOW_CATALOG.items():
        contract = WorkflowContract.model_validate(entry.contract)
        assert contract.workflow_id == wf_id
        assert sorted(contract.required_backends) == sorted(entry.required_backends)
        assert contract.input_ports
        assert contract.output_ports
        assert contract.execution_policy.dry_run_default is True
        assert contract.execution_policy.requires_allow_execution is True
        assert contract.execution_policy.requires_confirm is True
        assert contract.execution_policy.low_level_direct_call_allowed is False


def test_validate_workflow_contracts_status_ok() -> None:
    payload = validate_workflow_contracts()
    assert payload["status"] == "ok"
    assert payload["missing_contracts"] == []
    assert payload["invalid_contracts"] == []
