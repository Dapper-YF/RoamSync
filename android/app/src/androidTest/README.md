# Native Android device smoke

`NativeSmokeInstrumentation` uses Android's `Instrumentation` and `UiAutomation`
accessibility APIs. It launches the actual `MainActivity`, edits visible native
fields and clicks the existing product controls. It adds no production backdoor
and requires no additional test libraries.

Build both APKs using `scripts/stage2/android-build.ps1 -DeviceTests`, then install
`app-debug.apk` and `app-debug-androidTest.apk` on the selected Android device.
Connect the isolated API through `adb -s <serial> reverse tcp:18003 tcp:18003`.
Obtain a fresh one-use pairing code immediately before starting:

```powershell
adb -s <serial> shell am instrument -w `
  -e baseUrl http://127.0.0.1:18003/ -e pairingCode $oneUseCode `
  com.roamsync.app.v2preview.test/com.roamsync.app.smoke.NativeSmokeInstrumentation
```

The normal flow saves travel preferences, changes the local field without saving,
refreshes to prove the saved value was fetched again, creates a labelled draft,
generates and modifies it, saves it, reopens it, cancels it and restores it. Model
operations allow 240 seconds each; a busy screen is observed without clicking its
disabled controls. The final legacy trip list check only opens and refreshes the
list. It does not create a formal Trip or start planning/navigation.

Optional arguments:

- `-e mode inspect`: read the initial native accessibility tree without pairing.
- `-e resumeExisting true`: skip preferences, creation and initial generation;
  open the first/newest Hangzhou draft in the native list. This is only for a
  previously retained labelled smoke draft; its requirements must include
  `Android模拟器验收`. Continue modification, save, reopen, cancel and restore.
- `-e resumeAfterModify true` together with `resumeExisting`: when a previous
  UI-triggered model modification has completed on the service after a runner
  interruption, read its labelled requirements and continue save/reopen/cancel/
  restore without issuing another model operation. Also pass `-e retainedMarker`
  with that run's non-secret `Android模拟器验收-...` label. Modification requirements
  are asserted in the native completed run record; the edit field continues to
  show the draft's initial requirements after a reload.
- `-e mode route`: after pairing, exercise the native AI place-card route shortcut.
  This optional check needs live place/model/route services and is reported
  separately from the draft smoke.
- `-e mode trips -e expectAutoRefresh true`: after pairing, only open the legacy
  trip list. Wait for the retained fixture card and stable idle, assert the stale
  authorization error disappeared automatically, and capture evidence without
  clicking refresh. No draft/model operation is performed. The fixture card title
  can be selected with `-e retainedTripTitle`.
- `-e assistantRoute true`: add that route check after the draft flow.

Screenshots are captured only after pairing has completed and its input has been
cleared. Diagnostic tree dumps redact editable values. The runner prints the
device evidence directory under the target app's external `files/native-smoke/`;
pull that exact ASCII `run-...` directory using `adb pull`. The pairing code and
temporary access token are never written into the evidence. Service test drafts
are explicitly labelled and retained. Restore shared preferences separately from
the isolated service's pre-test snapshot.

On a phone that blocks the instrumentation process from launching an activity
in the background, start the runner and then foreground the installed preview
with `adb -s <serial> shell am start -n com.roamsync.app.v2preview/com.roamsync.app.MainActivity`
before its 30-second launch timeout. Unlock the phone first. Temporarily keeping
it awake while USB is connected prevents a model wait from ending at the lock
screen; record and restore the previous device setting after testing. Installation
prompts and USB debugging authorization must be allowed on the phone.

Route mode captures both its immediate frame and a second screenshot after
25 seconds, beyond the map's 20-second loading/error boundary. A successful
route assertion alone does not establish that map tiles rendered.

A successful emulator run is evidence for Android framework/native UI behavior on
that emulator. It is not evidence for a physical phone, GPS, navigation, or a
rendered live map. Inspect the screenshots and service run records before making
those claims. Earlier runner synchronization failures must remain distinguishable
from product failures and completed service-side model calls.
