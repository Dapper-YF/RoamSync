"""Port only this task's additive changes onto the extracted live API source."""
from pathlib import Path
import hashlib
import json
import shutil

root = Path(__file__).resolve().parent
repo = root.parents[3]
app = root / 'release' / 'app'
original = root / 'runtime_original'
original.mkdir(exist_ok=True)
for path in app.glob('*.py'):
    shutil.copy2(path, original / path.name)

def replace(name, old, new):
    path = app / name
    value = path.read_text(encoding='utf-8')
    assert value.count(old) == 1, (name, old, value.count(old))
    path.write_text(value.replace(old, new), encoding='utf-8')

replace('companion_contracts.py', '"current_reconstruction", "rationale_unavailable"]',
        '"current_reconstruction", "rationale_unavailable", "saved_plan_notes"]')
replace('companion_contracts.py', '        return self\n\n\nclass CompanionComparison',
        '        if self.explanation_type == "saved_plan_notes" and (not self.source_decision_ref or not self.reasons or not self.fact_freshness_warning):\n'
        '            raise ValueError("saved plan notes require provenance and an explicit verification limitation")\n'
        '        return self\n\n\nclass CompanionComparison')
replace('companion_contracts.py', '    referenced_decision: CompanionExplanation | None = None\n',
        '    referenced_decision: CompanionExplanation | None = None\n    saved_plan_notes: dict | None = None\n')
replace('companion_context.py', '            if need.decision_history_required and len(rows) == 1:',
        '            if (need.decision_history_required and len(rows) == 1\n'
        '                and (rows[0].custom_name or rows[0].name) in context.current_message\n'
        '                and not re.search(r"候选|待确认|新方案", context.current_message)):')
replace('companion_context.py', '        return context.model_copy(update=changes)',
        '        if need.decision_history_required and not context.resolved_entities:\n'
        '            from app.saved_plan_notes import read_saved_plan_notes\n'
        '            changes["saved_plan_notes"] = await read_saved_plan_notes(self._session, self._trip_id, context.current_message)\n'
        '        return context.model_copy(update=changes)')
graph = (repo / 'backend/app/companion_graph.py').read_text(encoding='utf-8')
begin = graph.index('            elif context.saved_plan_notes:')
end = graph.index('            elif len(selected)', begin)
replace('companion_graph.py', '            elif len(selected) == 1 and selected[0].reasons',
        graph[begin:end] + '            elif len(selected) == 1 and selected[0].reasons')
replace('assistant_service.py', '        row.latest_run_id = None\n        row.messages = [*row.messages, {"id": str(message_id), "user": message, "assistant": result.response_text,',
        '        row.messages = [*row.messages, {"id": str(message_id), "user": message, "assistant": result.response_text,')
shutil.copy2(repo / 'backend/app/saved_plan_notes.py', app)
(root / 'release/tests').mkdir(exist_ok=True)
shutil.copy2(repo / 'backend/tests/test_saved_plan_notes.py', root / 'release/tests')
manifest = {'base_api_image': 'sha256:60723c02c240875e3956744440ab19ea609dcf8ca31b6668a00845b57c2ef7a5',
            'files': {str(p.relative_to(root)): hashlib.sha256(p.read_bytes()).hexdigest()
                      for folder in [original, app, root / 'release/tests'] for p in folder.glob('*.py')}}
(root / 'hotfix_source_manifest.json').write_text(json.dumps(manifest, indent=2), encoding='utf-8')
