"""Read-only support receipts. Related provider data is never a proof of fit."""
from datetime import UTC, datetime
from hashlib import sha256
import re


DOMAINS = {
    'walking_effort': r'省力|轻松|不累|走路|步行|台阶|轮椅|长辈|老人',
    'diet': r'忌口|过敏|不辣|吃辣|清汤|素食|吃素',
    'budget': r'预算|账单|人均|消费|价格|餐费|花费',
    'route': r'路线|路程|距离|耗时|车程',
}


def _time(value):
    try:
        parsed = datetime.fromisoformat(str(value).replace('Z', '+00:00'))
        return parsed if parsed.tzinfo else None
    except (TypeError, ValueError):
        return None


def assess_support(message, memory, reads, bound_refs=(), *, now=None, expected_route=None):
    """Only exact fresh bound route estimates may be supported here.

    Other evidence domains require richer evidence than these adapters provide;
    their related information remains visible, with the missing link explicit.
    The receipt is not an authorization, Planner constraint or general fact check.
    """
    now = now or datetime.now(UTC)
    requests = [(message, 'current_question', None)]
    for key in ('preferences','requirements'):
        for record in (memory or {}).get(key, []):
            requests.append((str(record.get('value','')), record.get('message_id') or key, record.get('scope')))
    for key, record in (memory or {}).get('slots', {}).items():
        requests.append((('预算：' if key == 'budget' else '') + str(record.get('value','')), record.get('message_id') or key, record.get('scope')))
    output = []
    for text, source, scope in requests:
        for domain, pattern in DOMAINS.items():
            if not re.search(pattern, text):
                continue
            related = []
            for observation in reads:
                ids = {str(p.get('place_id')) for p in observation.get('places', []) if p.get('place_id')}
                wanted = set(map(str, bound_refs))
                if not wanted or not wanted.issubset(ids):
                    continue
                result = observation.get('result', {})
                route = observation.get('kind') == 'route'
                if route and domain not in {'route','walking_effort'}:
                    continue
                expiry = _time(result.get('source', {}).get('expires_at') if route else observation.get('expires_at'))
                fresh = bool(expiry and expiry > now and (not route or
                    result.get('source', {}).get('freshness') == 'fresh' and not result.get('is_estimated_fallback')))
                related.append({'kind':observation.get('kind'), 'message_id':observation.get('message_id'),
                    'binding':observation.get('binding'),
                    'place_ids':sorted(ids), 'scope':'returned_endpoints_and_mode' if route else 'reference_excerpt',
                    'mode':result.get('mode') if route else None,
                    'expires_at':expiry.isoformat() if expiry else None, 'fresh':fresh})
            status = 'requested'
            reason = '尚无绑定当前地点的相关资料'
            if related:
                status, reason = 'related_information', '取得相关资料，尚不等于满足要求'
            if source == 'current_question' or related and not any(r['fresh'] for r in related):
                status = 'insufficient_or_stale'
            if (domain == 'route' and expected_route and len(expected_route.get('place_ids', [])) == 2
                and len(set(expected_route['place_ids'])) == 2
                and set(expected_route['place_ids']) == set(map(str, bound_refs))
                and expected_route.get('mode') in {'walk','driving'}
                and any(r['fresh'] and r['kind']=='route' and r['binding'] == expected_route
                    and r['mode'] == expected_route['mode'] for r in related)
                and not re.search(r'必须|最多|不超过|以内|全程|省力|轻松|不累|不用|保证', text)):
                status, reason = 'supported', '只支持所绑定两端及交通方式的路线估计'
            missing = {'walking_effort':'园内动线、台阶、上下车点到入口及休息设施',
                'diet':'整餐食材、汤底、调料及交叉接触处理',
                'budget':'本次完整订单、份量、服务费与最终结算',
                'route':'对应地点、交通方式及仍有效的路线结果'}[domain]
            output.append({'requirement_id':sha256((str(source)+domain+text).encode()).hexdigest()[:20],
                'text':text, 'source_ref':str(source), 'scope':scope, 'domain':domain,
                'requested':True, 'status':status, 'observations':related[-8:], 'reason':reason,
                'missing_link':None if status=='supported' else missing, 'checked_at':now.isoformat()})
    return {'version':1,'assessments':output,'semantics':'read_only_scoped_support_not_satisfaction_or_write_authority'}
