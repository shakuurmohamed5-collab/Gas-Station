from decimal import Decimal

from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models import Sum
from django.urls import reverse
from django.utils import timezone


class TimeStampedModel(models.Model):
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class EmployeeProfile(TimeStampedModel):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="employee_profile")
    phone = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=80, blank=True, default="Employee")

    class Meta:
        ordering = ["user__first_name", "user__username"]

    def __str__(self):
        return self.user.get_full_name() or self.user.username


class CompanySetting(models.Model):
    name = models.CharField(max_length=120, default="GasFlow")
    phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    email = models.EmailField(blank=True)
    currency = models.CharField(max_length=8, default="$")
    auto_send_whatsapp = models.BooleanField(
        default=False,
        help_text="Automatically send an invoice/balance message after each sale or payment when Cloud API credentials are configured.",
    )
    invoice_footer = models.CharField(
        max_length=255,
        blank=True,
        default="Thank you for choosing us. Please keep this invoice for your records.",
    )

    class Meta:
        verbose_name = "Company settings"
        verbose_name_plural = "Company settings"

    def __str__(self):
        return self.name


class Customer(TimeStampedModel):
    name = models.CharField(max_length=120)
    phone = models.CharField(max_length=30, unique=True, db_index=True)
    alternate_phone = models.CharField(max_length=30, blank=True)
    address = models.CharField(max_length=255, blank=True)
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.phone})"

    @property
    def total_purchases(self):
        return self.sales.aggregate(total=Sum("items__line_total"))["total"] or Decimal("0")

    @property
    def total_balance(self):
        return sum((sale.balance for sale in self.sales.all()), Decimal("0"))

    def get_absolute_url(self):
        return reverse("customer_detail", kwargs={"pk": self.pk})


class GasCylinder(TimeStampedModel):
    PRODUCT_TYPES = [
        ("new_cylinder", "New cylinder"),
        ("cylinder_gas", "Cylinder gas"),
        ("cooker", "Cooking machine"),
    ]

    name = models.CharField(max_length=120)
    size = models.CharField(max_length=60, help_text="Cylinder size or cooking-machine model, for example 13 kg or 2 burner")
    product_type = models.CharField(max_length=16, choices=PRODUCT_TYPES, default="new_cylinder", db_index=True)
    image = models.ImageField(upload_to="gas-cylinders/%Y/%m/", blank=True, null=True)
    selling_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    cost_price = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    stock_quantity = models.PositiveIntegerField(default=0)
    reorder_level = models.PositiveIntegerField(default=3)
    is_active = models.BooleanField(default=True)
    description = models.TextField(blank=True)

    class Meta:
        ordering = ["name", "size"]
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"{self.name} — {self.size}"

    @property
    def is_low_stock(self):
        return self.stock_quantity <= self.reorder_level

class Sale(TimeStampedModel):
    PAYMENT_STATUS = [
        ("unpaid", "Unpaid"),
        ("partial", "Partially paid"),
        ("paid", "Paid"),
    ]

    invoice_number = models.CharField(max_length=24, unique=True, db_index=True)
    customer = models.ForeignKey(Customer, on_delete=models.PROTECT, related_name="sales")
    sale_date = models.DateField(default=timezone.localdate, db_index=True)
    discount = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    payment_status = models.CharField(max_length=10, choices=PAYMENT_STATUS, default="unpaid", db_index=True)
    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="sales_created")

    class Meta:
        ordering = ["-sale_date", "-id"]

    def __str__(self):
        return self.invoice_number

    @property
    def subtotal(self):
        return self.items.aggregate(total=Sum("line_total"))["total"] or Decimal("0")

    @property
    def total(self):
        return max(self.subtotal - self.discount, Decimal("0"))

    @property
    def amount_paid(self):
        return self.payments.aggregate(total=Sum("amount"))["total"] or Decimal("0")

    @property
    def balance(self):
        return max(self.total - self.amount_paid, Decimal("0"))

    @property
    def gross_profit(self):
        cost = self.items.aggregate(total=Sum("line_cost"))["total"] or Decimal("0")
        return self.total - cost

    def refresh_payment_status(self):
        if self.total and self.amount_paid >= self.total:
            status = "paid"
        elif self.amount_paid > 0:
            status = "partial"
        else:
            status = "unpaid"
        if self.payment_status != status:
            Sale.objects.filter(pk=self.pk).update(payment_status=status)
            self.payment_status = status

    def get_absolute_url(self):
        return reverse("sale_detail", kwargs={"pk": self.pk})


class SaleItem(models.Model):
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="items")
    cylinder = models.ForeignKey(GasCylinder, on_delete=models.PROTECT, related_name="sale_items")
    quantity = models.PositiveIntegerField(default=1, validators=[MinValueValidator(1)])
    unit_price = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    unit_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, validators=[MinValueValidator(0)])
    line_total = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    line_cost = models.DecimalField(max_digits=12, decimal_places=2, default=0, editable=False)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["sale", "cylinder"], name="unique_product_per_sale")]

    def save(self, *args, **kwargs):
        self.line_total = self.unit_price * self.quantity
        self.line_cost = self.unit_cost * self.quantity
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.quantity} × {self.cylinder}"


class StockMovement(TimeStampedModel):
    MOVEMENT_TYPES = [
        ("opening", "Opening stock"),
        ("sale", "Product sold"),
        ("received", "Stock received"),
    ]

    cylinder = models.ForeignKey(GasCylinder, on_delete=models.PROTECT, related_name="stock_movements")
    movement_type = models.CharField(max_length=20, choices=MOVEMENT_TYPES)
    product_change = models.IntegerField(default=0)
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name="stock_movements")
    notes = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, null=True, blank=True, related_name="stock_movements_created")

    class Meta:
        ordering = ["-created_at", "-id"]

    def __str__(self):
        return f"{self.cylinder}: {self.get_movement_type_display()}"


class Payment(TimeStampedModel):
    METHODS = [
        ("cash", "Cash"),
        ("mobile", "Mobile money"),
        ("bank", "Bank transfer"),
        ("other", "Other"),
    ]

    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name="payments")
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    payment_date = models.DateField(default=timezone.localdate, db_index=True)
    method = models.CharField(max_length=12, choices=METHODS, default="cash")
    reference = models.CharField(max_length=100, blank=True)
    notes = models.CharField(max_length=255, blank=True)
    received_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="payments_received")

    class Meta:
        ordering = ["-payment_date", "-id"]

    def __str__(self):
        return f"{self.sale.invoice_number}: {self.amount}"


class Expense(TimeStampedModel):
    CATEGORIES = [
        ("transport", "Transport"),
        ("utilities", "Utilities"),
        ("salary", "Salary / wages"),
        ("maintenance", "Maintenance"),
        ("supplies", "Supplies"),
        ("other", "Other"),
    ]

    expense_date = models.DateField(default=timezone.localdate, db_index=True)
    category = models.CharField(max_length=20, choices=CATEGORIES)
    description = models.CharField(max_length=255)
    amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    recorded_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="expenses_recorded")

    class Meta:
        ordering = ["-expense_date", "-id"]

    def __str__(self):
        return f"{self.get_category_display()}: {self.amount}"


class WhatsAppLog(TimeStampedModel):
    STATUSES = [("queued", "Queued"), ("sent", "Sent"), ("failed", "Failed"), ("link", "Opened as link")]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="whatsapp_logs")
    sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True, related_name="whatsapp_logs")
    message = models.TextField()
    status = models.CharField(max_length=10, choices=STATUSES, default="queued")
    provider_response = models.TextField(blank=True)
    sent_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.customer.phone} — {self.status}"
