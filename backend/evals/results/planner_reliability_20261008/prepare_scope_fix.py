import pathlib,tarfile,hashlib,json,difflib
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-decision-context-scope-fix-20261008')
if not W.exists():
    W.mkdir()
    with tarfile.open(A/'candidate4a523b7.tar') as t:t.extractall(W,filter='data')
paths=['backend/app/decision_context.py','backend/tests/test_decision_context.py']
old={p:(W/p).read_bytes() for p in paths}
p=W/paths[0];b=p.read_bytes()
needle=b'    target_days = [\n'
new='''    recovery = context.get("execution_recovery") or {}
    execution = recovery.get("execution_state") or {}
    execution_reference_ids = {str(execution[key]) for key in (
        "current_activity_id", "navigation_target_activity_id", "first_impacted_activity_id",
    ) if execution.get(key)}
    # Keep referenced execution days as immutable context, even for a request
    # targeting a different day. Never hide global execution pointers.
'''.encode()
assert b.count(needle)==1;b=b.replace(needle,new+needle)
needle=b'        if not target_ids or str(day.get("id")) in target_ids\n';assert b.count(needle)==1
b=b.replace(needle,needle+'        or any(str(activity["id"]) in execution_reference_ids for activity in day.get("activities", []))\n'.encode())
needle=b'    recovery = context.get("execution_recovery") or {}\n';assert b.count(needle)==2
# Remove the original later copy, keeping the one inserted before scope selection.
offset=b.index(b'    activities = [activity')
b=b[:offset]+b[offset:].replace(needle,b'',1)
needle=b'    protected_sources: dict[str, set[str]] = defaultdict(set)\n';assert b.count(needle)==1
b=b.replace(needle,needle+'''    for day in target_days:
        if target_ids and str(day.get("id")) not in target_ids:
            for activity in day.get("activities", []):
                protected_sources[str(activity["id"])].add("outside_requested_scope")
'''.encode());p.write_bytes(b)
p=W/paths[1];p.write_bytes(p.read_bytes()+'''

def _cross_day_context():
    from copy import deepcopy
    context, goals, resolution = _context()
    extra = deepcopy(context["days"][0]["activities"][-1])
    extra.update(id="future-editable", status="planned", schedule_locked=False)
    context["days"].append({"id": "day-2", "date": "2026-10-21", "route_legs": [], "activities": [extra]})
    unrelated = deepcopy(extra)
    unrelated["id"] = "unrelated-editable"
    context["days"].append({"id": "day-3", "date": "2026-10-22", "route_legs": [], "activities": [unrelated]})
    goals["target_days"] = ["2026-10-21"]
    resolution["grounded_intent"]["target_day_ids"] = ["day-2"]
    return context, goals, resolution


def test_other_day_request_keeps_execution_references_as_readonly_context():
    from copy import deepcopy
    context, goals, resolution = _cross_day_context()
    before = deepcopy(context)
    result = build_decision_context(context=context, goals=goals, resolution=resolution)
    assert context == before
    assert result["goal_context"]["target_days"] == ["2026-10-21"]
    assert {day["day_id"] for day in result["formal_itinerary"]["days"]} == {"day-1", "day-2"}
    assert result["protected_constraints"]["editable_activity_ids"] == ["future-editable"]
    execution_ids = {activity["id"] for activity in context["days"][0]["activities"]}
    assert execution_ids <= set(result["protected_constraints"]["protected_activity_ids"])
    for activity_id in execution_ids:
        assert "outside_requested_scope" in result["protected_constraints"]["provenance"][activity_id]
    assert result["execution_context"]["current_activity"]["name"] == "当前活动"
    assert result["execution_context"]["navigation_target"]["name"] == "导航目标"
    assert result["execution_context"]["first_impacted_activity_id"] == "activity-target"
    assert_decision_context_invariants(result)


@pytest.mark.parametrize("reference", ["current_activity_id", "navigation_target_activity_id", "first_impacted_activity_id"])
def test_other_day_request_still_rejects_truly_unknown_execution_references(reference):
    context, goals, resolution = _cross_day_context()
    context["execution_recovery"]["execution_state"][reference] = "unknown-activity"
    with pytest.raises(DecisionContextInvariantError) as error:
        build_decision_context(context=context, goals=goals, resolution=resolution)
    assert "execution_references_unknown_activity" in error.value.codes
'''.encode())
patch=b'';manifest={}
for p in paths:
    new=(W/p).read_bytes();manifest[p]={'before':hashlib.sha256(old[p]).hexdigest(),'after':hashlib.sha256(new).hexdigest()}
    patch+=b'diff --git a/'+p.encode()+b' b/'+p.encode()+b'\n'
    patch+=''.join(difflib.unified_diff(old[p].decode().splitlines(keepends=True),new.decode().splitlines(keepends=True),fromfile='a/'+p,tofile='b/'+p)).encode()
(A/'proposed_decision_context_scope_fix.patch').write_bytes(patch)
(A/'scope_fix_patch_manifest.json').write_text(json.dumps({'base_commit':'4a523b7bd91df6c7c77c06cff87b2ff6a36a80de','paths':manifest,'patch_sha256':hashlib.sha256(patch).hexdigest(),'invariant_function_unchanged':True,'candidate_validator_unchanged':True,'graph_unchanged':True,'production_untouched':True},indent=2),encoding='utf-8')
print('Independent scoped-context patch prepared; strict invariant function untouched.')
