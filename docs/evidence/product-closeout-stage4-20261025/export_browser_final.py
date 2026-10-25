"""Export the original stored browser conversation and observed recovery boundary."""
import json
from pathlib import Path
root=Path(__file__).parent
snapshot=json.loads((root/'runtime-final-v6/browser-states/adopted60-after-refresh.json').read_text(encoding='utf-8'))
sessions=[s for s in snapshot['tables']['assistant_sessions'] if s['trip_id']=='fd8f4a28-566d-4feb-b0f2-b74a4164b865' and s['messages']]
if len(sessions)!=1: raise ValueError('Expected original unique conversation')
session=sessions[0]
parts=['''# 苏州真实浏览器连续验收

结论：完整自然对话黄金链FAIL。受测产品736e3b7，app hash f5f37b0c0f5bc8133d36ec76188517f9429ae8281d35e7eb60960bb592a173ff。
此处导出的是原隔离数据库AssistantSession中的可见用户/助手全文，模型选择与高德调用另见同目录api-trace.ndjson。
真实行程fd8f4a28-566d-4feb-b0f2-b74a4164b865，原会话'''+session['id']+'''。

## 路径与状态

1. 零正式表行开始，苏州两园比较与参考照片真实显示，第二个=狮子林。
2. 前一个→后一个：高德588米/8分钟；今天开放时间只有冲突摘录，未完成充分具体核实步骤，记partial。
3. 真实生成120/90分钟候选，午餐12–13、步行；拙政园改75且其他开始时间不变。
4. “先不采用”推断讨论后正式表仍零；明确采用后Trip版本2，首项75。
5. 保存回读有重复片段；60分钟修改生成pending Revision a677cd99-f5f6-4037-acd1-53a0e6d15153，正式首项仍75。
6. 浏览器刷新恢复相同Revision、差异卡和版本；随后聊天追问差异却说看不到候选，构成整链阻断。
7. 后续用户steering/执行环境中断导致隔离服务和测试PG停止，恢复原库，没有重建/补库/替换对象。
   新浏览器上下文根页未恢复原对话；从实际已知Trip页可恢复pending预览，页面明确按钮采用60后刷新成功。
   这一段是页面恢复采用，不是原完整自然对话通过。
8. 前后真实表差异：仅目标duration75→60及其version/updated_at变化；Trip2→2→3，午餐/第二活动/偏好等保留。
   路线按原写入链重建；不能把路线SQL重建表述为绝无相关数据库写入。

## 图片范围

实测显示的是Wikimedia照片搜索参考，非AI生成、非预置苏州候选；未逐图核实地点身份、许可或当前现场状态。
旧reviewed图库11地点/4城市没有苏州。原网络TLS失败及无关街景失败记录保留在v2/v3，不被新结果抹去。

## 原始用户/助手全文
''']
for i,message in enumerate(session['messages'],1):
    parts.append(f'\n### Turn {i}\n\nUser:\n\n{message.get("user", "")}\n\nAssistant:\n\n{message.get("assistant", "")}\n')
parts.append('''
## 浏览器证据

runtime-final-v4/screenshots/suzhou-photos.png与suzhou-second-photo.png：真实照片显示。
runtime-final-v6/screenshots/pending60-before-refresh.png：75→60差异。
runtime-final-v6/screenshots/restored60-trip-page.png：环境恢复后的实际候选。
runtime-final-v6/screenshots/adopted60-after-refresh.png：明确按钮采用后刷新保存态。
browser-final-state-comparisons.json：正式态不变/采用后单目标delta；状态原件在runtime-final-v6/browser-states。

安全五实验使用本浏览器pending60精确克隆，五项结果不代替自然语言任务完成性。
''')
(root/'BROWSER_FULL_CHAIN.md').write_text(''.join(parts),encoding='utf-8')
print(json.dumps({'session_id':session['id'],'stored_turns':len(session['messages']),'golden_path':'FAIL'}))
