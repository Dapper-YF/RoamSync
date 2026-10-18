# Emulator evidence, 2026-10-15

Device: private `RoamSyncRound2`, `emulator-5554`, Android 16 / SDK 36,
x86_64 Google Play emulator. This was not a physical phone. API requests used
`adb reverse tcp:18003 tcp:18003` and a fresh one-use code entered through the
native connection page. No credential is present in these artifacts.

The cumulative native UI workflow passed with retained Draft
`d1817392-3fad-4043-90ec-61334366950e`. Creation and model calls occurred in
earlier interrupted runner segments; this was not one uninterrupted full run.
The final resume segment did not repeat either model operation.

| UI action / assertion | Evidence |
| --- | --- |
| Save preference categories and keywords; replace local text with an unsaved value; refresh and recover saved text and checkbox value | `preferences-refreshed.png`; original segment `run-1792046977069` |
| Create labelled three-day Hangzhou draft and click real generation | Retained private `run-1792047095012/03-draft-created.png`; service completed the request after runner ended |
| Edit requirements and click real model modification | Retained private `run-1792047335308`; native completed run record with `Android模拟器验收-1792047335176 修改` was asserted again in final segment |
| Save and return to list; latest card immediately says saved without manual refresh | `list-saved-without-refresh.png` |
| Reopen the draft; completed modification record and saved state remain | Final private `06-draft-reopened.png`; runner assertions passed |
| Cancel: native restore control appears; editing is disabled | `draft-cancelled.png` |
| Restore: native save/cancel controls return; saved state and plan remain | `draft-restored.png`, `draft-restored.redacted.txt` |
| Open legacy journey list read-only, then refresh | `trips-entry.redacted.txt`, `trips-refreshed.redacted.txt` |

At the draft checkpoint, the journey entry initially showed the stale startup error `请通过本地 RoamSync
页面访问`. Clicking its existing refresh button loaded retained trip cards and
removed the error. Merely opening that earlier page
was not counted as a clean journey-list load. No formal Trip, planning operation
or navigation was created by this smoke.

Final resume ran against production fix `415a6da` (draft list cache/scroll), debug
APK SHA256 `3A86CA7C07EDD1C598F2C01B9B87050EB2A4726EA320CFAFD598451C5F95FD93`.
Build: `scripts/stage2/android-build.ps1 -DeviceTests` succeeded. Both APKs were
installed with `install -r`; application data was retained.

Command (the transient code is intentionally omitted):

```powershell
adb -s emulator-5554 shell am instrument -w `
  -e pairingCode $oneUseCode -e baseUrl http://127.0.0.1:18003/ `
  -e resumeExisting true -e resumeAfterModify true `
  -e retainedMarker Android模拟器验收-1792047335176 `
  com.roamsync.app.v2preview.test/com.roamsync.app.smoke.NativeSmokeInstrumentation
```

Result: `PASS native Android UI smoke`. Final device/pulled evidence directory:
`native-smoke/run-1792048035968`. Full pulled artifacts are retained locally under
`.private-integration/android-native-evidence/`.

Earlier diagnostics remain there in `run-1792046977069`, `run-1792047095012`,
`run-1792047335308`, `run-1792047555794` and `run-1792047709941`. They expose runner
synchronization and initial-requirement-versus-run-requirement assertion mistakes,
and the actual stale list/scroll bug fixed in `415a6da`. An accessibility click
reporting failure did not prove the server received no request. Some earlier
images named `05-draft-modified` show an in-flight operation and are not completion
evidence. No earlier failed segment is presented as a full pass.

## Separate trip and AI route follow-up

Production trip-entry fix `121d889` was built and installed with `install -r`.
Debug APK SHA256:
`1F44B4F75927328B5F756840C8444208A77CA55F4F0FF64D233ED86A3D168BEB`.
Both independent modes below passed their native accessibility/data assertions;
neither touched the Draft workflow.

`-e mode trips -e expectAutoRefresh true` (`run-1792048695169`) paired, opened the
legacy trip list, waited for its retained fixture card and stable idle, and
asserted the old authorization error was absent. It never clicked refresh.
`trips-auto-refreshed.png` was visually checked: the existing card is visible and
there is no error banner. This closes the earlier entry-refresh issue.

`-e mode route` (`run-1792048760458`, marker
`Android模拟器验收-1792048760361`) used native UI to search and set the real
断桥残雪 origin, then search 灵隐寺, open its returned POI, and discuss it in AI.
The runner waited for its new marker message and clicked only a shortcut after
that message. It opened the route page and asserted both endpoint names plus the
provider route estimate. `route-entry.redacted.txt` records the exact endpoints
`杭州西湖风景名胜区-断桥残雪 → 灵隐寺-灵隐请香处` and `5585 米 · 约 74 分钟 ·
高德真实步行路线（估计）`.

The immediate screenshot `route-entry-immediate.png` has a white body; its tree
still says `正在加载地图…`. Thus the route data and native route transition passed,
but the screenshot does not prove map tiles or even the route header had finished
painting. This is a capture/loading observation, not a verified permanent map
failure. No claim is made for rendered map tiles, physical GPS, or controlled
navigation. All full local artifacts and failed runner diagnostics remain in
`.private-integration/android-native-evidence/`.

Service drafts stay labelled and retained; shared preferences are restored by the
integration owner from the pre-emulator snapshot.
