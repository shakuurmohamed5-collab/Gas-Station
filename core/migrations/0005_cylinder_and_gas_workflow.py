from django.core.validators import MinValueValidator
from django.db import migrations, models


def reshape_existing_data(apps, schema_editor):
    GasCylinder = apps.get_model("core", "GasCylinder")
    SaleItem = apps.get_model("core", "SaleItem")
    StockMovement = apps.get_model("core", "StockMovement")

    SaleItem.objects.filter(transaction_type="purchase").update(transaction_type="package")
    SaleItem.objects.filter(transaction_type="exchange").update(transaction_type="gas_only")

    for product in GasCylinder.objects.all():
        product.gas_stock = product.stock_quantity if product.product_type == "cylinder" else 0
        product.save(update_fields=["gas_stock"])
    for movement in StockMovement.objects.all():
        if movement.movement_type == "purchase_sale":
            movement.movement_type = "package_sale"
            movement.gas_change = movement.product_change
        elif movement.movement_type == "exchange_sale":
            quantity = abs(movement.product_change)
            movement.movement_type = "gas_sale"
            movement.product_change = 0
            movement.gas_change = -quantity
        elif movement.movement_type == "received":
            movement.movement_type = "product_received"
            movement.gas_change = 0
        elif movement.movement_type == "refilled":
            movement.movement_type = "gas_received"
            movement.product_change = 0
            movement.gas_change = abs(movement.gas_change)
        elif movement.movement_type == "opening":
            movement.gas_change = movement.product_change
        movement.save(update_fields=["movement_type", "product_change", "gas_change"])


class Migration(migrations.Migration):
    dependencies = [("core", "0004_lpg_exchange_inventory")]

    operations = [
        migrations.RenameField(model_name="gascylinder", old_name="empty_stock", new_name="gas_stock"),
        migrations.RenameField(model_name="gascylinder", old_name="exchange_price", new_name="gas_price"),
        migrations.RenameField(model_name="gascylinder", old_name="exchange_cost", new_name="gas_cost"),
        migrations.RenameField(model_name="stockmovement", old_name="filled_change", new_name="product_change"),
        migrations.RenameField(model_name="stockmovement", old_name="empty_change", new_name="gas_change"),
        migrations.AddField(model_name="gascylinder", name="gas_reorder_level", field=models.PositiveIntegerField(default=3)),
        migrations.AlterField(
            model_name="gascylinder",
            name="gas_price",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Amount charged for gas when the customer already has a cylinder.", max_digits=12, validators=[MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name="gascylinder",
            name="gas_cost",
            field=models.DecimalField(decimal_places=2, default=0, help_text="Company cost of the gas supplied for one cylinder.", max_digits=12, validators=[MinValueValidator(0)]),
        ),
        migrations.AlterField(
            model_name="saleitem",
            name="transaction_type",
            field=models.CharField(choices=[("package", "New cylinder + gas"), ("gas_only", "Gas only — customer has cylinder"), ("product", "Cooking machine")], default="package", max_length=12),
        ),
        migrations.AlterField(
            model_name="stockmovement",
            name="movement_type",
            field=models.CharField(choices=[("opening", "Opening stock"), ("package_sale", "New cylinder + gas supplied"), ("gas_sale", "Gas only supplied"), ("product_sale", "Cooking machine supplied"), ("product_received", "Cylinder / product stock received"), ("gas_received", "Gas stock received")], max_length=20),
        ),
        migrations.RunPython(reshape_existing_data, migrations.RunPython.noop),
    ]
