from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0002_companysetting_auto_send_whatsapp"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="Stove",
            new_name="GasCylinder",
        ),
        migrations.RemoveConstraint(
            model_name="saleitem",
            name="unique_stove_per_sale",
        ),
        migrations.RenameField(
            model_name="saleitem",
            old_name="stove",
            new_name="cylinder",
        ),
        migrations.RemoveField(
            model_name="gascylinder",
            name="sku",
        ),
        migrations.RemoveField(
            model_name="gascylinder",
            name="cost_price",
        ),
        migrations.AlterField(
            model_name="gascylinder",
            name="image",
            field=models.ImageField(blank=True, null=True, upload_to="gas-cylinders/%Y/%m/"),
        ),
        migrations.AlterField(
            model_name="gascylinder",
            name="size",
            field=models.CharField(help_text="Example: 6 kg, 13 kg, or 25 kg", max_length=60),
        ),
        migrations.AlterModelOptions(
            name="gascylinder",
            options={"ordering": ["name", "size"], "verbose_name": "Gas cylinder", "verbose_name_plural": "Gas cylinders"},
        ),
        migrations.AddConstraint(
            model_name="saleitem",
            constraint=models.UniqueConstraint(fields=("sale", "cylinder"), name="unique_cylinder_per_sale"),
        ),
    ]
