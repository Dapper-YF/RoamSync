from pathlib import Path
out=Path(__file__).parent
src=Path('E:/Study/RoamSync-stage3-evidence-20261024/verify_real_objects_final.py').read_text(encoding='utf-8')
src=src.replace("E:/Study/RoamSync-stage3-evidence-20261024/batch6/real-object-safety-final.json",(out/'real-object-safety-final.json').as_posix())
src=src.replace("FREEZE = OUT.parent/'freeze.json'", "FREEZE = OUT.parent/'safety-freeze.json'")
src=src.replace("roamsync_agent_b3_stage3_batch4_after5_test", "roamsync_agent_b3_stage4_safety_template_test")
src=src.replace("roamsync_agent_b3_stage3real2_", "roamsync_agent_b3_stage4_real_")
src=src.replace("'provenance':'batch4/real-after5.json actual GLM+AMap Run/Revision; no candidate seeding or table edits'",
    "'provenance':'runtime-final/browser-states/pending60.json exact captured GLM+AMap pending Run/Revision; restore receipt verifies equality; no constructed candidate'")
src=src.replace('from app.schemas import CandidatePlanSnapshot', 'from app.schemas import CandidatePlanSnapshot\nfrom app.revision_presentation import revision_presentation_hash')
src=src.replace('rid,tid=revision.id,revision.trip_id', 'rid,tid=revision.id,revision.trip_id\n            presented_hash=revision_presentation_hash(revision)')
src=src.replace('accept_plan_revision(db,rid)', 'accept_plan_revision(db,rid,expected_presentation_hash=presented_hash)')
src=src.replace("rid,'trip_id':tid", "rid,'trip_id':tid,'presentation_hash':presented_hash")
(out/'verify_real_objects_stage4.py').write_text(src,encoding='utf-8')
compile(src,'verify_real_objects_stage4.py','exec')
