# Reviewed media audit — 2026-10-24

Scope: the isolated conversation-itinerary branch, without deployment or production database access. The new image is a historical photograph; it makes no claim about present opening hours, businesses, availability or crowd conditions.

## New whole-POI binding

VERIFIED: an authenticated request to the isolated public search/detail API on port 18058 returned the following real AMap identity. No private conversations were read.

| Field | Verified value |
|---|---|
| Scenic-area name | 宽窄巷子景区 |
| Canonical place ID | `8ca144f2-f437-5d2e-a38a-9b77c7363e0b` |
| AMap provider ID | `B001C7YCM4` |
| City/category | 成都市 / attraction |
| GCJ02 longitude, latitude | `104.053307, 30.663869` |
| Address | 少城街道金河路口宽窄巷子 |
| Provider source | [AMap exact POI](https://www.amap.com/search?id=B001C7YCM4) |
| Detail retrieval | `2026-10-24T01:59:44.794969Z`, fresh provider identity |

The category-free literal keyword search distinguished this whole scenic area from the metro `BV10536811`, the merchant `B0FFIL06X6`, the sub-site `B0FFHQRM8G` and the B entrance `B0FFHXLNMY`. These identities cannot use the new image. Name, canonical/provider identity, city and coordinate guards remain unchanged. Existing bindings for other destinations were not expanded.

## Photograph provenance and transformation

VERIFIED: [Commons file description](https://commons.wikimedia.org/wiki/File:Street_scene_-_Kuanzhai_Alleys_-_Chengdu,_China_-_DSC05311.jpg), its imageinfo metadata and its file category identify the Kuanzhai Alleys in Chengdu. The author is [Daderot](https://commons.wikimedia.org/wiki/User:Daderot); the upload declares the author's own work under [CC0 1.0](https://creativecommons.org/publicdomain/zero/1.0/deed.en). The recorded capture date is 2015-09-25. Manual visual inspection confirmed a street scene in the alley complex, rather than a metro station or a photograph of one merchant used as the whole attraction.

The original is 5472×3648 pixels and 12,340,623 bytes. Its downloaded SHA-1 matches Commons imageinfo:

```
original SHA-1   d85ed6d21e60ae8040959da487974b4b68bf65fa
original SHA-256 378f1bcd193b382d881070935b31c3fc5662c16925e11433e4b68b309c2df25b
```

The source image was converted to RGB and resized proportionally from the original with Pillow 12.2.0, LANCZOS, JPEG quality 85, optimize/progressive enabled, with EXIF removed. No content was generated, added or removed. The UI may crop a cover image; the catalog discloses resizing/compression and possible cover cropping.

| Local asset | Pixels | Bytes | SHA-256 |
|---|---|---:|---|
| `chengdu-kuanzhai-0-480.jpg` | 480×320 | 48,356 | `95cf902451cbe9fdf91c056c46eca78b131b7cb89f75eb2be16c47665db453da` |
| `chengdu-kuanzhai-0-960.jpg` | 960×640 | 175,050 | `1d0a38b1e1b6aaf03bf69d0f7ae74d1d5a2b6c70036719452911358f5a6b6649` |

Only these small variants enter the repository. The original and public-provider responses remain in the external isolated evidence directory.

## Existing catalog recheck

MEASURED: all 13 catalog photographs, including this addition, were fetched together from the primary Commons imageinfo API. Every original SHA-1, author and selected license matched the stored catalog. There are three CC0 photographs, nine CC BY-SA 4.0 photographs and one CC BY-SA 3.0 photograph. Existing images retain their individual prior review records and exact POI guards; no new location association was inferred from a similar name or nearby coordinates.

All 26 local variants matched their catalog byte counts and SHA-256 values and decoded as JPEG images. Existing attribution, license links and transformation notices remain attached to each media DTO. CC BY-SA variants keep their selected source license.

The media tests verify exact canonical/provider binding, exclusion of nearby sub-sites/metro/merchants, local HTTP asset responses, complete license attribution, city scoping, removal/missing-file behavior and every local asset digest. These fixture checks establish media projection/integrity; the complete model→candidate→adoption product acceptance is reported separately.

## Evidence locations

Public-source metadata and download digest evidence are retained outside Git at:

`E:/Study/RoamSync-conversation-redesign-evidence-20261023/task5-kuanzhai-media-audit/`

The directory contains `commons-description.md`, `commons-imageinfo.json`, `all-catalog-commons-imageinfo.json`, `catalog-license-audit.json`, the original JPEG, `amap-keyword-search.json`, `amap-exact-detail.json` and `approved-media-record.json`. Provider credentials, environment files and private chat records are absent.
