"""Request-local literal spans. They bind user data, never approval authority."""
import re


def action_clause(message, quote):
    """Literal scope including an elliptical question about this operation."""
    if not quote or message.count(quote) != 1:
        return ''
    start=message.index(quote)
    before=list(re.finditer(r'[，,；;。!?！？\n]',message[:start]))
    tail=message[start+len(quote):]
    boundary=re.search(r'[，,；;。!?！？\n]',tail)
    end=start+len(quote)+(boundary.start() if boundary else len(tail))
    dependent=re.match(r'[，,]\s*(?:那|这样|这|又)?(?:会怎样|会如何|是否可行|是否合适|能不能这样)[^。!?！？\n]*',message[end:])
    if dependent:
        end+=dependent.end()
    return message[before[-1].end() if before else 0:end]


def source_registry(history, message):
    spans = {}
    for i, text in enumerate([*(t.get('user', '') for t in history[-8:]), message]):
        if not isinstance(text, str) or not text:
            continue
        spans[f'user_{i}'] = text
        for j, match in enumerate(re.finditer(r'[^，,。；;!?！？\n]+', text)):
            spans[f'user_{i}_span_{j}'] = match[0]
    return spans
