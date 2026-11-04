import re

from django.db import migrations


def seed(apps, schema_editor):
    Container = apps.get_model("inventory", "Container")
    Code = apps.get_model("inventory", "BoxCode")
    Sequence = apps.get_model("inventory", "BoxSequence")
    codes = list(Container.objects.values_list("code", flat=True))
    Code.objects.bulk_create([Code(code=code) for code in codes], ignore_conflicts=True)
    highest = max((int(c[1:]) for c in codes if re.fullmatch(r"B\d+", c)), default=0)
    Sequence.objects.get_or_create(pk=1, defaults={"next_number": highest + 1})


class Migration(migrations.Migration):
    dependencies = [("inventory", "0004_boxcode_boxsequence_boxbatch_boxbatchmember")]
    operations = [migrations.RunPython(seed, migrations.RunPython.noop)]
