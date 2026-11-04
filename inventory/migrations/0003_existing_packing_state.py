from django.db import migrations


def initialise(apps, schema_editor):
    Container = apps.get_model("inventory", "Container")
    Item = apps.get_model("inventory", "Item")
    ids = (
        Item.objects.filter(container__isnull=False)
        .exclude(status="removed")
        .values("container_id")
    )
    Container.objects.filter(pk__in=ids, packing_state="empty").update(
        packing_state="stored"
    )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0002_printer_tagbatch_container_category_and_more")]
    operations = [migrations.RunPython(initialise, migrations.RunPython.noop)]
