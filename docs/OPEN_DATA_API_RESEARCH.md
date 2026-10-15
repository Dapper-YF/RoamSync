# 公开数据 API 选型记录

日期：2026-09-06

## 结论

`public-apis` 更适合作为目录，不是统一服务。它收录的天气、地理编码、活动和交通
接口拥有不同的授权、覆盖范围、稳定性和许可，不能直接把目录条目当作生产依赖。

## 可选服务

| 能力 | 候选 | 当前建议 | 原因 |
|---|---|---|---|
| 天气预报 | Open-Meteo | 优先评估 | 无 API Key、支持经纬度预报，适合后端代理；需确认商业使用和请求频率 | 
| 地理编码 | OpenCage / Geocode.xyz | 暂不替换高德 | RoamSync 已使用高德城市、POI 和路线，切换会破坏地点 ID 一致性 | 
| 活动/门票 | Eventbrite | 暂不接入 | 需要 OAuth，数据覆盖和中文城市活动质量需单独验证 | 
| 航班/酒店 | Amadeus | 暂不接入 | 需要 OAuth，价格和库存是短时有效数据，必须设计供应商订单模型 | 
| 地图底图 | OpenStreetMap | 可作为底图备选 | 适合作为地图瓦片来源，但不提供 RoamSync 所需的完整路线和 POI 业务语义 | 

## 采用规则

1. 公开 API 只能由后端代理调用，不能把供应商 Key 放进 Web 包。
2. 外部数据必须保存 `provider`、`provider_id`、抓取时间、有效期和来源 URL。
3. 天气、价格、库存和活动安排必须显示时间戳，过期后不能伪装成实时数据。
4. 供应商失败时返回明确的“数据不可用”，不能回退到固定演示值。
5. 在没有真实业务需求和验收数据前，不接入多个同类供应商制造功能数量。

## 参考

- public-apis 目录：[https://github.com/public-apis/public-apis](https://github.com/public-apis/public-apis)
- Open-Meteo：[https://open-meteo.com/](https://open-meteo.com/)
- 同类产品 Turistar 的核心逻辑是“仪表盘/旅行列表 → 安全编辑器 → 按天行程”，并使用持久化存储：[https://github.com/andre-lmarinho/turistar](https://github.com/andre-lmarinho/turistar)
- OpenTripPlanner 将“地点库、旅行卡片、按天行程、地图路线”拆成连续的工作流：[https://github.com/clawnify/OpenTripPlanner](https://github.com/clawnify/OpenTripPlanner)

这些项目提供的是信息架构参考，不代表 RoamSync 可以直接复制其代码或数据许可。
