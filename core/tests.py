from datetime import date, timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse

from .models import Customer, EmployeeProfile, Expense, GasCylinder, Payment, Sale, SaleItem, StockMovement, WhatsAppLog


class GasFlowTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(username="manager", password="StrongPass123!")
        self.customer = Customer.objects.create(name="Amina Hassan", phone="252611111111")
        self.cylinder = GasCylinder.objects.create(name="SomGas New Cylinder", size="13 kg", product_type="new_cylinder", selling_price="48.00", cost_price="32.00", stock_quantity=10)
        self.gas = GasCylinder.objects.create(name="SomGas Cylinder Gas", size="13 kg", product_type="cylinder_gas", selling_price="12.00", cost_price="7.00", stock_quantity=10)

    def login(self):
        self.client.login(username="manager", password="StrongPass123!")

    def test_root_is_login_and_private_pages_require_authentication(self):
        response = self.client.get(reverse("login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Welcome back")
        response = self.client.get(reverse("dashboard"))
        self.assertRedirects(response, "/?next=/dashboard/")

    def test_customer_can_be_found_by_phone(self):
        self.login()
        response = self.client.get(reverse("customer_list"), {"q": "611111"})
        self.assertContains(response, "Amina Hassan")

    def test_recording_sale_creates_invoice_and_deducts_stock(self):
        self.login()
        data = {
            "customer_phone": self.customer.phone,
            "customer_name": self.customer.name,
            "sale_date": date.today().isoformat(),
            "discount": "3.00",
            "notes": "Delivered",
            "payment_status_choice": "paid",
            "payment_method": "mobile",
            "items-TOTAL_FORMS": "3",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-cylinder": self.cylinder.pk,
            "items-0-quantity": "2",
            "items-0-unit_price": "48.00",
            "items-1-cylinder": "",
            "items-1-quantity": "1",
            "items-1-unit_price": "",
            "items-2-cylinder": "",
            "items-2-quantity": "1",
            "items-2-unit_price": "",
        }
        response = self.client.post(reverse("sale_create"), data)
        sale = Sale.objects.get()
        self.assertRedirects(response, sale.get_absolute_url())
        self.assertEqual(sale.total, Decimal("93.00"))
        self.assertEqual(sale.payment_status, "paid")
        self.assertEqual(sale.amount_paid, Decimal("93.00"))
        self.assertEqual(sale.payments.get().method, "mobile")
        self.cylinder.refresh_from_db()
        self.assertEqual(self.cylinder.stock_quantity, 8)

    def test_payment_updates_invoice_status_and_balance(self):
        self.login()
        sale = Sale.objects.create(invoice_number="GS-TEST-0001", customer=self.customer, sale_date=date.today(), created_by=self.user)
        SaleItem.objects.create(sale=sale, cylinder=self.cylinder, quantity=1, unit_price="48.00")
        response = self.client.post(reverse("payment_create", args=[sale.pk]), {"amount": "20.00", "payment_date": date.today(), "method": "cash", "reference": "", "notes": ""})
        self.assertRedirects(response, sale.get_absolute_url())
        sale.refresh_from_db()
        self.assertEqual(sale.payment_status, "partial")
        self.assertEqual(sale.balance, Decimal("28.00"))

    def test_sale_can_be_marked_fully_paid_from_invoice_or_sales_list(self):
        self.login()
        sale = Sale.objects.create(invoice_number="GS-TEST-LATER", customer=self.customer, sale_date=date.today(), created_by=self.user)
        SaleItem.objects.create(sale=sale, cylinder=self.cylinder, quantity=1, unit_price="48.00")
        Payment.objects.create(sale=sale, amount="8.00", payment_date=date.today(), method="cash", received_by=self.user)
        sale.refresh_payment_status()

        response = self.client.post(
            reverse("sale_mark_paid", args=[sale.pk]),
            {"method": "mobile", "next": reverse("sale_list") + "?status=partial"},
        )

        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("sale_list") + "?status=partial")
        sale.refresh_from_db()
        final_payment = sale.payments.order_by("-id").first()
        self.assertEqual(final_payment.amount, Decimal("40.00"))
        self.assertEqual(final_payment.method, "mobile")
        self.assertEqual(final_payment.payment_date, date.today())
        self.assertEqual(sale.payment_status, "paid")
        self.assertEqual(sale.balance, Decimal("0.00"))

    def test_sales_and_report_filters_are_automatic(self):
        self.login()
        sales_response = self.client.get(reverse("sale_list"))
        self.assertContains(sales_response, 'id="sales-filter-form"')
        self.assertContains(sales_response, 'id="sales-search"')
        self.assertNotContains(sales_response, ">Filter</button>")

        report_response = self.client.get(reverse("reports"))
        self.assertContains(report_response, 'id="report-filter-form"')
        self.assertContains(report_response, 'id="report-period"')
        self.assertContains(report_response, 'value="range"')
        self.assertNotContains(report_response, ">Apply</button>")

    def test_report_period_dropdown_calculates_dates(self):
        self.login()
        today = date.today()

        response = self.client.get(reverse("reports"), {"period": "today"})
        self.assertEqual(response.context["start"], today)
        self.assertEqual(response.context["end"], today)
        self.assertEqual(response.context["period"], "today")

        response = self.client.get(reverse("reports"), {"period": "last_7_days"})
        self.assertEqual(response.context["start"], today - timedelta(days=6))
        self.assertEqual(response.context["end"], today)

        response = self.client.get(
            reverse("reports"),
            {"period": "range", "start": "2026-08-20", "end": "2026-08-10"},
        )
        self.assertEqual(response.context["start"], date(2026, 8, 10))
        self.assertEqual(response.context["end"], date(2026, 8, 20))

    @override_settings(WHATSAPP_ACCESS_TOKEN="", WHATSAPP_PHONE_NUMBER_ID="")
    def test_whatsapp_falls_back_to_secure_click_to_send_link(self):
        self.login()
        sale = Sale.objects.create(invoice_number="GS-TEST-0002", customer=self.customer, sale_date=date.today(), created_by=self.user)
        SaleItem.objects.create(sale=sale, cylinder=self.cylinder, quantity=1, unit_price="48.00")
        response = self.client.post(reverse("whatsapp_sale", args=[sale.pk]), HTTP_X_REQUESTED_WITH="XMLHttpRequest")
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["link"].startswith("https://wa.me/"))
        self.assertEqual(WhatsAppLog.objects.get().status, "link")

    def test_primary_authenticated_pages_render(self):
        self.login()
        sale = Sale.objects.create(invoice_number="GS-TEST-0003", customer=self.customer, sale_date=date.today(), created_by=self.user)
        SaleItem.objects.create(sale=sale, cylinder=self.cylinder, quantity=1, unit_price="48.00")
        Payment.objects.create(sale=sale, amount="10.00", payment_date=date.today(), method="cash", received_by=self.user)
        Expense.objects.create(expense_date=date.today(), category="transport", description="Delivery fuel", amount="5.00", recorded_by=self.user)
        urls = [
            reverse("dashboard"),
            reverse("customer_list"),
            reverse("customer_detail", args=[self.customer.pk]),
            reverse("cylinder_list"),
            reverse("sale_list"),
            reverse("sale_create"),
            reverse("sale_detail", args=[sale.pk]),
            reverse("invoice", args=[sale.pk]),
            reverse("expense_list"),
            reverse("reports"),
            reverse("password_change"),
        ]
        for url in urls:
            with self.subTest(url=url):
                response = self.client.get(url)
                self.assertEqual(response.status_code, 200)

    def test_phone_lookup_and_new_customer_creation_during_sale(self):
        self.login()
        lookup = self.client.get(reverse("customer_search"), {"q": "611111"})
        self.assertEqual(lookup.status_code, 200)
        self.assertEqual(lookup.json()["results"][0]["name"], "Amina Hassan")

        data = {
            "customer_phone": "252622222222",
            "customer_name": "Mohamed Ali",
            "sale_date": date.today().isoformat(),
            "discount": "0.00",
            "notes": "",
            "items-TOTAL_FORMS": "3",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-cylinder": self.cylinder.pk,
            "items-0-quantity": "1",
            "items-0-unit_price": "48.00",
            "items-1-cylinder": "",
            "items-1-quantity": "1",
            "items-1-unit_price": "",
            "items-2-cylinder": "",
            "items-2-quantity": "1",
            "items-2-unit_price": "",
        }
        response = self.client.post(reverse("sale_create"), data)
        self.assertEqual(response.status_code, 302)
        self.assertTrue(Customer.objects.filter(phone="252622222222", name="Mohamed Ali").exists())

    def test_new_sale_starts_with_one_product_line(self):
        self.login()
        response = self.client.get(reverse("sale_create"))
        self.assertEqual(response.context["formset"].total_form_count(), 1)
        self.assertContains(response, "Add another product")

    def test_gas_only_sale_does_not_reduce_cylinder_stock(self):
        self.login()
        data = {
            "customer_phone": self.customer.phone,
            "customer_name": self.customer.name,
            "sale_date": date.today().isoformat(),
            "discount": "0.00",
            "notes": "Customer owns cylinder",
            "items-TOTAL_FORMS": "3",
            "items-INITIAL_FORMS": "0",
            "items-MIN_NUM_FORMS": "1",
            "items-MAX_NUM_FORMS": "1000",
            "items-0-cylinder": self.gas.pk,
            "items-0-quantity": "2",
            "items-0-unit_price": "12.00",
            "items-1-cylinder": "",
            "items-1-quantity": "1",
            "items-1-unit_price": "",
            "items-2-cylinder": "",
            "items-2-quantity": "1",
            "items-2-unit_price": "",
        }
        response = self.client.post(reverse("sale_create"), data)
        self.assertEqual(response.status_code, 302)
        self.cylinder.refresh_from_db()
        self.gas.refresh_from_db()
        self.assertEqual(self.cylinder.stock_quantity, 10)
        self.assertEqual(self.gas.stock_quantity, 8)
        sale_item = SaleItem.objects.get()
        self.assertEqual(sale_item.unit_cost, Decimal("7.00"))
        movement = StockMovement.objects.get(movement_type="sale")
        self.assertEqual(movement.product_change, -2)

    def test_receiving_cylinder_gas_stock(self):
        self.login()
        self.gas.stock_quantity = 4
        self.gas.save()
        response = self.client.post(
            reverse("stock_movement_create"),
            {"cylinder": self.gas.pk, "quantity": 3, "notes": "Gas received"},
        )
        self.assertRedirects(response, reverse("cylinder_list"))
        self.gas.refresh_from_db()
        self.assertEqual(self.gas.stock_quantity, 7)

    def test_admin_can_create_and_deactivate_employee(self):
        self.login()
        response = self.client.post(
            reverse("employee_create"),
            {
                "username": "cashier",
                "first_name": "Fadumo",
                "last_name": "Ali",
                "email": "",
                "phone": "252633333333",
                "job_title": "Sales employee",
                "is_active": "on",
                "password1": "SecureEmployee123!",
                "password2": "SecureEmployee123!",
            },
        )
        employee = get_user_model().objects.get(username="cashier")
        self.assertRedirects(response, reverse("employee_list"))
        self.assertTrue(employee.check_password("SecureEmployee123!"))
        self.assertFalse(employee.is_staff)
        self.assertEqual(employee.employee_profile.phone, "252633333333")

        response = self.client.post(
            reverse("employee_edit", args=[employee.pk]),
            {
                "username": "cashier",
                "first_name": "Fadumo",
                "last_name": "Ali",
                "email": "",
                "phone": "252633333333",
                "job_title": "Sales employee",
                "password1": "",
                "password2": "",
            },
        )
        employee.refresh_from_db()
        self.assertRedirects(response, reverse("employee_list"))
        self.assertFalse(employee.is_active)

    def test_employee_can_sell_but_cannot_open_admin_pages(self):
        employee = get_user_model().objects.create_user(username="seller", password="StrongPass123!", first_name="Sahra")
        EmployeeProfile.objects.create(user=employee, job_title="Sales employee")
        self.client.login(username="seller", password="StrongPass123!")
        for url in [reverse("dashboard"), reverse("sale_create"), reverse("customer_list"), reverse("cylinder_list")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 200)
        for url in [reverse("cylinder_create"), reverse("stock_movement_create"), reverse("expense_list"), reverse("reports"), reverse("employee_list"), reverse("settings")]:
            with self.subTest(url=url):
                self.assertEqual(self.client.get(url).status_code, 403)

    def test_unprofiled_user_is_not_authorized(self):
        get_user_model().objects.create_user(username="unknown", password="StrongPass123!")
        self.client.login(username="unknown", password="StrongPass123!")
        self.assertEqual(self.client.get(reverse("dashboard")).status_code, 403)
        self.client.post(reverse("logout"))
        response = self.client.post(reverse("login"), {"username": "unknown", "password": "StrongPass123!"})
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "has not been authorized")

    def test_language_toggle_switches_complete_interface_to_somali(self):
        self.login()
        response = self.client.post(reverse("language_switch"), {"language": "so", "next": reverse("dashboard")}, follow=True)
        self.assertContains(response, "Bogga guud")
        self.assertContains(response, "Iibka maanta")
        self.assertContains(response, "Deynta macaamiisha")
        self.assertContains(response, "Soomaali")

        self.client.post(reverse("logout"))
        response = self.client.get(reverse("login"))
        self.assertContains(response, "Soo dhawoow mar kale")
        response = self.client.post(reverse("language_switch"), {"language": "en", "next": reverse("login")}, follow=True)
        self.assertContains(response, "Welcome back")
