from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0003_rename_stove_to_gas_cylinder"),
    ]

    operations = [
        migrations.AddField(
            model_name="gascylinder",
            name="product_type",
            field=models.CharField(choices=[("cylinder", "Gas cylinder"), ("cooker", "Cooking machine")], db_index=True, default="cylinder", max_length=12),
        ),
        migrations.AddField(
            model_name="gascylinder",
            name="empty_stock",
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.AddField(
            model_name="gascylinder",
            name="cost_price",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="gascylinder",
            name="exchange_price",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Amount charged when a customer returns an empty cylinder for a filled one.", max_digits=12, validators=[MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="gascylinder",
            name="exchange_cost",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Company cost of refilling one cylinder.", max_digits=12, validators=[MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="saleitem",
            name="transaction_type",
            field=models.CharField(choices=[("purchase", "First purchase"), ("exchange", "Empty cylinder exchange")], default="purchase", max_length=12),
        ),
        migrations.AddField(
            model_name="saleitem",
            name="unit_cost",
            field=models.DecimalField(decimal_places=2, default=0, max_digits=12, validators=[MinValueValidator(0)]),
        ),
        migrations.AddField(
            model_name="saleitem",
            name="line_cost",
            field=models.DecimalField(decimal_places=2, default=0, editable=False, max_digits=12),
        ),
        migrations.RemoveConstraint(
            model_name="saleitem",
            name="unique_cylinder_per_sale",
        ),
        migrations.AddConstraint(
            model_name="saleitem",
            constraint=models.UniqueConstraint(fields=("sale", "cylinder", "transaction_type"), name="unique_product_transaction_per_sale"),
        ),
        migrations.CreateModel(
            name="StockMovement",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("movement_type", models.CharField(choices=[("opening", "Opening stock"), ("purchase_sale", "First purchase supplied"), ("exchange_sale", "Cylinder exchange"), ("received", "Filled stock received"), ("refilled", "Empty cylinders refilled")], max_length=20)),
                ("filled_change", models.IntegerField(default=0)),
                ("empty_change", models.IntegerField(default=0)),
                ("notes", models.CharField(blank=True, max_length=255)),
                ("created_by", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements_created", to=settings.AUTH_USER_MODEL)),
                ("cylinder", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="stock_movements", to="core.gascylinder")),
                ("sale", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="stock_movements", to="core.sale")),
            ],
            options={"ordering": ["-created_at", "-id"]},
        ),
    ]
