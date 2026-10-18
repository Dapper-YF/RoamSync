# 杭州地点内容与授权照片增量（2026-10-18）

## 结果

在已有精确地点目录中为杭州西湖风景名胜区、中国丝绸博物馆和杭州博物馆各增加一张真实授权照片，共新增 3 张照片及 6 个本地衍生文件（480px、960px）。照片按 AMap POI ID、canonical UUID、地点名、城市和坐标绑定，静态媒体由审核文件 allowlist 提供。

三个文化摘要继续使用 UNESCO、西湖馆方和杭州市文旅局来源；仅陈述已核实的文化与展陈主题。当前开放/预约、游览时长、遮雨、无障碍、实时费用及拥挤度继续明确为未知。

| 精确地点 | 照片来源与作者 | 授权 |
|---|---|---|
| 杭州西湖风景名胜区（B023B13L9M） | [West Lake Hangzhou 2016 3.jpg](https://commons.wikimedia.org/wiki/File:West_Lake_Hangzhou_2016_3.jpg)，Fredlyfish4 | CC BY-SA 4.0 |
| 中国丝绸博物馆（B023B09JLL） | [China Silk Museum, 2017-11-12 01.jpg](https://commons.wikimedia.org/wiki/File:China_Silk_Museum,_2017-11-12_01.jpg)，Siyuwj | CC BY-SA 4.0 |
| 杭州博物馆（B0FFFWQGI8） | [Hangzhou Museum 01 2018-07.jpg](https://commons.wikimedia.org/wiki/File:Hangzhou_Museum_01_2018-07.jpg)，猫猫的日记本 | CC BY-SA 4.0 |

导入时从 Commons 获取每张原图并按 API 返回的 SHA-1 校验；留存文件页、原图 URL、原图 SHA-1、作者、许可、逐图身份依据及本地 SHA-256。处理只做等比缩放和 JPEG 重编码；UI 仍显示作者、Commons 来源页和 CC 许可链接，CC BY-SA 衍生文件保持原许可。

## 验证

三个地点各自的精确 AMap ID 投影为一个照片；媒体 API 的 480/960 响应均为 JPEG，响应体哈希与目录一致。`backend/tests/test_place_images.py` 与 `backend/tests/test_reviewed_experiences.py` 共 8 项通过。Web Vitest 全套 33 个测试文件、188 项通过，其中包含照片详情/归属显示与地点内容映射用例。

验收数据见 [`review.json`](../evidence/place-content-photos-20261018/review.json)。共享 18004 服务的重启及最终产品集成由 root 执行；本切片没有部署，也没有接触正式 Trip 数据。
