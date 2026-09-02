import type { DayPlan, PlaceCandidate, Trip } from "../domain/types";

export const DEMO_TRIP_ID = "demo";
export const DEMO_TRIP_UUID = "00000000-0000-4000-8000-000000000001";
export const DEMO_STORAGE_KEY = "roamsync:planner:demo:v1";
export const DEMO_SCHEMA_VERSION = 2;

const source = (id: string, title: string, url: string, provider = "高德地图") => ({
  id,
  title,
  url,
  provider,
  queriedAt: "2026-08-31T10:00:00+08:00",
  confidence: "high" as const,
});

export const demoTrip: Trip = {
  id: DEMO_TRIP_ID,
  title: "杭州 · 两日慢游",
  destination: "杭州",
  startDate: "2026-09-05",
  endDate: "2026-09-06",
  totalBudgetFen: 120_000,
  dailyBudgetFen: 60_000,
  currency: "CNY",
  accommodation: "杭州湖滨银泰附近",
};

export const demoCandidates: PlaceCandidate[] = [
  {
    id: "west-lake",
    name: "西湖·断桥",
    category: "nature",
    neighborhood: "北山街",
    description: "从断桥开始沿湖慢行，适合作为第一天的低强度开场。",
    coordinates: [120.15027, 30.26012],
    suggestedDurationMinutes: 90,
    estimatedCostFen: 0,
    rating: 4.8,
    tags: ["湖景", "步行", "免费"],
    source: source("src-west-lake", "西湖风景名胜区", "https://www.amap.com/place/B023B0A1UN"),
  },
  {
    id: "lingyin",
    name: "灵隐寺",
    category: "culture",
    neighborhood: "灵隐路",
    description: "山林寺院组合，建议预留半天并避开午后返程高峰。",
    coordinates: [120.10141, 30.24094],
    suggestedDurationMinutes: 150,
    estimatedCostFen: 7500,
    rating: 4.7,
    tags: ["古建", "山林", "门票"],
    source: source("src-lingyin", "灵隐景区", "https://www.amap.com/place/B023B0A6YT"),
  },
  {
    id: "longjing",
    name: "龙井村",
    category: "nature",
    neighborhood: "龙井路",
    description: "茶山与村落路线，适合天气晴朗时安排在上午。",
    coordinates: [120.10068, 30.22019],
    suggestedDurationMinutes: 120,
    estimatedCostFen: 3000,
    rating: 4.5,
    tags: ["茶山", "轻徒步", "拍照"],
    source: source("src-longjing", "龙井村", "https://www.amap.com/place/B023B0A3P9"),
  },
  {
    id: "china-art-academy",
    name: "中国美术学院美术馆",
    category: "culture",
    neighborhood: "南山路",
    description: "靠近湖滨，作为雨天或高温时的室内替代节点。",
    coordinates: [120.15825, 30.24703],
    suggestedDurationMinutes: 90,
    estimatedCostFen: 0,
    rating: 4.6,
    tags: ["展览", "室内", "预约"],
    source: source("src-art", "中国美术学院美术馆", "https://www.caa.edu.cn", "官方网站"),
  },
  {
    id: "hefang-street",
    name: "河坊街",
    category: "shopping",
    neighborhood: "清河坊",
    description: "老街夜游节点，餐饮与购物花费弹性较大。",
    coordinates: [120.17429, 30.23852],
    suggestedDurationMinutes: 75,
    estimatedCostFen: 8000,
    rating: 4.3,
    tags: ["夜游", "小吃", "老街"],
    source: source("src-hefang", "清河坊历史文化街区", "https://www.amap.com/place/B023B0A0FH"),
  },
  {
    id: "green-tea",
    name: "绿茶餐厅·湖滨店",
    category: "food",
    neighborhood: "湖滨商圈",
    description: "方便衔接湖滨行程的正餐候选，演示预算预估用途。",
    coordinates: [120.16588, 30.25772],
    suggestedDurationMinutes: 70,
    estimatedCostFen: 9000,
    rating: 4.4,
    tags: ["杭帮菜", "正餐", "排队"],
    source: source("src-food", "绿茶餐厅", "https://www.amap.com/search?id=B0FFG5M5P1"),
  },
  {
    id: "leifeng-pagoda",
    name: "雷峰塔",
    category: "sight",
    neighborhood: "南山路",
    description: "可俯瞰西湖，适合在日落前到达。",
    coordinates: [120.14852, 30.23111],
    suggestedDurationMinutes: 75,
    estimatedCostFen: 4000,
    rating: 4.5,
    tags: ["地标", "日落", "门票"],
    source: source("src-leifeng", "雷峰塔景区", "https://www.amap.com/place/B023B0A4LM"),
  },
  {
    id: "xiaohe-park",
    name: "小河公园",
    category: "sight",
    neighborhood: "拱墅区",
    description: "运河边工业遗存更新空间，适合第二天下午慢行。",
    coordinates: [120.14236, 30.31524],
    suggestedDurationMinutes: 80,
    estimatedCostFen: 0,
    rating: 4.6,
    tags: ["建筑", "运河", "免费"],
    source: source("src-xiaohe", "小河公园", "https://www.amap.com/place/B0H6JMM4T8"),
  },
];

const activity = (
  id: string,
  placeId: string,
  scheduledTime: string,
  durationMinutes?: number,
) => {
  const place = demoCandidates.find((candidate) => candidate.id === placeId);
  if (!place) throw new Error(`Unknown demo place: ${placeId}`);
  return {
    id,
    placeId,
    name: place.name,
    originalName: place.name,
    category: place.category,
    neighborhood: place.neighborhood,
    coordinates: place.coordinates,
    scheduledTime,
    durationMinutes: durationMinutes ?? place.suggestedDurationMinutes,
    estimatedCostFen: place.estimatedCostFen,
    status: "planned" as const,
    scheduleLocked: false,
    version: 1,
    updatedAt: "2026-08-31T00:00:00Z",
    source: place.source,
  };
};

export const demoDays: DayPlan[] = [
  {
    id: "day-1",
    tripId: DEMO_TRIP_ID,
    date: "2026-09-05",
    label: "第 1 天",
    theme: "湖滨散步与城市夜色",
    activities: [
      activity("activity-west-lake", "west-lake", "09:30"),
      activity("activity-china-art-academy", "china-art-academy", "13:30"),
      activity("activity-hefang-street", "hefang-street", "18:20"),
    ],
  },
  {
    id: "day-2",
    tripId: DEMO_TRIP_ID,
    date: "2026-09-06",
    label: "第 2 天",
    theme: "山林茶村与从容返程",
    activities: [
      activity("activity-lingyin", "lingyin", "08:40"),
      activity("activity-longjing", "longjing", "13:20"),
    ],
  },
];
