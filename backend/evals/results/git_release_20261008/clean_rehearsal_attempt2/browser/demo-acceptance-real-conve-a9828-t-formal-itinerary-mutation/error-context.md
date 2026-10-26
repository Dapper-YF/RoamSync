# Instructions

- Following Playwright test failed.
- Explain why, be concise, respect Playwright best practices.
- Provide a snippet of code with the fix, if possible.

# Test info

- Name: demo-acceptance.spec.ts >> real conversation reaches validated candidate without formal itinerary mutation
- Location: e2e\demo-acceptance.spec.ts:7:1

# Error details

```
Error: Run failed: planner_research_invalid_output
```

# Page snapshot

```yaml
- main [ref=e3]:
  - generic [ref=e4]:
    - generic [ref=e5]:
      - text: 当前旅行
      - combobox "当前旅行" [ref=e6]:
        - option "南京历史文化老街巷三日游" [selected]
    - link "打开完整工作台 ↗" [ref=e7] [cursor=pointer]:
      - /url: /trips/5f3846c6-633c-425a-84ef-51496f488322?ai=1
  - complementary "旅程总管" [ref=e9]:
    - generic [ref=e10]:
      - generic [ref=e16]:
        - generic [ref=e17]: 旅行对话助手
        - heading "旅程总管" [level=2] [ref=e18]
      - generic [ref=e19]:
        - link "打开监控台" [ref=e20] [cursor=pointer]:
          - /url: /dev/agent-monitor?trip=5f3846c6-633c-425a-84ef-51496f488322
        - button "关闭旅程总管" [ref=e23] [cursor=pointer]
      - paragraph [ref=e27]: 聊聊目的地、旅行体验，也可以问问旅途中的问题。
      - generic [ref=e28]: 围绕这趟旅行，随时聊聊
    - generic [ref=e30]:
      - generic [ref=e35]:
        - strong [ref=e36]: 今天想聊点什么？
        - paragraph [ref=e37]: 可以聊聊目的地、旅行灵感和出行方式，想规划时再告诉我。
      - group [ref=e38]:
        - generic "对话与方案记录" [ref=e39] [cursor=pointer]
      - generic [ref=e47]:
        - generic [ref=e48]: 请根据可靠资料介绍南京的历史文化和老街巷；如果资料不足就说明，不要猜。
        - generic [ref=e49]:
          - generic [ref=e50]: 现有来源不足以核实这个问题。可以补充具体出处，或改为一般介绍。
          - group [ref=e51]:
            - generic "Thinking · 回答说明" [ref=e52] [cursor=pointer]
      - generic [ref=e53]:
        - generic [ref=e54]: 南京明天下午天气怎么样？
        - generic [ref=e55]:
          - generic [ref=e56]: 我现在没有拿到可靠的地点坐标，无法核实天气预报。
          - group [ref=e57]:
            - generic "Thinking · 回答说明" [ref=e58] [cursor=pointer]
      - generic [ref=e59]:
        - generic [ref=e60]: 你好
        - generic [ref=e61]:
          - generic [ref=e62]: 你好呀～接着刚才聊的南京：老门东的青砖小巷、夫子庙—秦淮河的傍晚灯影，还有朝天宫一带的市井老街，都很适合一个人慢慢逛。节奏上保持“一天一个主题”就轻松自在。想继续聊聊哪一块？比如南京的老街巷细节，或者换个方向找点新灵感都可以。
          - group [ref=e63]:
            - generic "Thinking · 回答说明" [ref=e64] [cursor=pointer]
      - generic [ref=e65]:
        - generic [ref=e66]: 最近想出去玩，一个人有点怕无聊，先聊聊，不要创建旅行。
        - generic [ref=e67]:
          - generic [ref=e68]: 接着刚才的话题继续聊～一个人在南京其实很难无聊：老门东的青砖窄巷可以慢慢走慢慢拍，带点生活气息；傍晚去夫子庙—秦淮河边散步，灯影映在水面上，是独旅里很有氛围感的一段。朝天宫附近的老街市井味也很足，适合找个角落看人来人往。节奏上记住“一天一个主题”就不会累：上午逛一个历史街区或博物馆，下午咖啡馆或书店歇脚写写笔记，傍晚沿河走走。想一个人也热闹点的话，可以留意当地的一日徒步或美食小团，很容易顺路认识同好。
          - group [ref=e69]:
            - generic "Thinking · 回答说明" [ref=e70] [cursor=pointer]
      - generic [ref=e71]:
        - generic [ref=e72]: 南京怎么样？我喜欢历史文化和老街巷，想轻松一点。
        - generic [ref=e73]:
          - generic [ref=e74]: 南京很适合你的偏好。它是有深厚历史底蕴的六朝古都，明城墙、夫子庙、总统府、众多博物馆都集中市区，历史密度高又不显得赶。老街巷方面，老门东的青砖窄巷和传统民居最有味道，夫子庙—秦淮河一带白天逛老街、傍晚看灯影，朝天宫周边则更有市井生活气息。喜欢轻松的话，保持一天一个主题：上午逛一处历史街区或博物馆，下午找家咖啡馆或书店歇脚，傍晚沿秦淮河散步，一个人也不累。拍照上，老门东窄巷砖墙白天顺光出片，傍晚拍秦淮河灯影倒影最有氛围感。
          - group [ref=e75]:
            - generic "Thinking · 回答说明" [ref=e76] [cursor=pointer]
      - generic [ref=e77]:
        - generic [ref=e78]: 请根据可靠资料介绍南京的历史文化和老街巷；如果资料不足就说明，不要猜。
        - generic [ref=e79]:
          - generic [ref=e80]: 现有来源不足以核实这个问题。可以补充具体出处，或改为一般介绍。
          - group [ref=e81]:
            - generic "Thinking · 回答说明" [ref=e82] [cursor=pointer]
      - generic [ref=e83]:
        - generic [ref=e84]: 南京明天下午天气怎么样？
        - generic [ref=e85]:
          - generic [ref=e86]: 南京（城市级预报），2026年10月09日的 Open-Meteo 小时预报（Asia/Shanghai）： 12:00–13:00：预计气温24°C，降水概率0% 13:00–14:00：预计气温24.4°C，降水概率0% 14:00–15:00：预计气温24.4°C，降水概率0% 15:00–16:00：预计气温24.2°C，降水概率0% 16:00–17:00：预计气温23.7°C，降水概率0% 17:00–18:00：预计气温22.3°C，降水概率0% 这是10月08日 08:36获取、通过15分钟新鲜度检查的预测，不是实测或保证；数据未提供模型发布时刻，临近出发时可再确认。
          - group [ref=e87]:
            - generic "Thinking · 回答说明" [ref=e88] [cursor=pointer]
      - generic [ref=e89]:
        - generic [ref=e90]: 南京博物院2026年10月7日几点开门，几点停止入馆？
        - generic [ref=e91]:
          - generic [ref=e92]: 南京博物院，2026-10-07（Asia/Shanghai）：公告开放时段为09:00–17:00，16:00停止入馆。 依据场馆官方日期公告（2026-09-17发布），本次10月08日 08:36获取。 https://www.njmuseum.com/zh/newsDetails?id=381205 这是已发布的日期安排，不能证明此刻实际开着，也不保证能入馆；未确认不存在临时调整，具体展厅可能另有安排。
          - group [ref=e93]:
            - generic "Thinking · 回答说明" [ref=e94] [cursor=pointer]
      - generic [ref=e95]:
        - generic [ref=e96]: 请帮我创建一趟新的独立南京三天旅行，已有旅行保留不改。2026年10月9日出发，10月11日返程，一个人，总预算3000元，喜欢历史文化、老街巷和本地小吃，节奏轻松。先给创建预览，等我确认。
        - generic [ref=e97]: 请核对：南京市，2026-10-09 至 2026-10-11，共 3 天，总预算 3000 元，每日预算 1000.00 元。确认后执行。
      - generic [ref=e99]:
        - generic [ref=e100]: 确认执行
        - generic [ref=e101]: 旅行已创建，正在根据我们的讨论准备候选行程，确认后再保存具体安排。
      - generic [ref=e103]: 请根据已保存的日期、预算和旅行偏好生成完整行程。
      - alert [ref=e104]:
        - strong [ref=e105]: 目的地研究尚未形成完整的景点资料，请重试。
        - button "重试本次需求" [ref=e107] [cursor=pointer]
    - generic [ref=e108]:
      - button "生成完整行程" [ref=e110] [cursor=pointer]
      - generic [ref=e113]:
        - textbox "告诉旅程总管" [ref=e114]:
          - /placeholder: 想了解目的地、旅行体验或目前安排？
        - generic [ref=e115]:
          - generic [ref=e116]: 仅在你确认后更新正式行程
          - button "发送需求" [disabled] [ref=e120]
      - generic [ref=e123]:
        - generic [ref=e124]: Enter
        - text: 发送
        - generic [ref=e125]: ·
        - generic [ref=e126]: Shift + Enter
        - text: 换行
```

# Test source

```ts
  11  |   const report: Record<string, any> = resume || previewResume ? JSON.parse(readFileSync(resolve(evidence, "conversation.json"), "utf8")) :
  12  |     { status: "in_progress", mock: false, isolated: true, turns: [], observations: [] };
  13  |   if (resume) { report.resumed_existing_run = true; report.status = "in_progress"; }
  14  |   if (previewResume) { expect(report.turns).toHaveLength(7); expect(report.run_id).toBeUndefined(); report.status = "in_progress"; delete report.error; }
  15  |   const save = () => writeFileSync(resolve(evidence, "conversation.json"), JSON.stringify(report, null, 2));
  16  |   save();
  17  |   // Refuse the production URL; preserve any earlier isolated acceptance fixtures.
  18  |   expect(new URL(test.info().project.use.baseURL!).port).toBe("3001");
  19  |   const initialTrips = await (await page.request.get("/api/v1/trips")).json();
  20  |   if (resume) expect(initialTrips.some((t: any) => t.id === report.trip_id)).toBe(true);
  21  |   else report.initial_trips = initialTrips;
  22  |   await page.goto(resume ? `/dev/agent-conversation/${report.trip_id}` : "/dev/agent-conversation");
  23  |   await expect(page.getByLabel("告诉旅程总管")).toBeEnabled({ timeout: 30_000 });
  24  |   const texts = [
  25  |     "你好",
  26  |     "最近想出去玩，一个人有点怕无聊，先聊聊，不要创建旅行。",
  27  |     "南京怎么样？我喜欢历史文化和老街巷，想轻松一点。",
  28  |     "请根据可靠资料介绍南京的历史文化和老街巷；如果资料不足就说明，不要猜。",
  29  |     "南京明天下午天气怎么样？",
  30  |     "南京博物院2026年10月7日几点开门，几点停止入馆？",
  31  |     "请帮我创建一趟新的独立南京三天旅行，已有旅行保留不改。2026年10月9日出发，10月11日返程，一个人，总预算3000元，喜欢历史文化、老街巷和本地小吃，节奏轻松。先给创建预览，等我确认。",
  32  |   ];
  33  |   try {
  34  |     if (!resume) {
  35  |     for (const [index, text] of (previewResume ? [] : texts).entries()) {
  36  |       await page.getByLabel("告诉旅程总管").fill(text);
  37  |       const response = page.waitForResponse(r => r.url().includes("/assistant/sessions/") && r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
  38  |       await page.getByRole("button", { name: "发送需求", exact: true }).click();
  39  |       const result = await response;
  40  |       const body = await result.json();
  41  |       const last = body.messages?.at(-1);
  42  |       report.turns.push({ text, http_status: result.status(), session_id: body.id, last, pending_action: body.pending_action });
  43  |       report.session_id = body.id;
  44  |       save();
  45  |       console.log("turn", index + 1, result.status(), last?.goal_routing?.target_runtime);
  46  |       expect(result.ok()).toBeTruthy();
  47  |       expect(last.assistant.trim().length).toBeGreaterThan(0);
  48  |       await expect(page.locator(".ai-message.agent").last()).toContainText(last.assistant.slice(0, 20));
  49  |       expect(await (await page.request.get("/api/v1/trips")).json()).toEqual(initialTrips);
  50  |       if (index < 6) {
  51  |         expect(last.goal_routing.target_runtime).toBe("companion");
  52  |         expect(last.goal_routing.mutation_requested).toBe(false);
  53  |         expect(body.latest_run_id).toBeNull();
  54  |         expect(body.pending_action).toBeNull();
  55  |       } else {
  56  |         expect(last.goal_routing.target_runtime).toBe("planning");
  57  |         expect(last.planning_brief).toBeTruthy();
  58  |         expect(body.pending_action?.tool).toBe("create_trip");
  59  |       }
  60  |       if (index === 4) {
  61  |         expect(last.companion_result.resolved_facts.some((f: any) => f.requirement.fact_type === "weather.forecast" && f.usable_as_current)).toBe(true);
  62  |       }
  63  |       if (index === 3) {
  64  |         expect(last.assistant).not.toContain("西湖");
  65  |         expect(last.companion_result.conversation_destination).toBe("南京");
  66  |         expect(last.companion_result.information_gaps.some((g: any) => g.code.startsWith("knowledge_"))).toBe(true);
  67  |       }
  68  |       if (index === 5) {
  69  |         expect(last.companion_result.resolved_facts.some((f: any) => f.requirement.fact_type === "place.opening_hours" && f.usable_as_current)).toBe(true);
  70  |       }
  71  |       await page.screenshot({ path: resolve(evidence, `turn-${index + 1}.png`), fullPage: true });
  72  |       await expect(page.getByLabel("告诉旅程总管")).toBeEnabled({ timeout: 30_000 });
  73  |     }
  74  |     if (previewResume) {
  75  |       const text = "请创建一趟新的独立旅行，已有那趟保留不改。南京三天，2026年10月9日至11日，一个人，总预算3000元，喜欢历史文化、老街巷和本地小吃，节奏轻松。先给创建预览，等我确认。";
  76  |       await page.getByLabel("告诉旅程总管").fill(text);
  77  |       const pending = page.waitForResponse(r => r.url().endsWith("/messages") && r.request().method() === "POST", { timeout: 180_000 });
  78  |       await page.getByRole("button", { name: "发送需求", exact: true }).click();
  79  |       const response = await pending;
  80  |       const body = await response.json();
  81  |       report.creation_clarification = { text, http_status: response.status(), last: body.messages.at(-1), pending_action: body.pending_action };
  82  |       save();
  83  |       expect(response.ok()).toBeTruthy();
  84  |       expect(body.id).toBe(report.turns.at(-1).session_id);
  85  |       expect(body.latest_run_id).toBeNull();
  86  |       expect(body.pending_action?.tool).toBe("create_trip");
  87  |       expect(await (await page.request.get("/api/v1/trips")).json()).toEqual(initialTrips);
  88  |     }
  89  |     await expect(page.getByRole("button", { name: "确认创建", exact: true })).toBeVisible();
  90  |     const decision = page.waitForResponse(r => r.url().endsWith("/decision") && r.request().method() === "POST", { timeout: 180_000 });
  91  |     await page.getByRole("button", { name: "确认创建", exact: true }).click();
  92  |     const response = await decision;
  93  |     expect(response.ok()).toBeTruthy();
  94  |     const created = await response.json();
  95  |     report.creation = created;
  96  |     report.trip_id = created.trip_id;
  97  |     report.run_id = created.latest_run_id;
  98  |     save();
  99  |     expect(created.trip_id).toBeTruthy();
  100 |     expect(created.latest_run_id).toBeTruthy();
  101 |     report.formal_before_candidate = await (await page.request.get(`/api/v1/trips/${created.trip_id}/days`)).json();
  102 |     }
  103 |     const created = report.creation;
  104 |     const daysBefore = report.formal_before_candidate;
  105 |     expect(daysBefore.flatMap((d: any) => d.activities)).toHaveLength(0);
  106 |     await expect.poll(async () => {
  107 |       const run = await (await page.request.get(`/api/v1/planning-runs/${created.latest_run_id}`)).json();
  108 |       report.latest_run = run;
  109 |       report.observations.push({ at: new Date().toISOString(), status: run.status, progress: run.progress, heartbeat_at: run.heartbeat_at });
  110 |       save();
> 111 |       if (["failed", "cancelled", "awaiting_clarification"].includes(run.status)) throw new Error(`Run ${run.status}: ${run.error_code ?? JSON.stringify(run.pending_interrupt)}`);
      |                                                                                         ^ Error: Run failed: planner_research_invalid_output
  112 |       return run.status;
  113 |     }, { timeout: 480_000, intervals: [2000, 5000] }).toBe("awaiting_confirmation");
  114 |     const revision = await (await page.request.get(`/api/v1/planning-runs/${created.latest_run_id}/revision`)).json();
  115 |     report.revision = revision;
  116 |     expect(revision.status).toBe("pending");
  117 |     expect(revision.validation_result.valid).toBe(true);
  118 |     expect(revision.proposed_snapshot.activities.length).toBeGreaterThan(0);
  119 |     const daysAfter = await (await page.request.get(`/api/v1/trips/${created.trip_id}/days`)).json();
  120 |     expect(daysAfter).toEqual(daysBefore);
  121 |     await expect(page.locator(".ai-proposal").filter({ hasText: "候选方案" })).toBeVisible({ timeout: 30_000 });
  122 |     await page.screenshot({ path: resolve(evidence, "candidate.png"), fullPage: true });
  123 |     report.status = "candidate_gate_passed_lifecycle_pending";
  124 |     delete report.error;
  125 |     save();
  126 |   } catch (error) {
  127 |     report.status = "failed";
  128 |     report.error = error instanceof Error ? error.message : String(error);
  129 |     save();
  130 |     throw error;
  131 |   }
  132 | });
  133 | 
```