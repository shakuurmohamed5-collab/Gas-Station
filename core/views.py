import json
from datetime import timedelta
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.views import LoginView
from django.conf import settings
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Case, Count, DecimalField, F, IntegerField, OuterRef, Q, Subquery, Sum, Value, When
from django.db.models.functions import Coalesce, Greatest
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils import timezone
from django.views.decorators.http import require_POST

from .access import admin_required, employee_required
from .forms import CompanySettingForm, CustomerForm, EmployeeForm, ExpenseForm, GasCylinderForm, LoginForm, PaymentForm, SaleForm, SaleItemFormSet, StockMovementForm
from .models import CompanySetting, Customer, EmployeeProfile, Expense, GasCylinder, Payment, Sale, SaleItem, StockMovement
from .services import send_sale_whatsapp


MONEY_FIELD = DecimalField(max_digits=14, decimal_places=2)


def money_sum(field):
    return Coalesce(Sum(field), Decimal("0"), output_field=MONEY_FIELD)


def sales_with_dashboard_totals(queryset=None):
    queryset = queryset if queryset is not None else Sale.objects.all()
    item_total = (
        SaleItem.objects.filter(sale_id=OuterRef("pk"))
        .values("sale_id")
        .annotate(total=Sum("line_total"))
        .values("total")[:1]
    )
    paid_total = (
        Payment.objects.filter(sale_id=OuterRef("pk"))
        .values("sale_id")
        .annotate(total=Sum("amount"))
        .values("total")[:1]
    )
    return (
        queryset.annotate(
            dashboard_subtotal=Coalesce(Subquery(item_total, output_field=MONEY_FIELD), Decimal("0"), output_field=MONEY_FIELD),
            dashboard_paid=Coalesce(Subquery(paid_total, output_field=MONEY_FIELD), Decimal("0"), output_field=MONEY_FIELD),
        )
        .annotate(
            dashboard_total=Greatest(F("dashboard_subtotal") - F("discount"), Decimal("0"), output_field=MONEY_FIELD),
        )
        .annotate(
            dashboard_balance=Greatest(F("dashboard_total") - F("dashboard_paid"), Decimal("0"), output_field=MONEY_FIELD),
        )
    )


def company():
    return CompanySetting.objects.first() or CompanySetting.objects.create()


class RootLoginView(LoginView):
    template_name = "registration/login.html"
    authentication_form = LoginForm
    redirect_authenticated_user = True


@require_POST
def language_switch(request):
    language = request.POST.get("language", "en")
    if language not in {"en", "so"}:
        language = "en"
    next_url = request.POST.get("next", "/")
    if not url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        next_url = "/"
    response = redirect(next_url)
    response.set_cookie(
        settings.LANGUAGE_COOKIE_NAME,
        language,
        max_age=60 * 60 * 24 * 365,
        path=settings.LANGUAGE_COOKIE_PATH,
        secure=settings.LANGUAGE_COOKIE_SECURE,
        httponly=settings.LANGUAGE_COOKIE_HTTPONLY,
        samesite=settings.LANGUAGE_COOKIE_SAMESITE,
    )
    return response


def page(request, queryset, per_page=20):
    return Paginator(queryset, per_page).get_page(request.GET.get("page"))


@employee_required
def dashboard(request):
    today = timezone.localdate()
    start = today - timedelta(days=6)
    today_sales = list(sales_with_dashboard_totals(Sale.objects.filter(sale_date=today)))
    all_open_sales = sales_with_dashboard_totals(Sale.objects.exclude(payment_status="paid"))

    sales_total = sum((sale.dashboard_total for sale in today_sales), Decimal("0"))
    gas_units = SaleItem.objects.filter(sale__sale_date=today, cylinder__product_type="cylinder_gas").aggregate(qty=Coalesce(Sum("quantity"), 0))["qty"]
    collected = Payment.objects.filter(payment_date=today).aggregate(total=money_sum("amount"))["total"]
    outstanding = sum((sale.dashboard_balance for sale in all_open_sales), Decimal("0"))

    daily_map = {}
    for sale in sales_with_dashboard_totals(Sale.objects.filter(sale_date__range=(start, today))):
        daily_map[sale.sale_date] = daily_map.get(sale.sale_date, Decimal("0")) + sale.dashboard_total
    collected_rows = Payment.objects.filter(payment_date__range=(start, today)).values("payment_date").annotate(total=money_sum("amount"))
    collected_map = {row["payment_date"]: row["total"] for row in collected_rows}
    chart_labels, chart_values, chart_collected = [], [], []
    for offset in range(7):
        day = start + timedelta(days=offset)
        chart_labels.append(day.strftime("%a"))
        chart_values.append(float(daily_map.get(day, 0)))
        chart_collected.append(float(collected_map.get(day, 0)))

    low_stock_queryset = (
        GasCylinder.objects.filter(is_active=True, stock_quantity__lte=F("reorder_level"))
        .annotate(
            shortage=F("reorder_level") - F("stock_quantity"),
            product_priority=Case(When(product_type="cylinder_gas", then=Value(0)), default=Value(1), output_field=IntegerField()),
        )
        .order_by("product_priority", "stock_quantity")
    )
    today_cost = SaleItem.objects.filter(sale__sale_date=today).aggregate(total=money_sum("line_cost"))["total"]
    today_expenses = Expense.objects.filter(expense_date=today).aggregate(total=money_sum("amount"))["total"]

    context = {
        "today": today,
        "sales_total": sales_total,
        "sales_count": len(today_sales),
        "gas_units": gas_units,
        "collected": collected,
        "outstanding": outstanding,
        "gross_profit": sales_total - today_cost,
        "today_expenses": today_expenses,
        "net_cash": collected - today_expenses,
        "recent_sales": sales_with_dashboard_totals(Sale.objects.select_related("customer", "created_by"))[:7],
        "low_stock": low_stock_queryset[:5],
        "low_stock_count": low_stock_queryset.count(),
        "chart_labels": json.dumps(chart_labels),
        "chart_values": json.dumps(chart_values),
        "chart_collected": json.dumps(chart_collected),
    }
    return render(request, "core/dashboard.html", context)


@employee_required
def customer_list(request):
    q = request.GET.get("q", "").strip()
    customers = Customer.objects.all()
    if q:
        customers = customers.filter(Q(name__icontains=q) | Q(phone__icontains=q) | Q(alternate_phone__icontains=q))
    return render(request, "core/customer_list.html", {"customers": page(request, customers), "q": q})


@employee_required
def customer_search(request):
    query = request.GET.get("q", "").strip()
    if len(query) < 2:
        return JsonResponse({"results": []})
    customers = Customer.objects.filter(Q(phone__icontains=query) | Q(name__icontains=query)).order_by("name")[:8]
    return JsonResponse(
        {
            "results": [
                {
                    "id": customer.pk,
                    "name": customer.name,
                    "phone": customer.phone,
                    "address": customer.address,
                    "balance": f"{customer.total_balance:.2f}",
                }
                for customer in customers
            ]
        }
    )


@employee_required
def customer_create(request):
    form = CustomerForm(request.POST or None)
    if form.is_valid():
        customer_obj = form.save()
        messages.success(request, f"Customer {customer_obj.name} was added.")
        next_url = request.GET.get("next")
        return redirect(next_url if next_url and next_url.startswith("/") else customer_obj)
    return render(request, "core/form.html", {"form": form, "title": "Add customer", "subtitle": "Save contact details once and use them on every future sale.", "submit_label": "Save customer"})


@employee_required
def customer_edit(request, pk):
    customer_obj = get_object_or_404(Customer, pk=pk)
    form = CustomerForm(request.POST or None, instance=customer_obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Customer details updated.")
        return redirect(customer_obj)
    return render(request, "core/form.html", {"form": form, "title": "Edit customer", "submit_label": "Update customer"})


@employee_required
def customer_detail(request, pk):
    customer_obj = get_object_or_404(Customer, pk=pk)
    sales = customer_obj.sales.select_related("created_by").prefetch_related("items__cylinder", "payments")
    return render(request, "core/customer_detail.html", {"customer_record": customer_obj, "sales": sales})


@employee_required
def cylinder_list(request):
    q = request.GET.get("q", "").strip()
    cylinders = GasCylinder.objects.all()
    if q:
        cylinders = cylinders.filter(Q(name__icontains=q) | Q(size__icontains=q))
    movements = StockMovement.objects.select_related("cylinder", "created_by")[:12]
    return render(request, "core/cylinder_list.html", {"cylinders": page(request, cylinders, 12), "movements": movements, "q": q})


@admin_required
def cylinder_create(request):
    form = GasCylinderForm(request.POST or None, request.FILES or None)
    if form.is_valid():
        with transaction.atomic():
            product = form.save(commit=False)
            product.stock_quantity = form.cleaned_data.get("opening_stock") or 0
            product.save()
            if product.stock_quantity:
                StockMovement.objects.create(
                    cylinder=product,
                    movement_type="opening",
                    product_change=product.stock_quantity,
                    notes="Opening stock",
                    created_by=request.user,
                )
        messages.success(request, "Product added to inventory.")
        return redirect("cylinder_list")
    return render(request, "core/product_form.html", {"form": form, "title": "Add product", "subtitle": "Choose cooking machine, new cylinder, or cylinder gas. Each has its own price and stock.", "submit_label": "Save product"})


@admin_required
def cylinder_edit(request, pk):
    cylinder = get_object_or_404(GasCylinder, pk=pk)
    form = GasCylinderForm(request.POST or None, request.FILES or None, instance=cylinder)
    if form.is_valid():
        form.save()
        messages.success(request, "Product updated.")
        return redirect("cylinder_list")
    return render(request, "core/product_form.html", {"form": form, "title": "Edit product", "subtitle": "Update prices and reorder levels. Use Receive stock to increase quantities.", "submit_label": "Update product"})


@admin_required
def stock_movement_create(request):
    form = StockMovementForm(request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            selected = form.cleaned_data["cylinder"]
            product = GasCylinder.objects.select_for_update().get(pk=selected.pk)
            quantity = form.cleaned_data["quantity"]
            product.stock_quantity += quantity
            product.save(update_fields=["stock_quantity", "updated_at"])
            StockMovement.objects.create(
                cylinder=product,
                movement_type="received",
                product_change=quantity,
                notes=form.cleaned_data["notes"],
                created_by=request.user,
            )
            messages.success(request, "Stock received and recorded.")
            return redirect("cylinder_list")
    return render(request, "core/form.html", {"form": form, "title": "Receive stock", "subtitle": "Choose a product and enter the quantity received.", "submit_label": "Receive stock"})


@employee_required
def sale_list(request):
    q = request.GET.get("q", "").strip()
    status = request.GET.get("status", "")
    sales = Sale.objects.select_related("customer", "created_by").prefetch_related("items", "payments")
    if q:
        sales = sales.filter(Q(invoice_number__icontains=q) | Q(customer__name__icontains=q) | Q(customer__phone__icontains=q))
    if status in dict(Sale.PAYMENT_STATUS):
        sales = sales.filter(payment_status=status)
    return render(request, "core/sale_list.html", {"sales": page(request, sales), "q": q, "status": status, "statuses": Sale.PAYMENT_STATUS})


def next_invoice_number(day):
    prefix = f"GS-{day:%Y%m%d}-"
    latest = Sale.objects.filter(invoice_number__startswith=prefix).order_by("-invoice_number").values_list("invoice_number", flat=True).first()
    sequence = int(latest.rsplit("-", 1)[-1]) + 1 if latest else 1
    return f"{prefix}{sequence:04d}"


@employee_required
def sale_create(request):
    sale = Sale(created_by=request.user)
    form = SaleForm(request.POST or None, instance=sale)
    formset = SaleItemFormSet(request.POST or None, instance=sale, prefix="items")
    if request.method == "POST" and form.is_valid() and formset.is_valid():
        item_forms = [item_form for item_form in formset.forms if item_form.cleaned_data and not item_form.cleaned_data.get("DELETE")]
        cylinder_ids = [item_form.cleaned_data["cylinder"].pk for item_form in item_forms]
        if len(cylinder_ids) != len(set(cylinder_ids)):
            messages.error(request, "Add each product only once; increase its quantity instead.")
        else:
            try:
                with transaction.atomic():
                    customer_phone = form.cleaned_data["customer_phone"]
                    customer_name = form.cleaned_data["customer_name"].strip()
                    customer_obj = Customer.objects.select_for_update().filter(phone=customer_phone).first()
                    if customer_obj is None:
                        customer_obj = Customer.objects.create(phone=customer_phone, name=customer_name)

                    locked_cylinders = {item.pk: item for item in GasCylinder.objects.select_for_update().filter(pk__in=cylinder_ids)}
                    for item_form in item_forms:
                        cylinder = locked_cylinders[item_form.cleaned_data["cylinder"].pk]
                        quantity = item_form.cleaned_data["quantity"]
                        if quantity > cylinder.stock_quantity:
                            raise ValueError(f"Only {cylinder.stock_quantity} × {cylinder} are in stock.")

                    sale = form.save(commit=False)
                    sale.customer = customer_obj
                    sale.created_by = request.user
                    sale.invoice_number = next_invoice_number(sale.sale_date)
                    sale.save()
                    for item_form in item_forms:
                        item = item_form.save(commit=False)
                        item.sale = sale
                        item.unit_cost = item.cylinder.cost_price
                        item.save()
                        cylinder = locked_cylinders[item.cylinder_id]
                        cylinder.stock_quantity -= item.quantity
                        cylinder.save(update_fields=["stock_quantity", "updated_at"])
                        StockMovement.objects.create(
                            cylinder=cylinder,
                            movement_type="sale",
                            product_change=-item.quantity,
                            sale=sale,
                            notes=f"Invoice {sale.invoice_number}",
                            created_by=request.user,
                        )
                    if sale.discount > sale.subtotal:
                        raise ValueError("Discount cannot be greater than the sale subtotal.")
                    marked_paid = form.cleaned_data["payment_status_choice"] == "paid"
                    if marked_paid and sale.total > 0:
                        Payment.objects.create(
                            sale=sale,
                            amount=sale.total,
                            payment_date=sale.sale_date,
                            method=form.cleaned_data["payment_method"],
                            notes="Recorded with sale",
                            received_by=request.user,
                        )
                        sale.refresh_payment_status()
                    elif marked_paid:
                        Sale.objects.filter(pk=sale.pk).update(payment_status="paid")
                        sale.payment_status = "paid"
                    else:
                        sale.refresh_payment_status()
                company_settings = company()
                if company_settings.auto_send_whatsapp:
                    send_sale_whatsapp(sale, request.user, company_settings)
                messages.success(request, f"Sale {sale.invoice_number} recorded as {sale.get_payment_status_display().lower()}.")
                return redirect(sale)
            except (ValueError, IntegrityError) as exc:
                messages.error(request, str(exc))
    cylinder_prices = {str(cylinder.pk): str(cylinder.selling_price) for cylinder in GasCylinder.objects.filter(is_active=True)}
    return render(request, "core/sale_form.html", {"form": form, "formset": formset, "cylinder_prices": cylinder_prices})


@employee_required
def sale_detail(request, pk):
    sale = get_object_or_404(Sale.objects.select_related("customer", "created_by").prefetch_related("items__cylinder", "payments__received_by"), pk=pk)
    return render(request, "core/sale_detail.html", {"sale": sale})


@employee_required
def invoice(request, pk):
    sale = get_object_or_404(Sale.objects.select_related("customer", "created_by").prefetch_related("items__cylinder", "payments"), pk=pk)
    return render(request, "core/invoice.html", {"sale": sale})


@employee_required
def payment_create(request, pk):
    sale = get_object_or_404(Sale.objects.prefetch_related("items", "payments"), pk=pk)
    if sale.balance <= 0:
        messages.info(request, "This invoice is already paid in full.")
        return redirect(sale)
    form = PaymentForm(request.POST or None, sale=sale, initial={"amount": sale.balance})
    if form.is_valid():
        payment_saved = False
        with transaction.atomic():
            locked_sale = Sale.objects.select_for_update().get(pk=sale.pk)
            if form.cleaned_data["amount"] > locked_sale.balance:
                form.add_error("amount", "Another payment was recorded first. Refresh and enter no more than the new balance.")
            else:
                payment = form.save(commit=False)
                payment.sale = locked_sale
                payment.received_by = request.user
                payment.save()
                locked_sale.refresh_payment_status()
                payment_saved = True
        if payment_saved:
            company_settings = company()
            if company_settings.auto_send_whatsapp:
                send_sale_whatsapp(locked_sale, request.user, company_settings)
            messages.success(request, "Payment recorded and balance updated.")
            return redirect(sale)
    return render(request, "core/form.html", {"form": form, "title": f"Record payment — {sale.invoice_number}", "subtitle": f"Customer: {sale.customer.name}", "submit_label": "Save payment"})


@require_POST
@employee_required
def sale_mark_paid(request, pk):
    payment_saved = None
    with transaction.atomic():
        sale = get_object_or_404(Sale.objects.select_for_update().prefetch_related("items", "payments"), pk=pk)
        remaining = sale.balance
        if remaining > 0:
            method = request.POST.get("method", "cash")
            if method not in dict(Payment.METHODS):
                method = "cash"
            payment_saved = Payment.objects.create(
                sale=sale,
                amount=remaining,
                payment_date=timezone.localdate(),
                method=method,
                notes="Remaining balance paid in full",
                received_by=request.user,
            )
            sale.refresh_payment_status()
    if payment_saved:
        company_settings = company()
        if company_settings.auto_send_whatsapp:
            send_sale_whatsapp(sale, request.user, company_settings)
        messages.success(request, f"{sale.invoice_number} was marked paid. The remaining balance was recorded.")
    else:
        messages.info(request, "This invoice is already paid in full.")
    next_url = request.POST.get("next", "")
    if next_url and url_has_allowed_host_and_scheme(next_url, allowed_hosts={request.get_host()}, require_https=request.is_secure()):
        return redirect(next_url)
    return redirect(sale)


@require_POST
@employee_required
def whatsapp_sale(request, pk):
    sale = get_object_or_404(Sale.objects.select_related("customer").prefetch_related("items", "payments"), pk=pk)
    result = send_sale_whatsapp(sale, request.user, company())
    if result["sent"]:
        messages.success(request, "WhatsApp invoice message sent.")
    else:
        messages.info(request, "WhatsApp is ready. Complete sending in the opened WhatsApp window.")
    if request.headers.get("x-requested-with") == "XMLHttpRequest":
        return JsonResponse({"sent": result["sent"], "link": result["link"]})
    return redirect(result["link"] or sale.get_absolute_url())


@admin_required
def expense_list(request):
    expenses = Expense.objects.select_related("recorded_by")
    total = expenses.aggregate(total=money_sum("amount"))["total"]
    return render(request, "core/expense_list.html", {"expenses": page(request, expenses), "total": total})


@admin_required
def expense_create(request):
    form = ExpenseForm(request.POST or None)
    if form.is_valid():
        expense = form.save(commit=False)
        expense.recorded_by = request.user
        expense.save()
        messages.success(request, "Expense recorded.")
        return redirect("expense_list")
    return render(request, "core/form.html", {"form": form, "title": "Record expense", "submit_label": "Save expense"})


@admin_required
def reports(request):
    today = timezone.localdate()
    this_month_start = today.replace(day=1)
    previous_month_end = this_month_start - timedelta(days=1)
    periods = {
        "today": (today, today),
        "last_7_days": (today - timedelta(days=6), today),
        "this_month": (this_month_start, today),
        "last_month": (previous_month_end.replace(day=1), previous_month_end),
    }
    requested_period = request.GET.get("period", "")
    if not requested_period and (request.GET.get("start") or request.GET.get("end")):
        requested_period = "range"
    period = requested_period if requested_period in {*periods, "range"} else "this_month"

    if period == "range":
        try:
            start = timezone.datetime.strptime(request.GET.get("start", ""), "%Y-%m-%d").date()
        except ValueError:
            start = this_month_start
        try:
            end = timezone.datetime.strptime(request.GET.get("end", ""), "%Y-%m-%d").date()
        except ValueError:
            end = today
    else:
        start, end = periods[period]
    if start > end:
        start, end = end, start

    sales = Sale.objects.filter(sale_date__range=(start, end)).prefetch_related("items", "payments")
    revenue = sum((sale.total for sale in sales), Decimal("0"))
    gross_profit = sum((sale.gross_profit for sale in sales), Decimal("0"))
    units = SaleItem.objects.filter(sale__sale_date__range=(start, end)).aggregate(qty=Coalesce(Sum("quantity"), 0))["qty"]
    gas_only_sales = SaleItem.objects.filter(sale__sale_date__range=(start, end), cylinder__product_type="cylinder_gas").aggregate(qty=Coalesce(Sum("quantity"), 0))["qty"]
    collected = Payment.objects.filter(payment_date__range=(start, end)).aggregate(total=money_sum("amount"))["total"]
    expense_total = Expense.objects.filter(expense_date__range=(start, end)).aggregate(total=money_sum("amount"))["total"]
    popular = (
        SaleItem.objects.filter(sale__sale_date__range=(start, end))
        .values("cylinder__name", "cylinder__size")
        .annotate(quantity=Sum("quantity"), revenue=money_sum("line_total"))
        .order_by("-quantity")[:8]
    )
    daily = (
        SaleItem.objects.filter(sale__sale_date__range=(start, end))
        .values(date=F("sale__sale_date"))
        .annotate(quantity=Sum("quantity"), revenue=money_sum("line_total"))
        .order_by("-date")
    )
    return render(
        request,
        "core/reports.html",
        {
            "start": start,
            "end": end,
            "period": period,
            "revenue": revenue,
            "gross_profit": gross_profit,
            "operating_profit": gross_profit - expense_total,
            "units": units,
            "gas_only_sales": gas_only_sales,
            "collected": collected,
            "expense_total": expense_total,
            "net_cash": collected - expense_total,
            "popular": popular,
            "daily": daily,
        },
    )


@admin_required
def settings_view(request):
    settings_obj = company()
    form = CompanySettingForm(request.POST or None, instance=settings_obj)
    if form.is_valid():
        form.save()
        messages.success(request, "Company settings updated.")
        return redirect("settings")
    return render(request, "core/form.html", {"form": form, "title": "Company settings", "subtitle": "These details appear on invoices and customer messages.", "submit_label": "Save settings"})


@admin_required
def employee_list(request):
    employees = (
        get_user_model().objects.filter(is_superuser=False)
        .select_related("employee_profile")
        .annotate(sales_recorded=Count("sales_created", distinct=True), payments_recorded=Count("payments_received", distinct=True))
        .order_by("-is_active", "first_name", "username")
    )
    return render(request, "core/employee_list.html", {"employees": employees})


@admin_required
def employee_create(request):
    form = EmployeeForm(request.POST or None)
    if form.is_valid():
        with transaction.atomic():
            employee = form.save()
        messages.success(request, f"Employee {employee.get_full_name() or employee.username} was added and authorized.")
        return redirect("employee_list")
    return render(request, "core/form.html", {"form": form, "title": "Add employee", "subtitle": "Create a secure sign-in for an authorized staff member.", "submit_label": "Create employee"})


@admin_required
def employee_edit(request, pk):
    employee = get_object_or_404(get_user_model().objects.filter(is_superuser=False), pk=pk)
    form = EmployeeForm(request.POST or None, instance=employee)
    if form.is_valid():
        with transaction.atomic():
            employee = form.save()
        messages.success(request, f"Employee {employee.get_full_name() or employee.username} was updated.")
        return redirect("employee_list")
    return render(request, "core/form.html", {"form": form, "title": "Edit employee", "subtitle": "Update the profile, password, or sign-in authorization.", "submit_label": "Save employee"})
