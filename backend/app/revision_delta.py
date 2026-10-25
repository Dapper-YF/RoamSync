"""Shared retention rule for Revision review and the existing Accept writer."""
def protected_activity_ids(items, frozen=(), protected=()):
    execution={str(value) for value in [*frozen,*protected]}
    result=set()
    for item in items:
        def value(key,default=None):
            return item.get(key,default) if isinstance(item,dict) else getattr(item,key,default)
        identity=value('id')
        if value('schedule_locked',False) or value('status') in {'active','completed','skipped'} or str(identity) in execution:
            result.add(identity)
    return result
