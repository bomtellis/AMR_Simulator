"""Effective staff choice shared by generation and runtime handling."""


def resolve_staff_requirement(requirement=None, *, labels=(), task_id='', source='',
                              payload='', is_return=False):
    """Preserve explicit choice and the legacy Stores-only omission fallback.

    Callers parse configuration scalars before calling; this function does not
    introduce a second JSON coercion policy or change the saved choice.
    """
    if is_return:
        return False
    if requirement is not None:
        return bool(requirement)
    return (
        'stores' in {str(label).strip().lower() for label in (labels or [])}
        or str(task_id or '').strip().upper().startswith('GEN_STORES_')
        or str(source or '').strip().lower() == 'stores'
        or str(payload or '').strip() == 'stores'
    )
