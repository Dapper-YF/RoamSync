# B lane evidence manifest

Product code commit: `30142f8348ffd5afd626b6b81404833e87a6b253`. Hashes below describe integration candidate `9738473`, including the coordinator-added address-query boundary test. Later official fixture-gate changes are test-only; the actual official source/test hashes used by the full regression are recorded in `../integration/official-source-freeze.json`.

## Product source SHA-256

| File | SHA-256 |
|---|---|
| `backend/app/assistant_capabilities.py` | `9FFF0A381B24A2465B5E7648F02D6F5CC6CE47480845BF5AA1A075F014CF7392` |
| `backend/app/assistant_selection_contract.py` | `D7831710FE4A0A80E5B5ED984251269E76D752F28BBBC0A94AF1A75E2FF7379C` |
| `backend/app/read_calculations.py` | `E2820160452F1260A89AF842D9BC77797649F605F8339ED110674B0C97B10263` |
| `backend/app/read_references.py` | `0A2F32AA7A687168F9EC42A6DA6022255CDD48E62C647BC596615502D49EAFCD` |
| `backend/tests/test_formal_write_protection.py` | `DD67B8734C90CEF0577380F2A3BFE1B6D6010C7DCB5F8D3280D4235C194F65E8` |
| `backend/tests/test_stage2_read_continuity.py` | `5C2192D76609C98512703B9C45AA2AD46DB60EEB05535F16FDCADD0791F32220` |
| `backend/tests/test_stage6_read_calculations.py` | `049C447541B93C488AFD0EB3494AF6BD8ABC80926DF2C918D74951AB3F82BE1A` |
| `backend/tests/test_stage6_read_focus.py` | `8873A33DF84BCC5F00AD89AD98971ECF6A9357A8FCC422B8FCF148863119C730` |

## Evidence SHA-256

| File | SHA-256 |
|---|---|
| `coordinator-targeted.xml` | `4017A3A23D73C9BC248B7C62F02B999F6B7B0F2F6FD544A9B91B859FD48A7B7E` |
| `targeted-after-estimates.xml` | `826FB8B72314FC16C7D0AFB86F27894361D260B1105CDDB0AE2B4B58C7E3C729` |
| `targeted-after.xml` | `6A9910AEDE9BE7F385A76D07F1855FD539A5E0FE9C3FBEC9AFE52AFB11C0088D` |
| `public1.json` | `2FBFBDE8DFE4196E3F136DB0E4FE01788B8F258B6AD1DA2D65C331ACB03ADE50` |
| `public2.json` | `1BEEE13ECA9C08D487F568610A516F640C06EB1FAA698A07D38403970710D99C` |
| `public_b_answers.json` | `CCF09E6780E25845F2B0D0C4CEE934D5DABEF2A41642DA156725A8F15E84346E` |

Logs ignored by `.gitignore` were explicitly added after checking for credential patterns. The two public model captures are from the common WIP baseline, not the post-fix source.
