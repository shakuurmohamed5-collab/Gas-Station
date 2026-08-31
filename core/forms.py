from decimal import Decimal

from django import forms
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import AuthenticationForm, PasswordChangeForm
from django.contrib.auth.password_validation import validate_password
from django.forms import inlineformset_factory

from .models import CompanySetting, Customer, EmployeeProfile, Expense, GasCylinder, Payment, Sale, SaleItem


class BootstrapFormMixin:
    def _apply_bootstrap(self):
        for field in self.fields.values():
            widget = field.widget
            if isinstance(widget, forms.CheckboxInput):
                widget.attrs["class"] = "form-check-input"
            elif isinstance(widget, forms.Select):
                widget.attrs["class"] = "form-select"
            else:
                widget.attrs["class"] = "form-control"
            if field.required:
                widget.attrs.setdefault("required", True)


class LoginForm(BootstrapFormMixin, AuthenticationForm):
    username = forms.CharField(widget=forms.TextInput(attrs={"autofocus": True, "placeholder": "Username"}))
    password = forms.CharField(strip=False, widget=forms.PasswordInput(attrs={"placeholder": "Password"}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()

    def confirm_login_allowed(self, user):
        super().confirm_login_allowed(user)
        if not user.is_superuser and not EmployeeProfile.objects.filter(user=user).exists():
            raise forms.ValidationError("This account has not been authorized by an administrator.", code="unauthorized")


class StyledPasswordChangeForm(BootstrapFormMixin, PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class EmployeeForm(BootstrapFormMixin, forms.Form):
    username = forms.CharField(max_length=150, help_text="Used by the employee to sign in.")
    first_name = forms.CharField(max_length=150)
    last_name = forms.CharField(max_length=150, required=False)
    email = forms.EmailField(required=False)
    phone = forms.CharField(max_length=30, required=False)
    job_title = forms.CharField(max_length=80, required=False, initial="Employee")
    is_active = forms.BooleanField(required=False, initial=True, label="Authorized to sign in")
    password1 = forms.CharField(label="Password", strip=False, widget=forms.PasswordInput, required=False)
    password2 = forms.CharField(label="Confirm password", strip=False, widget=forms.PasswordInput, required=False)

    def __init__(self, *args, instance=None, **kwargs):
        self.instance = instance
        super().__init__(*args, **kwargs)
        if instance:
            profile = getattr(instance, "employee_profile", None)
            self.initial.update(
                {
                    "username": instance.username,
                    "first_name": instance.first_name,
                    "last_name": instance.last_name,
                    "email": instance.email,
                    "phone": profile.phone if profile else "",
                    "job_title": profile.job_title if profile else "Employee",
                    "is_active": instance.is_active,
                }
            )
            self.fields["password1"].help_text = "Leave blank to keep the current password."
        else:
            self.fields["password1"].required = True
            self.fields["password2"].required = True
        self._apply_bootstrap()

    def clean_username(self):
        username = self.cleaned_data["username"].strip()
        users = get_user_model().objects.filter(username__iexact=username)
        if self.instance:
            users = users.exclude(pk=self.instance.pk)
        if users.exists():
            raise forms.ValidationError("That username is already in use.")
        return username

    def clean(self):
        cleaned = super().clean()
        password = cleaned.get("password1")
        if password != cleaned.get("password2"):
            self.add_error("password2", "The passwords do not match.")
        if password:
            candidate = self.instance or get_user_model()(username=cleaned.get("username", ""))
            validate_password(password, candidate)
        return cleaned

    def save(self):
        user = self.instance or get_user_model()()
        user.username = self.cleaned_data["username"]
        user.first_name = self.cleaned_data["first_name"].strip()
        user.last_name = self.cleaned_data["last_name"].strip()
        user.email = self.cleaned_data["email"].strip()
        user.is_active = self.cleaned_data["is_active"]
        user.is_staff = False
        user.is_superuser = False
        if self.cleaned_data.get("password1"):
            user.set_password(self.cleaned_data["password1"])
        user.save()
        EmployeeProfile.objects.update_or_create(
            user=user,
            defaults={"phone": self.cleaned_data["phone"].strip(), "job_title": self.cleaned_data["job_title"].strip() or "Employee"},
        )
        return user


class CustomerForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Customer
        fields = ("name", "phone", "alternate_phone", "address", "notes")
        widgets = {"notes": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        self.fields["phone"].help_text = "Use the customer's WhatsApp number, including country code when possible."

    def clean_phone(self):
        return "".join(self.cleaned_data["phone"].split())


class GasCylinderForm(BootstrapFormMixin, forms.ModelForm):
    opening_stock = forms.IntegerField(min_value=0, initial=0, required=False, label="Opening stock")

    class Meta:
        model = GasCylinder
        fields = ("product_type", "name", "size", "image", "selling_price", "cost_price", "opening_stock", "reorder_level", "is_active", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        self.fields["image"].widget.attrs["accept"] = "image/*"
        self.fields["selling_price"].label = "Selling price"
        self.fields["cost_price"].label = "Cost price"
        self.fields["size"].label = "Size / model"
        if self.instance and self.instance.pk:
            self.fields.pop("opening_stock")


class SaleForm(BootstrapFormMixin, forms.ModelForm):
    payment_status_choice = forms.ChoiceField(
        label="Payment status",
        choices=(("paid", "Paid"), ("unpaid", "Unpaid")),
        initial="paid",
        required=False,
        widget=forms.RadioSelect,
    )
    payment_method = forms.ChoiceField(label="Payment method", choices=Payment.METHODS, initial="cash", required=False)
    customer_phone = forms.CharField(
        max_length=30,
        label="Customer phone number",
        widget=forms.TextInput(
            attrs={
                "inputmode": "tel",
                "autocomplete": "off",
                "placeholder": "Start typing the phone number…",
            }
        ),
    )
    customer_name = forms.CharField(
        max_length=120,
        label="Customer name",
        widget=forms.TextInput(attrs={"autocomplete": "name", "placeholder": "Enter or confirm the customer name"}),
    )

    class Meta:
        model = Sale
        fields = ("sale_date", "discount", "notes")
        widgets = {
            "sale_date": forms.DateInput(attrs={"type": "date"}),
            "notes": forms.Textarea(attrs={"rows": 2, "placeholder": "Delivery or warranty notes (optional)"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        if self.instance and self.instance.customer_id:
            self.fields["customer_phone"].initial = self.instance.customer.phone
            self.fields["customer_name"].initial = self.instance.customer.name
        self.fields["customer_phone"].help_text = "Existing customers will be suggested automatically. A new number creates a new customer."
        self.fields["payment_status_choice"].widget.attrs["class"] = "payment-status-radios"

    def clean_customer_phone(self):
        phone = "".join(self.cleaned_data["customer_phone"].split())
        if len(phone) < 6:
            raise forms.ValidationError("Enter a valid customer phone number.")
        return phone

    def clean_payment_status_choice(self):
        return self.cleaned_data.get("payment_status_choice") or "unpaid"

    def clean_payment_method(self):
        return self.cleaned_data.get("payment_method") or "cash"


class SaleItemForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = SaleItem
        fields = ("cylinder", "quantity", "unit_price")
        widgets = {
            "quantity": forms.NumberInput(attrs={"min": 1}),
            "unit_price": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        self.fields["cylinder"].queryset = GasCylinder.objects.filter(is_active=True).order_by("name", "size")
        self.fields["cylinder"].label_from_instance = lambda obj: f"{obj.name} — {obj.size} ({obj.stock_quantity} available)"

SaleItemFormSet = inlineformset_factory(
    Sale,
    SaleItem,
    form=SaleItemForm,
    fields=("cylinder", "quantity", "unit_price"),
    extra=0,
    min_num=1,
    validate_min=True,
    can_delete=True,
)


class StockMovementForm(BootstrapFormMixin, forms.Form):
    cylinder = forms.ModelChoiceField(queryset=GasCylinder.objects.filter(is_active=True).order_by("name", "size"), label="Product")
    quantity = forms.IntegerField(min_value=1)
    notes = forms.CharField(required=False, max_length=255, widget=forms.Textarea(attrs={"rows": 2}))

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()

class PaymentForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Payment
        fields = ("amount", "payment_date", "method", "reference", "notes")
        widgets = {"payment_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, sale=None, **kwargs):
        self.sale = sale
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
        if sale:
            self.fields["amount"].widget.attrs["max"] = str(sale.balance)
            self.fields["amount"].help_text = f"Outstanding balance: {sale.balance:.2f}"

    def clean_amount(self):
        amount = self.cleaned_data["amount"]
        if self.sale and amount > self.sale.balance:
            raise forms.ValidationError("Payment cannot be greater than the outstanding balance.")
        return amount


class ExpenseForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = Expense
        fields = ("expense_date", "category", "description", "amount")
        widgets = {"expense_date": forms.DateInput(attrs={"type": "date"})}

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()


class CompanySettingForm(BootstrapFormMixin, forms.ModelForm):
    class Meta:
        model = CompanySetting
        fields = ("name", "phone", "email", "address", "currency", "invoice_footer", "auto_send_whatsapp")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._apply_bootstrap()
