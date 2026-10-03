from django.db import transaction

from core.models import NumberSequence


@transaction.atomic
def next_number(code):
    sequence = NumberSequence.objects.select_for_update().get(code=code)
    value = sequence.next_value
    sequence.next_value += 1
    sequence.save(update_fields=("next_value", "updated_at"))
    return f"{sequence.prefix}{value}"
