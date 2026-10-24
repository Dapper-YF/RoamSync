"""Request-local literal spans. They bind user data, never approval authority."""
import re


def source_registry(history, message):
    spans = {}
    for i, text in enumerate([*(t.get('user', '') for t in history[-8:]), message]):
        if not isinstance(text, str) or not text:
            continue
        spans[f'user_{i}'] = text
        for j, match in enumerate(re.finditer(r'[^，,。；;!?！？\n]+', text)):
            spans[f'user_{i}_span_{j}'] = match[0]
    return spans
