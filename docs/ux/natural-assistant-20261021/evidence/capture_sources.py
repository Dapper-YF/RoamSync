"""Capture only audited source files; never reads env, chats, logs or databases."""
from pathlib import Path
from datetime import datetime
from zoneinfo import ZoneInfo
import hashlib
import json
import subprocess

root = Path(__file__).resolve().parents[4]
targets = {
    'web/src/main.tsx': ['DiscoveryApp'],
    'web/src/discovery/DiscoveryApp.tsx': ['JourneyPage', 'AssistantPage'],
    'web/src/journeys/JourneyPage.tsx': ['ArrangementExtras', 'selectedDayId', '准备好了'],
    'web/src/journeys/journeyApi.ts': ['JourneyAssistantContext'],
    'web/src/product/ArrangementExtras.tsx': ['setScheduling', 'scheduleChoice', '安排具体时间'],
    'web/src/product/AssistantDecisions.tsx': ['decidePreview(false)', 'const stale'],
    'web/src/product/TravelAssistant.tsx': ['routeTripSeen', 'action_target', 'session.global'],
    'web/src/data/productAssistantContext.ts': ['physical_location', 'discussing_place', 'action_target'],
    'backend/app/assistant_routes.py': ['class MessageInput', 'selected_day_id', 'decision_endpoint'],
    'backend/app/database.py': ['class AssistantSession', 'class TripArrangementItem', 'ForeignKey("trips.id", ondelete="CASCADE")'],
    'backend/app/assistant_memory.py': ['class MemoryUpdate', 'source', 'Asia/Shanghai'],
    'backend/app/assistant_arrangement.py': ['choice_command', 'apply_arrangement_message'],
    'backend/app/assistant_capabilities.py': ['planning', 'memory_updates'],
    'backend/app/assistant_service.py': ['confirm_action', 'if not accept', 'prepare_action'],
    'backend/app/assistant_turn.py': ['source_messages', 'selected_day_id'],
    'backend/app/plan_revision_service.py': ['version', 'accept'],
    'backend/app/planning_run_repository.py': ['selected_day_id', 'selected_activity_id'],
}
entries = []
for relative, needles in targets.items():
    path = root / relative
    raw = path.read_bytes()
    lines = raw.decode('utf-8-sig').splitlines()
    matches = {needle: [i for i, line in enumerate(lines, 1) if needle in line][:12] for needle in needles}
    entries.append({'path': relative, 'sha256': hashlib.sha256(raw).hexdigest(), 'lines': len(lines), 'anchors': matches})
head = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=root, text=True).strip()
status = subprocess.check_output(['git', 'status', '--porcelain', '--untracked-files=no'], cwd=root, text=True)
result = {
    'captured_at': datetime.now(ZoneInfo('Asia/Shanghai')).isoformat(),
    'canonical_root': str(root), 'head': head, 'working_tree_is_clean': not status.strip(),
    'scope': 'Current working files including prior uncommitted changes; hashes captured after audit. Not a deployed-image manifest or a before/after comparison.',
    'files': entries,
}
(Path(__file__).parent / 'source-snapshot.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
print(f'Captured {len(entries)} audited sources at {head[:12]}; no environment or database files read.')
