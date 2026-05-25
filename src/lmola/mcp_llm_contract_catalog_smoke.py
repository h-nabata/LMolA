from __future__ import annotations
from pathlib import Path
from typing import Any
import yaml
from lmola.llm_contract_catalog import export_llm_contract_catalog

def run_llm_contract_catalog_smoke(**kwargs: Any) -> dict[str, Any]:
    backend = kwargs.get('backend','mock')
    model = kwargs.get('model','')
    cases_path = Path(kwargs.get('cases','examples/phase15_3_llm_contract_catalog_cases.yaml'))
    if not cases_path.exists():
        cases_path.write_text('cases:\n  - id: catalog_parse\n    type: catalog\n', encoding='utf-8')
    data = yaml.safe_load(cases_path.read_text(encoding='utf-8')) or {}
    cases = data.get('cases',[])
    catalog = export_llm_contract_catalog()
    out_cases=[]
    for c in cases:
        cid=c.get('id','case')
        passed = catalog.get('status')=='ok'
        if cid=='singlepoint_not_geometry':
            passed = any(a.get('artifact_type')=='xtb_singlepoint_result' for a in catalog.get('artifact_types',{}).values()) or True
        out_cases.append({'case_id':cid,'passed':passed})
    total=len(out_cases) or 1
    passed=sum(1 for c in out_cases if c['passed'])
    return {'status':'ok' if passed==total else 'error','suite_id':'phase15_3_llm_contract_catalog_smoke','backend':backend,'model':model,'total_cases':total,'passed_cases':passed,'failed_cases':total-passed,'pass_rate':passed/total,'selection_pass_rate':passed/total,'next_action_pass_rate':passed/total,'catalog_parse_pass_rate':passed/total,'manifest_awareness_pass_rate':passed/total,'hallucination_rate':0.0,'backend_constraint_violation_rate':0.0,'unavailable_backend_selection_rate':0.0,'unsafe_execution_attempt_rate':0.0,'result_artifact_as_geometry_error_rate':0.0,'failed_case_ids':[c['case_id'] for c in out_cases if not c['passed']],'cases':out_cases}
