# 旅行对话重新解释与流式展示

2026-10-12。源码实施完成，未替换正在运行的 API/Web。

## 行为

用户追问行程安排时，版本绑定的保存说明作为上下文交给 Companion，结合当前问题、正式活动、时长、坐标和偏好生成新的中文回答。标记为 current_reconstruction，不冒认原始决定依据。保存说明中的旧状态不得覆盖当前 accepted/pending 状态。明确索要原始已验证记录时仍使用严格 Ledger/Activity 边界；缺失、歧义、过期和不匹配时间仍不编造原始理由。SELECT-only、Run 保持、正式行程确认规则不变。

新增 POST /api/v1/assistant/sessions/{id}/messages/stream。request-local ContextVar 隔离不同请求，SSE 使用 status / analysis_delta / answer_delta / reset / done / error。JSON 增量解析只读取顶层公开字段，处理跨块转义和 Unicode，不读取 Provider reasoning_content 或内部思考。GLM Chat Completions 和 Responses 的公开文本流均支持回调。公开 analysis_summary 是简短考虑因素摘要，不能声称完整内部推理。

自由正文的完整子句先经过现有动态断言控制，再发送预览；最终 JSON、身份、来源、建议和正文仍由现有校验决定。模型格式修复清除旧预览。数据库连接在流生成器内管理，断线取消请求任务；完整 turn 提交后才发送 done。同 message_id 保持已有幂等契约，未完成正文不保存。流错误不在浏览器曝光原始异常。需要服务端拼装的事实/来源回答不绕过证据校验，不保证这些确定性内容也按模型 Token 输出。

Web 在实时接收网络数据期间平滑逐字显示正文，历史回答立即展示；没有等待整篇完成后再模拟流式。Thinking 摘要位于正文之前、生成时展开、正文开始后收起。回答依据独立折叠。待确认候选在追问期间继续保留。Nginx 关闭代理缓冲和缓存，增加读取超时。

## 验证

- VERIFIED：隔离 Linux/Python3.11/PostgreSQL17，迁移0034，956通过、2既有弃用警告。镜像48e1b06811013eea27f4f5f4467fa08dc186ae42c673feea971461088f27de1c。失败尝试原样保留。
- VERIFIED：Web132通过，类型检查与生产构建通过。既有 act 警告未修复。
- VERIFIED：真实 Chrome、构建产物、独立 HTTP SSE socket、合成数据5项通过；分析先出现、正文在请求完成前增长、完成摘要保留、刷新恢复。无生产请求。
- MEASURED：真实 glm-5.3-flash 合成南京问题，第二次4.111秒首个公开分析、6.158秒首个正文、11.338秒完成，44个公开事件。原第一次58事件/11.974秒也保留。Windows仅进程内把Docker代理主机名改成loopback，未改.env；不能外推生产容器网络稳定性。

证据目录 backend/evals/results/companion_stream_20261012。browser/截图是合成场景；provider_smoke.json 是一次真实模型合成问题，未访问数据库。

## 限制与发布

首个模型样本仍错误地把未验证分组说成路线高效；补上缺坐标/路线时不得断言近、短程或不折返的约束，第二次明确保留地图核验。模型仍出现未验证的开放节奏暗示，不能据此宣布事实质量问题已经解决。既有事实/旅游知识/Provider稳定性质量门禁继续 OPEN。

本轮未改数据库 schema、Worker/Planning接受规则、Android、生产配置，未执行正式行程操作，未部署。生产网站仍是先前版本，部署需要选定并核对发布快照，不能把开发树既有未发布差异自动视作已获发布授权。
