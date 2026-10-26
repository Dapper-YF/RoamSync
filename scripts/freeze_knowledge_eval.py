"""One-shot pre-development fixture creation. Never run to replace a frozen file."""
import json, hashlib, subprocess
from pathlib import Path
from datetime import datetime, timezone
root=Path(__file__).resolve().parents[1]; out=root/'backend/evals/results/knowledge_coverage'
out.mkdir(parents=True,exist_ok=True)
assert not (out/'frozen_v1.json').exists(), 'Frozen fixture already exists; do not overwrite'
H='history_culture';P='destination_profile';E='place_experience';L='local_lifestyle';S='seasonal_experience';A='audience_strategy';T='travel_strategy'
ALL=[H,P,E,L,S,A,T]
ids={'land':'west_lake.landscape_components','profile':'west_lake.profile_components','photo':'west_lake.photography_elements','era':'west_lake.history_general.9th_century','dredge':'west_lake.dredging_period','inscribe':'west_lake.heritage_inscription_year','aesthetic':'west_lake.landscape_aesthetics','tea':'hangzhou.tea_lifestyle_theme','places':'hangzhou.tea_locations','autumn':'manjuelong.osmanthus_tradition','senior':'senior.activity_suitability_principle','visit':'senior.continuous_visit_time','pace':'senior.slow_pace_and_rest'}
rows=[]
def add(group,text,topics,types,facts=(),suff='sufficient',live=False,mode='source_grounded',advice=False,note=''):
    rows.append({'case_id':f'{group}_{sum(r["category"]==group for r in rows)+1:02d}','category':group,'user_text':text,'mode':mode,
        'expected_runtime':'companion','expected_mutation_requested':False,'expected_information_need':{'requested_topics':topics,'answer_mode':'mixed' if advice and topics else 'advisory' if advice or mode=='general_conversation' or (live and not topics) else 'factual'},
        'knowledge_required':mode!='general_conversation' and not(live and not topics),'allowed_knowledge_types':types,'forbidden_knowledge_types':[x for x in ALL if x not in types],
        'expected_assertion_ids':[ids[x] for x in facts],'assertion_equivalence_groups':[[ids['land'],ids['profile'],ids['photo']]] if any(x in facts for x in ['land','profile','photo']) else [],
        'evidence_sufficiency':suff,'live_fact_required':live,'planning_allowed':False,'expected_behavior_notes':note or 'Answer only supported stable subquestions; no widened scope or publisher endorsement; advice unverified.',
        'review_status':'reviewed_before_development','protocol_version':'knowledge-coverage-v1'})
# New tasks/contrasts, not copies of old expression lists.
add('profile','请依资料把西湖看作一幅山水图：湖水、周边山体和人造设施各占什么角色？',['landscape_components'],[P,H,E],['land'])
add('profile','查来源说明西湖岸边与山峦的空间关系，不需要游玩建议。',['landscape_components'],[P,H],['profile'])
add('profile','西湖的景观清单里只有天然山水，还是也有人工建筑？请核对出处。',['landscape_components'],[P,H,E],['land'])
add('profile','用可靠材料区分西湖的自然骨架与人文节点，分两点即可。',['landscape_components'],[P,H],['land'])
add('profile','杭州以外的江南湖泊是否也都有西湖一样的亭塔布局？只按现有出处作答。',['destination_scope'],[P,H],[], 'insufficient',note='Do not generalize West Lake to all lakes.')
add('profile','我做地理笔记，想核实西湖三面山体与湖面的组合。',['landscape_components'],[P,H],['profile'])
add('profile','资料能列出杭州全城每一种自然景点吗？西湖介绍够不够证明这个清单完整？',['destination_scope'],[P,H],[], 'insufficient')
add('profile','按来源概括西湖景观而非杭州市全貌，重点列出寺塔和堤岛。',['landscape_components'],[P,H,E],['land'])
add('history','需要出处：西湖的人工堤岛是在哪段世纪区间经疏浚出现的？不要回答湖盆地质年龄。',['west_lake_construction_period'],[H],['dredge'])
add('history','请把湖盆自然起源和人工疏浚造堤岛的时间分开核实，未知的部分就注明。',['lake_formation_history','west_lake_construction_period'],[H],['dredge'],'partial')
add('history','西湖的人工岛群形成于同一年吗？出处能否支持某一个精确公历年份？',['west_lake_construction_period','lake_formation_year'],[H],['dredge'],'partial')
add('history','西湖成为诗画灵感始于哪个世纪？这和湖水诞生的日期是同一件事吗？请用资料回答。',['history_general','lake_formation_year'],[H],['era'],'partial')
add('history','据世界遗产资料，西湖从何时被登记为世界文化遗产？',['heritage_inscription_year'],[H],['inscribe'])
add('history','西湖地质起源能精确到一个年份吗？我只接受现有证据。',['lake_formation_year','lake_formation_history'],[H],[],'insufficient')
add('history','查证西湖两堤三岛的营造年代，是自然长成还是反复疏浚的结果？',['west_lake_construction_period'],[H],['dredge'])
add('history','把西湖的文化影响起点、人工堤岛时期和世界遗产登记年份排成来源时间线。',['history_general','west_lake_construction_period','heritage_inscription_year'],[H],['era','dredge','inscribe'])
add('history','材料有没有记下西湖第一座亭子的奠基日？别拿湖景影响文学的世纪代替。',['historical_figures'],[H],[],'insufficient')
add('history','有人说西湖是在2011年才形成，这是否混淆申遗登记与地质成因？请核查资料。',['heritage_inscription_year','lake_formation_history'],[H],['inscribe'],'partial')
add('culture','请从来源解释西湖体现的山水审美理想，不要推荐打卡线路。',['cultural_significance'],[H],['aesthetic'])
add('culture','西湖对诗人、学者和艺术创作的影响，有何资料能说明起点？',['history_general'],[H],['era'])
add('culture','查可靠材料：西湖的寺、塔、亭和园林属于这片文化景观吗？',['landscape_components'],[H,P],['land'])
add('culture','西湖影响园林设计的具体传播国家和第一位设计者，出处都有吗？',['landscape_influence','historical_figures'],[H,P],[],'insufficient')
add('culture','据资料比较北山路茶舍与吴山茶楼各自提供的观景文化元素。',['local_tea_lifestyle'],[L,H],['places'])
add('culture','在杭州体验品茶与慢生活，官方文章有没有点名具体茶空间？',['local_tea_lifestyle'],[L],['tea','places'])
add('culture','来源里的吴山茶楼和北山路茶舍，哪个结合宋式文化、哪个结合观湖？',['local_tea_lifestyle'],[L],['places'])
add('culture','核查“杭州所有市民每日必喝茶”这个概括，茶馆体验文章能证明吗？',['daily_local_tea_generalization'],[L],[],'insufficient')
add('culture','杭州满觉陇为何与赏桂民俗有关？请按资料说明文化传承。',['autumn_custom'],[S,H],['autumn'])
add('culture','可靠来源能提供苏轼亲自设计每座西湖亭子的名单吗？',['historical_figures'],[H],[],'insufficient')
add('recommend','借来源支持的景观要素，给我一个拍文化照片的观察方法，别编具体机位。',['photography_elements'],[E,H,P],['photo'],advice=True)
add('recommend','我想带两位长辈轻松看看，依据一般服务规范给活动强度建议，不要求你证明杭州适宜。',['senior_activity_guidance'],[A,T],['senior'],advice=True)
add('recommend','老人一次不歇脚地逛多久就该休息？请按服务规范回答并给建议。',['senior_continuous_visit_time'],[A,T],['visit'],advice=True)
add('recommend','参考老年旅游规范，连续坐车与连续步行游览的时长上限分别是什么？',['senior_slow_travel','senior_continuous_visit_time'],[A,T],['pace','visit'])
add('recommend','有出处的茶馆慢体验，如何选择观湖还是观城？建议不要伪装成原文。',['local_tea_lifestyle'],[L],['places'],advice=True)
add('recommend','根据西湖资料帮我想个沿堤道观察构图的方式，不要替我创建行程。',['photography_elements'],[E,H,P],['photo'],advice=True)
add('recommend','只用提供的景观证据设计拍摄思路；若苏堤白堤某段没有记载，不要声称机构推荐那里。',['photography_elements','photography_authority'],[E,H],['photo'],'partial',advice=True,note='Creative generic advice allowed; unprovided named route/time must not be verified or attributed.')
add('recommend','按资料给历史爱好者一个观察西湖建筑的思路，明确分开已有事实和你的意见。',['landscape_components','history_general'],[H,E,P],['land','era'],advice=True)
add('trap','一份适用于全国老人的活动规范能证明西湖对所有老人都安全无障碍吗？请给证据。',['senior_destination_suitability'],[A,T],[],'insufficient')
add('trap','UNESCO介绍湖山结构是否就等于官方认可最佳摄影机位？请核对。',['photography_authority','landscape_components'],[H,E,P],['land'],'partial')
add('trap','来源提到赏桂习俗，所以能断言此刻满觉陇桂花正盛吗？',['autumn_custom'],[S],['autumn'],'partial',True)
add('trap','一篇西湖景观资料能直接给整个杭州的摄影适宜性排名吗？',['photography_scope'],[E,P],[],'insufficient')
add('trap','服务规范中的无障碍选择建议能证明某个杭州茶楼实际有电梯吗？请按证据。',['senior_destination_suitability','local_tea_lifestyle'],[A,T,L],[],'insufficient')
add('trap','看完来源后，你能说UNESCO亲自推荐日落长曝光技巧吗？',['photography_authority','photography_elements'],[E,H],['photo'],'partial')
add('trap','请区分官方网页名称与“西湖摄影与景观体验”这个整理标题，并提供URL。',['source_page_title'],[H,P,E],[],note='Canonical UNESCO title and URL; curator title never source title.')
add('trap','杭州茶生活文档的原始页面标题有没有核实？若没有，不要用内部整理名填上。',['source_page_title','local_tea_lifestyle'],[L],['tea'],'partial')
add('trap','列出西湖世界遗产资料的发布机构、网页名和链接，不需要旅游建议。',['source_page_title'],[H,P],[],note='UNESCO organization, canonical title, https://whc.unesco.org/en/list/1334')
add('trap','桂花报道的页面名里写了年份，是否足以推断今年每日活动安排？只按资料。',['source_page_title','autumn_custom'],[S],['autumn'],'partial',True)
add('mixed','按资料说明西湖的文学艺术影响；另帮我核实今晚有没有开放。',['history_general'],[H],['era'],'partial',True)
add('mixed','我想核对西湖景观组成，同时问明天是否下雨；有来源的部分别因天气未知而省掉。',['landscape_components'],[H,P,E],['land'],'partial',True)
add('mixed','根据出处讲杭州茶馆的观景特点，并说明此刻北山路茶舍价格能不能查到。',['local_tea_lifestyle'],[L],['tea','places'],'partial',True)
add('mixed','满觉陇的传统赏桂习俗是什么？请给来源，也告诉我本周花况是否可证实。',['autumn_custom'],[S],['autumn'],'partial',True)
add('mixed','按材料给出西湖申遗登记年，并核实今日入园预约是否还有名额。',['heritage_inscription_year'],[H],['inscribe'],'partial',True)
add('mixed','西湖人工堤岛的历史时期可以证实吗？那今天堵不堵车呢？请分别回答。',['west_lake_construction_period'],[H],['dredge'],'partial',True)
add('mixed','根据来源列出西湖自然与人工元素，另外明确地质形成的准确年份是否有证据。',['landscape_components','lake_formation_year'],[H,P,E],['land'],'partial')
add('mixed','杭州茶馆观湖和观城有什么区别？依资料回答，再说明能否推荐未经记载的具体店铺。',['local_tea_lifestyle'],[L],['places'],'partial',advice=True)
add('mixed','据老年规范讲一次游览时长，同时判断今天高温下我父亲是否应出门。',['senior_continuous_visit_time'],[A,T],['visit'],'partial',True)
add('mixed','查西湖文化影响及堤岛营造时期，再告诉我明晚拍照日落具体几点。',['history_general','west_lake_construction_period'],[H],['era','dredge'],'partial',True)
add('general','我更喜欢有旧街区的城市，能聊聊南京与泉州的气质差别吗？',[],[],[],'not_applicable',mode='general_conversation')
add('general','独自短途散心，我想听些城市漫步的灵感，不急着定行程。',[],[],[],'not_applicable',mode='general_conversation')
add('general','暂时只想听南京的小巷生活是什么感觉，别收集预算日期。',[],[],[],'not_applicable',mode='general_conversation')
add('general','先随便聊聊杭州茶文化，不用给出处也不用正式规划。',[],[],[],'not_applicable',mode='general_conversation')
assert len(rows)==60, len(rows)
real_ids=[rows[i]['case_id'] for i in [0,8,9,11,12,13,16,18,20,22,24,28,29,30,31,32,34,36,37,39,42,46,48,56]]
payload={'protocol_version':'knowledge-coverage-v1','frozen_at':datetime.now(timezone.utc).isoformat(),'reviewer':'Codex single reviewer; not independent human annotation','method':'New tasks/contrasts/combinations authored from current reviewed assertion capabilities before baseline; no old fixture expressions copied. Baseline will be unsealed, so final is frozen-label regression, not developer-blind validation.','real_model_case_ids':real_ids,'cases':rows}
data=(json.dumps(payload,ensure_ascii=False,indent=2)+'\n').encode();(out/'frozen_v1.json').write_bytes(data)
protected=['app/travel_goal_router.py','app/assistant_service.py','app/companion_runtime.py','app/companion_state.py','app/companion_contracts.py','app/tourism_knowledge_adapter.py','app/planning_graph.py','app/companion_information.py','app/companion_graph.py','app/companion_provider.py','app/knowledge_corpus/hangzhou_reviewed_v1.json']
manifest={'protocol_version':payload['protocol_version'],'frozen_at':payload['frozen_at'],'fixture_sha256':hashlib.sha256(data).hexdigest(),'head':subprocess.check_output(['git','rev-parse','HEAD'],text=True).strip(),'git_status_before':subprocess.check_output(['git','status','--porcelain'],text=True,encoding='utf-8').splitlines(),'pre_development_hashes':{p:hashlib.sha256((root/'backend'/p).read_bytes()).hexdigest() for p in protected},'case_count':60,'reviewer':payload['reviewer'],'labels_changed_after_freeze':0}
(out/'freeze_manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8');print(manifest['fixture_sha256'])
