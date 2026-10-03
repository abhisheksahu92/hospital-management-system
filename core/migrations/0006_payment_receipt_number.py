from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0005_appointment_no_show_at_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="payment",
            name="receipt_number",
            field=models.CharField(default="", max_length=40, unique=True),
            preserve_default=False,
        ),
    ]
