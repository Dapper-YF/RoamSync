export type ReviewValue = { name: string | null; place_id: string; date: string; time: string; duration_minutes: number; estimated_cost_fen: number; locked: boolean };
export type RevisionReviewData = {complete: boolean; base_trip_version: number | null; changes: {kind: 'add'|'remove'|'change'; before: ReviewValue | null; after: ReviewValue | null}[]; preserved?:ReviewValue[]; routes: {position: number; day_date: string; mode: string; distance_meters: number; duration_minutes: number; provider: string; is_estimated: boolean}[]; warnings: {message: string}[]};
const valueText=(v: ReviewValue)=>`${v.name ?? '地点身份未核对'} · ${v.date} ${v.time} / ${v.duration_minutes}分钟${v.locked?' · 固定活动':''} · 规划费用${v.estimated_cost_fen/100}元（参考）`;
export function RevisionReview({review}:{review:RevisionReviewData}) {
  return <>
    <ul>{review.changes.map((change,n)=><li key={n}>{change.kind==='remove'?'删除：':change.kind==='add'?'新增：':'修改：'}{change.before&&<span>原来 {valueText(change.before)}</span>}{change.before&&change.after&&' → '}{change.after&&<span>{valueText(change.after)}</span>}</li>)}</ul>
    {!review.changes.length&&<p>没有活动内容变化。</p>}
    {review.preserved?.map((item,n)=><p key={n}>保留固定或执行中事项：{valueText(item)}</p>)}
    {!!review.routes.length&&<details><summary>采用后的活动间路线（地图估计）</summary>{review.routes.map((r,n)=><p key={n}>{r.day_date} 第{r.position+1}段 · {r.mode==='walk'?'步行':r.mode==='driving'?'驾车':r.mode} · {r.distance_meters}米 / {r.duration_minutes}分钟 · {r.is_estimated?'尚未核实的估算':r.provider}</p>)}</details>}
    {review.warnings.map((w,n)=><p key={n}>需留意：{w.message}</p>)}
    {!review.complete&&<p role="alert">这份历史候选缺少完整的修改前状态或地点身份，请重新生成可完整核对的候选。</p>}
  </>;
}
