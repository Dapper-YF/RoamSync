# C lane evidence manifest

Product commit: `098ae6bf4bd6d3ac75395186c8d3902a9f6a7912` from common WIP `8e53fd68d91720f1cf1674a97483e67f9bff8bf3`.

SHA256 of product files:

| File | SHA256 |
|---|---|
| `backend/app/saved_operation_bindings.py` | `48852061B465BBE0FA1992899A4D03EFC291610F08716DFEA3881F938C8D2A9B` |
| `backend/tests/test_agent_b2_planning_snapshot.py` | `16D9FE8C69AA7AD5E0FFF7C4C4EBF7C6DE40E412248B393F5A43AC60BEF61BA5` |
| `backend/tests/test_conversation_regressions.py` | `B09B1E0FFF987A545FA2C38234AA1A0C0A828E85AD7F4BF617CA165E6AB45A2F` |
| `web/vite.config.ts` | `BFB128BD40BBB3184B3309EF222D856650F36F10CA4B489CDE860B85CD832CE6` |

| Evidence file | SHA256 | Meaning |
|---|---|---|
| `backend-before.log` | `11DF86C4349E8D3273B318B98B4DB0CAD72D6925BC16C2E5D9F5B62B4E150F70` | 11 snapshot fixture failures before edit |
| `quantity-before.log` | `9FA330141EA7AA7B4D8DE9D032622BBA18D4DEE92A56D776E26CC7BB3B3C6438` | quantity classified as duration before edit |
| `backend-after1.log` | `E16FDED645A63FC48E149E572AEB7FFDBABC65692D15C18911448B2B1399087A` | intermediate fake query error; retained |
| `backend-after-final.log` | `8F5B5DE344EC05E1D15793A7F669617E930DD6E2801AD886FB417FCC3226C223` | 21 passed in 5.27s |
| `backend-after-final.xml` | `0E7AB9FC259336834462FC3039BC73F1970AF4718203E46E83CFB57603431E21` | pytest JUnit |
| `web-navigation-before.log` | `531E3AA5443125974B9968CC0A5A2D4925EFA3434B8E9E61ECFC9C2C79C9A8EB` | targeted pre-config 2 passed; key case 3963ms |
| `web-navigation-after.log` | `4A23674A39577B5EDFB32C5106A98D05EB34546A4191ABC2B9047E9279BA9A8E` | 7 passed under config; key case 2795ms |
| `web-typecheck.log` | `5F524A5A892CB612D21ED806A906356E4C528B99B873E71F3BB9FE76A076037D` | tsc exit 0 |
| `run_tests.py` | `34B404A829BF4B391EA9EB2515B59CF045B09AFA5C61B927F9D53BC08CC6FFF7` | copied Stage6 harness retargeted to C tree and C DB |

Historical retained failure and bounded replay already in `docs/evidence/product-closeout-stage5-20261025/photos-web-full.log`, `photos-navigation-isolated.log`, `photos-web-bounded.log`; batch3 full backend XML/log are external at `E:/Study/RoamSync-stage6-evidence-20261025/`. No `private-sealed` file was read. C did not run real provider or browser experiments.
