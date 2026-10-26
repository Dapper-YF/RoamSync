import pathlib,tarfile,hashlib,json,difflib
A=pathlib.Path(r'E:\Study\RoamSync\backend\evals\results\planner_reliability_20261008')
W=pathlib.Path(r'E:\Study\RoamSync-planner-reliability-followup-fix-20261008')
assert not W.exists();W.mkdir()
with tarfile.open(A/'candidate26e33f7.tar') as t:t.extractall(W,filter='data')
paths=['backend/app/planning_intent_service.py','backend/tests/test_planning_intents.py']
old={p:(W/p).read_bytes() for p in paths}
p=W/paths[0];b=p.read_bytes();needle='if value == "其他日期不变":'.encode();assert b.count(needle)==1;p.write_bytes(b.replace(needle,'if re.fullmatch(r"其他日期(?:安排)?不变", value):'.encode()))
p=W/paths[1];b=p.read_bytes();needle='    "保留其他日期不变",\n'.encode();assert b.count(needle)==1
b=b.replace(needle,needle+'    "保留其他日期安排不变",\n'.encode())
b+='''
    # A real alias wins before plan-meta filtering, even when it equals a label.
    assert _resolve_protected_activities("保留其他日期安排不变", [_ActivityEntity(activity, day, date(2026, 10, 10), ("其他日期安排不变",))], None, [], target_day_id=day) == [activity]
    from app.planning_intent_service import _is_plan_meta_activity_reference
    assert not _is_plan_meta_activity_reference("其他日期安排不变博物馆")
'''.encode()
p.write_bytes(b)
patch=b'';manifest={}
for p in paths:
    new=(W/p).read_bytes();manifest[p]={'before':hashlib.sha256(old[p]).hexdigest(),'after':hashlib.sha256(new).hexdigest()}
    patch+=b'diff --git a/'+p.encode()+b' b/'+p.encode()+b'\n'
    patch+=''.join(difflib.unified_diff(old[p].decode().splitlines(keepends=True),new.decode().splitlines(keepends=True),fromfile='a/'+p,tofile='b/'+p)).encode()
(A/'proposed_intent_meta_followup.patch').write_bytes(patch)
(A/'followup_patch_manifest.json').write_text(json.dumps({'base_commit':'26e33f7ecec848403c0992953c61216ddb305fec','paths':manifest,'patch_sha256':hashlib.sha256(patch).hexdigest(),'new_scope':'One observed optional word; true aliases remain first; unknown named venues strict','applied_to_release':False},indent=2),encoding='utf-8')
print('Independent follow-up patch prepared; release untouched.')
