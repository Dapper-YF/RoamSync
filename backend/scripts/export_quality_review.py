"""Export complete synthetic evaluation conversations; never rewrite AI answers."""
import json,statistics
from pathlib import Path
import quality_runtime
from sqlalchemy import create_engine,select
from app.config import get_settings
from app.database import AssistantSession
folder=Path(__file__).resolve().parents[2]/'docs/evidence/conversation-quality-20261020'
main_notes=[
'百科式景区介绍，面积、名湖、建筑师评价挤占了散步建议。',
'给了小范围建议，但平路、位置和省力判断缺少明确证据，仍堆面积。',
'回答简短，能承接一小时和不想多走的要求。',
'可以先问城市；回答仍从三种火锅分类开场，略长。',
'不再整段报地址评分，但口味判断不足，位置顺路也未经路线核实。',
'饮食偏好和预算追问退化为通用兜底，未解答用户。',
'只介绍皇城老妈，未完成两个分店的比较；数据较多不等于更适合。',
'引用了单条负面反馈，但没有直接说明无法比较哪家差评更多。',
'明确没有排队信息，不编造等待时间。',
'比较对象漏查南京博物院，却仍给了部分比较性事实。',
'无本轮检索支撑地断言两小时可以看得扎实、疲劳程度等。',
'预约问题返回地点兜底，没有回答所问。',
'文化解释可读，但分四因素且含概括性因果，未独立核实。',
'承认客源资料不足；仍加了常识推测，末尾重复缺口说明。',
'前轮说不知道客源，本轮却肯定本地人和游客都会去；只有POI资料。',
'遵守只说两个，但光线、人群和现场场景描述过于确定。',
'因玉林资料缺失而更推荐宽窄巷子，混淆资料覆盖与用户匹配。',
'自称无法给图；正文与服务端媒体能力可能矛盾。',
'未得城市和锚点时追问必要信息，未假定GPS。',
'用户已明确人民公园附近，仍追问地点。',
'未承接已给锚点，连续重复追问。',
'把南博和玄武湖说成邻近顺路，未查路线；已有日期却让用户自己核对周一。',
'口头接受了周六下午留白；具体哪天集中安排仍不够清楚。',
'不保存的边界得到尊重，但延续了未经核实的顺路和日期说法。',
'把个人疲劳误当场馆实时状态，答非所问。',
'澄清只是讨论后能恢复聊天，但补了未经核实的观光车和省力建议。',
'接受不去和留白，仍多余地推荐早晨和坐船。',
'以常识作出义乌工艺品等笼统商户判断，语气武断。',
'交通限制未进入可靠核实链，混用具体通行说法、距离、电量和泛安全建议。',
'核实渠道方向有用，但“我倾向于认为/我的建议是”机械前缀和重复缺口影响阅读。']
base_notes=['景区头衔和面积堆砌，没有围绕慢逛展开。','未经所取证据支持地给出游船通常二十分钟。','虽承接少走路，仍重复游船和排队推断。','先泛列火锅类型，再问城市。','地址、评分、营业时间全部进入正文，信息像报表。','漏了句首具体门店，清汤供应与品质判断无当轮证据。']
re_notes=['较接近体验回答，但仍列五洲并添加跨城市比较，证据不够。','仍列面积，并以乘船承诺省力。','承认资料缺口，却又补“通常免费”；没有很自然地给出结论。','南京博物院仍漏查，沿用玄武湖的百科内容；之后定位到城市前缀被误删。','仍根据已取到的一方资料作选择，不足以证明更适合。','把非官方页面的精确放票和名额表述当当前规则，高风险；随后增加规则保护。','必要追问城市。','已能解析人民公园，不再反复追问；但正文仍兜底，未形成有用餐饮判断。','正确取得早餐地点，但证据引用组合校验导致兜底；随后修复多地点比较的引用绑定。','不再要求核实用户疲劳，但仍推销未核实的坐船/观光车与省力承诺。','知道未保存、不声称修改行程；仍延续未经核实的替代玩法。','尊重不去和留白；仍有多余早起/船游推荐。']
labels_main={3:'基本可用',4:'有保留',5:'有保留',8:'有保留',9:'基本可用',13:'有保留',14:'有保留',16:'有保留',19:'基本可用',23:'有保留',27:'有保留',30:'有保留'}
batches=[('基线', 'baseline-6.json',base_notes),('主样本','conversations-30.json',main_notes),('定向复验','recheck-12.json',re_notes),('补缺复验','final-1.json',['两个地点已正确查到，但正文冒出非官方预约规则与两万步说法；随后增加保护。']),('最终保护复验','safety-1.json',['选择与历史兴趣相符，正文不再堆地址评分；预约规则句被保护拦下。静态介绍的准确性仍取决于来源。'])]
all_rows=[];lines=['# RoamSync 50轮真实模型测试：完整问答与逐条审查','', '这些是预先编写的合成用户问题，通过真实 AssistantService、PostgreSQL、模型、高德及搜索服务运行；不是50位真实用户的使用研究。没有人工改写或省略任何最终回复。失败、兜底和不理想的回答均保留。','', '阶段包含6轮基线、30轮主样本、12轮定向复验、1轮补缺复验和1轮最终保护复验。阶段间发生过修正，不能把全部样本当成最终版本的成功率。审查是人工内容分析，未对每条外部事实做独立权威核验；“无证据支持”不等于已经证明事实为假。','']
for batch,file,notes in batches:
 rows=json.loads((folder/file).read_text(encoding='utf8'));assert len(rows)==len(notes)
 lines+=['## '+batch,'']
 for i,(row,note) in enumerate(zip(rows,notes),1):
  n=len(all_rows)+1
  label=(labels_main.get(i,'有明显问题') if batch=='主样本' else '基本可用' if batch=='最终保护复验' else '有保留' if batch=='定向复验' and i in (7,11,12) else '有明显问题')
  if row.get('error'):label='调用失败'
  item={**row,'sample':n,'phase':batch,'review':{'judgment':label,'note':note}};all_rows.append(item)
  lines += [f'### {n:02d} · {row["scenario"]} · 第{row["turn"]}轮','', '**用户**','',row['user'],'','**AI 完整回复（原文）**','',row['assistant'] or '（没有收到回复）','',f'**审查：{label}。** {note}', '',f'耗时：{row["seconds"]}秒；工具：{row.get("tool") or "无"}；Trip：{row.get("trip_id") or "未创建"}。','']
  if row.get('error'):lines+=['失败类型：'+row['error'],'']
  sources=row.get('sources',{}).get('sources',[])
  if sources:
   lines+=['本轮实际保留的来源：','']
   lines += [f'- [{j}] [{s["title"]}]({s["url"]}) · {s.get("read_level","未知读取级别")}' for j,s in enumerate(sources,1)]
   lines+=['']
  if row.get('public_process'):lines+=['公开过程说明（不含私有推理）：','',row['public_process'],'']
assert len(all_rows)==50
(folder/'FULL_CONVERSATIONS.md').write_text('\n'.join(lines),encoding='utf8')
(folder/'reviewed-conversations.json').write_text(json.dumps(all_rows,ensure_ascii=False,indent=2),encoding='utf8')
main=[r for r in all_rows if r['phase']=='主样本']; summary={'sample_count':50,'main_count':30,'main_judgments':{k:sum(r['review']['judgment']==k for r in main) for k in ['基本可用','有保留','有明显问题','调用失败']},'main_median_seconds':statistics.median(r['seconds'] for r in main),'main_max_seconds':max(r['seconds'] for r in main),'main_fallback_count':sum(r['assistant'].startswith(('找到了下面','地点已经找到了')) for r in main),'main_created_trip_count':sum(bool(r.get('trip_id')) for r in main),'main_pending_action_count':sum(bool(r.get('pending_action')) for r in main),'script_errors':sum(bool(r.get('error')) for r in all_rows)}
(folder/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8');print(json.dumps(summary,ensure_ascii=True))
# Additional UI acceptance, kept separate from the 50 scripted samples.
question='南京玄武湖值得去吗？我只想在湖边慢慢走走。'
with create_engine(get_settings().database_url).connect() as db:
 matches=[m for messages in db.execute(select(AssistantSession.messages)).scalars() for m in messages if m.get('user')==question]
ui={'user':question,'first_attempt_visible_error':'这次回答未能完成，请重试。','retry_answer':matches[-1]['assistant'] if matches else None,'note':'独立浏览器验收，不计入50轮主采样；首次与批量采样共用未绑定旅行的会话，重试成功；疑似并发状态问题，未从异常详情确认根因。未以重试抹去失败。'}
(folder/'browser-acceptance.json').write_text(json.dumps(ui,ensure_ascii=False,indent=2),encoding='utf8')
with (folder/'FULL_CONVERSATIONS.md').open('a',encoding='utf8') as f:f.write('\n\n## 浏览器验收附录（不计入50轮）\n\n用户：'+question+'\n\n首次尝试：'+ui['first_attempt_visible_error']+'\n\n重试后的完整回复：\n\n'+(ui['retry_answer'] or '未取得')+'\n')
