from django.db import migrations, models


def split_cylinder_and_gas_products(apps, schema_editor):
    GasCylinder = apps.get_model("core", "GasCylinder")
    SaleItem = apps.get_model("core", "SaleItem")
    StockMovement = apps.get_model("core", "StockMovement")

    gas_products = {}
    for product in list(GasCylinder.objects.all()):
        if product.product_type != "cylinder":
            continue
        gas_product = GasCylinder.objects.create(
            name=f"{product.name} Gas",
            size=product.size,
            product_type="cylinder_gas",
            selling_price=product.gas_price,
            cost_price=product.gas_cost,
            stock_quantity=product.gas_stock,
            reorder_level=product.gas_reorder_level,
            is_active=product.is_active,
            description=f"Gas for customers who already own a {product.size} cylinder.",
        )
        gas_products[product.pk] = gas_product.pk
        product.product_type = "new_cylinder"
        product.selling_price += product.gas_price
        product.cost_price += product.gas_cost
        product.save(update_fields=["product_type", "selling_price", "cost_price"])

    for item in SaleItem.objects.select_related("cylinder"):
        original_product_id = item.cylinder_id
        if item.transaction_type == "gas_only" and original_product_id in gas_products:
            item.cylinder_id = gas_products[original_product_id]
            item.save(update_fields=["cylinder"])

    for movement in StockMovement.objects.all():
        original_product_id = movement.cylinder_id
        if movement.movement_type in ("gas_sale", "gas_received") and original_product_id in gas_products:
            movement.cylinder_id = gas_products[original_product_id]
            movement.product_change = movement.gas_change
        if movement.movement_type in ("package_sale", "gas_sale", "product_sale"):
            movement.movement_type = "sale"
        elif movement.movement_type in ("product_received", "gas_received"):
            movement.movement_type = "received"
        movement.save(update_fields=["cylinder", "movement_type", "product_change"])

    for original_id, gas_product_id in gas_products.items():
        gas_product = GasCylinder.objects.get(pk=gas_product_id)
        if gas_product.stock_quantity:
            StockMovement.objects.create(
                cylinder_id=gas_product_id,
                movement_type="opening",
                product_change=gas_product.stock_quantity,
                notes="Opening cylinder gas stock",
            )


class Migration(migrations.Migration):
    dependencies = [("core", "0005_cylinder_and_gas_workflow")]

    operations = [
        migrations.RunPython(split_cylinder_and_gas_products, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="saleitem", name="unique_product_transaction_per_sale"),
        migrations.RemoveField(model_name="saleitem", name="transaction_type"),
        migrations.AddConstraint(
            model_name="saleitem",
            constraint=models.UniqueConstraint(fields=("sale", "cylinder"), name="unique_product_per_sale"),
        ),
        migrations.RemoveField(model_name="gascylinder", name="gas_price"),
        migrations.RemoveField(model_name="gascylinder", name="gas_cost"),
        migrations.RemoveField(model_name="gascylinder", name="gas_stock"),
        migrations.RemoveField(model_name="gascylinder", name="gas_reorder_level"),
        migrations.AlterField(
            model_name="gascylinder",
            name="product_type",
            field=models.CharField(choices=[("new_cylinder", "New cylinder"), ("cylinder_gas", "Cylinder gas"), ("cooker", "Cooking machine")], db_index=True, default="new_cylinder", max_length=16),
        ),
        migrations.AlterField(
            model_name="gascylinder",
            name="size",
            field=models.CharField(help_text="Cylinder size or cooking-machine model, for example 13 kg or 2 burner", max_length=60),
        ),
        migrations.AlterModelOptions(
            name="gascylinder",
            options={"ordering": ["name", "size"], "verbose_name": "Product", "verbose_name_plural": "Products"},
        ),
        migrations.RemoveField(model_name="stockmovement", name="gas_change"),
        migrations.AlterField(
            model_name="stockmovement",
            name="movement_type",
            field=models.CharField(choices=[("opening", "Opening stock"), ("sale", "Product sold"), ("received", "Stock received")], max_length=20),
        ),
    ]
