from django.contrib.auth.views import LogoutView, PasswordChangeView
from django.urls import path

from . import views
from .forms import StyledPasswordChangeForm


urlpatterns = [
    path("", views.RootLoginView.as_view(), name="login"),
    path("language/", views.language_switch, name="language_switch"),
    path("logout/", LogoutView.as_view(), name="logout"),
    path(
        "account/password/",
        PasswordChangeView.as_view(
            template_name="core/form.html",
            form_class=StyledPasswordChangeForm,
            success_url="/dashboard/",
            extra_context={"title": "Change password", "subtitle": "Use a strong password that you do not use anywhere else.", "submit_label": "Update password"},
        ),
        name="password_change",
    ),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("customers/", views.customer_list, name="customer_list"),
    path("customers/search/", views.customer_search, name="customer_search"),
    path("customers/add/", views.customer_create, name="customer_create"),
    path("customers/<int:pk>/", views.customer_detail, name="customer_detail"),
    path("customers/<int:pk>/edit/", views.customer_edit, name="customer_edit"),
    path("cylinders/", views.cylinder_list, name="cylinder_list"),
    path("cylinders/add/", views.cylinder_create, name="cylinder_create"),
    path("cylinders/<int:pk>/edit/", views.cylinder_edit, name="cylinder_edit"),
    path("inventory/movement/", views.stock_movement_create, name="stock_movement_create"),
    path("sales/", views.sale_list, name="sale_list"),
    path("sales/new/", views.sale_create, name="sale_create"),
    path("sales/<int:pk>/", views.sale_detail, name="sale_detail"),
    path("sales/<int:pk>/invoice/", views.invoice, name="invoice"),
    path("sales/<int:pk>/payment/", views.payment_create, name="payment_create"),
    path("sales/<int:pk>/mark-paid/", views.sale_mark_paid, name="sale_mark_paid"),
    path("sales/<int:pk>/whatsapp/", views.whatsapp_sale, name="whatsapp_sale"),
    path("expenses/", views.expense_list, name="expense_list"),
    path("expenses/add/", views.expense_create, name="expense_create"),
    path("reports/", views.reports, name="reports"),
    path("settings/", views.settings_view, name="settings"),
    path("employees/", views.employee_list, name="employee_list"),
    path("employees/add/", views.employee_create, name="employee_create"),
    path("employees/<int:pk>/edit/", views.employee_edit, name="employee_edit"),
]
