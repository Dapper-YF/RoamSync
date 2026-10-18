# Physical phone evidence, 2026-10-15

Physical device model 23113RKC6C, Android 16. The preview application uses the
same isolated Web/API service on 3002/18003, USB reverse and one-use pairing.
No long-term service credential is embedded in the APK. Pairing inputs and
temporary bearer tokens are excluded from these artifacts.

Retained native UI Draft: `8848281b-18a8-4d48-bf02-0ebbb19c49c9`.
The test runner's historical `Android模拟器验收` label is reused in its content;
this directory records an actual physical phone, not emulator evidence.

- Preference categories and interests saved, local unsaved text replaced, then
  refreshed from the server and asserted: `preferences-refreshed.png`.
- Three-day undated Draft created through native UI and real model generation
  completed in about 28 seconds: `draft-generated.png`.
- First real-model modification failed; original plan and failed run remained
  visible: `draft-modification-failed.png`. A second native modification was
  submitted and also failed. Neither failure is reported as a successful edit.
- The second runner ended early on a disabled refresh control while the request
  continued server-side. The test now observes that busy state without clicking
  disabled controls. These are segmented checks, not one uninterrupted pass.
- An incorrect native footer saying content was updated after a failed run was
  fixed to use this request's returned status. A regression checks that an older
  completed run cannot make the current failed modification look successful.

After rebuilding the isolated API with `9a2fb8c`, the same native Draft was
modified successfully in 16.75 seconds. Native UI then saved it, returned to
the list (saved status visible without manual refresh), reopened it, cancelled
and restored it. Final API read: version 12, active, saved, three relative days
with two items each; latest run completed with source=model. Earlier failed
runs remain. Evidence: `draft-modified.png`, `draft-list-saved.png`,
`draft-reopened.png`, `draft-cancelled.png`, `draft-restored.png`.
Successful segment: `run-1792065639265`, modification marker
`Android模拟器验收-1792065639228`.

The service now explicitly passes its configured high reasoning effort instead
of relying on the client's implicit max default, and logs only safe error
metadata. The original two failures had no diagnostic logs, so their exact
causes remain unknown. A subsequent successful retry does not establish a sole
cause or guarantee that the external model cannot fail again.

Native AI route segment `run-1792065148176` used fresh real place/model/route
responses. The newest AI message's shortcut opened the route from 杭州西湖风景名胜区-断桥残雪
to 灵隐寺-灵隐请香处, 5585 m, about 74 minutes. `ai-route-loading.png`
is the first frame; `ai-route-map-rendered.png` shows real map tiles, both
numbered markers and the route line after loading. The latter capture occurred
during a task foreground/recents transition after the phone had locked; it
establishes map rendering, not uninterrupted foreground operation or GPS navigation.

Read-only legacy trip segment `run-1792065751121` passed: pairing, entering
旅程, automatically loading retained cards and clearing the stale authorization
error without pressing refresh. Evidence: `trips-auto-refreshed.png`.

After the phone flows, all seven protected-history checks reported zero changed
or missing rows and the formal Trip count stayed 182. Shared preferences match
the private pre-phone snapshot; the temporary keep-awake setting was restored
to its original value 0. The test Draft, failed runs and successful retry remain.

Initial runner starts also encountered phone lock screen/background launch and
USB authorization interruptions. Foregrounding the app and unlocking the phone
are environment prerequisites, not product workflow successes.

APK after the failure-notice fix:
`0575445160593443449CA91E58274AAE798C77213CD56DC8B155611042B95429`.
Android build, test APK build and 40 unit tests passed. Formal Trip count remains
182 and protected baseline row hashes remained unchanged at the recorded check.
