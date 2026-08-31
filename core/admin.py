from django.contrib import admin

from .models import CompanySetting, Customer, EmployeeProfile, Expense, GasCylinder, Payment, Sale, SaleItem, StockMovement, WhatsAppLog


@admin.register(CompanySetting)
class CompanySettingAdmin(admin.ModelAdmin):
    fieldsets = (("Company", {"fields": ("name", "phone", "email", "address")}), ("Invoices & messaging", {"fields": ("currency", "invoice_footer", "auto_send_whatsapp")}))

    def has_add_permission(self, request):
        return not CompanySetting.objects.exists()


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ("name", "phone", "address", "created_at")
    search_fields = ("name", "phone", "alternate_phone")


@admin.register(GasCylinder)
class GasCylinderAdmin(admin.ModelAdmin):
    list_display = ("name", "size", "product_type", "selling_price", "stock_quantity", "is_active")
    list_filter = ("product_type", "is_active")
    search_fields = ("name", "size")


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0


class PaymentInline(admin.TabularInline):
    model = Payment
    extra = 0


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ("invoice_number", "customer", "sale_date", "payment_status", "created_by")
    list_filter = ("payment_status", "sale_date")
    search_fields = ("invoice_number", "customer__name", "customer__phone")
    inlines = (SaleItemInline, PaymentInline)


admin.site.register(Expense)
admin.site.register(StockMovement)
admin.site.register(WhatsAppLog)
admin.site.register(EmployeeProfile)

admin.site.site_header = "GasFlow Administration"
admin.site.site_title = "GasFlow Admin"
