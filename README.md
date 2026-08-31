# GasFlow — gas cylinder sales management

GasFlow is a responsive Django system for a cooking-gas company with three simple product types: cooking machines, new cylinders, and cylinder gas for regular returning customers. It replaces paper books with searchable customer records, controlled inventory, invoices, payments, expenses, reports, and WhatsApp invoice messages.

## Included

- Secure Django authentication with `/` as the login page
- Dashboard for daily sales, gas supplied, cash collected, customer balances, seven-day trends, and low stock
- Admin-managed employee profiles with secure sign-in authorization and activity accountability
- Persistent English/Soomaali language switch with business-focused Somali terminology across sales, stock, finance, employees, and invoices
- Customer search by name or phone number, with complete purchase and unpaid history
- Product catalog for cooking machines, new cylinders, and cylinder gas, each with one price, cost, stock count, and reorder alert
- One simple product selection on each invoice line
- Permanent stock-movement history for sales and stock received
- Phone-first customer lookup during a sale, with automatic customer creation for new numbers
- Multi-item cylinder sales that automatically deduct inventory
- Printable invoices, discounts, partial payments, and automatic payment status
- Automatic WhatsApp Cloud API messages after sales/payments (optional), with a pre-filled WhatsApp fallback button when credentials are not configured
- Expense tracking and date-range sales, cash, and operating-profit reports
- Desktop sidebar that becomes a touch-friendly bottom navigation on phones
- Two clear access levels: employees run sales and customer work; administrators control products, stock changes, finance, settings, and employees

## Local setup

Use Python 3.11 or newer.

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py setup_gasflow --username admin --password "Choose-A-Strong-Password" --company "Your Company Name" --currency "$"
python manage.py runserver
```

Open `http://127.0.0.1:8000/` and sign in with the administrator you created.

Administrators can open **Employees** in the sidebar to create staff sign-ins, update profiles or passwords, and deactivate access without deleting transaction history.

After the first setup, Windows users can start the system by double-clicking `start.bat`, or by running:

```powershell
.\start.bat
```

The direct virtual-environment command is `.\.venv\Scripts\python.exe manage.py runserver`. The leading `.\` means “from this folder”; do not use `..venv`.

## Production notes

Copy `.env.example` to `.env` and load those values through your hosting platform. Set `DJANGO_DEBUG=False`, use a long random `DJANGO_SECRET_KEY`, set the real host in `DJANGO_ALLOWED_HOSTS`, serve uploaded media from durable storage, and use PostgreSQL for a larger multi-user installation. Run `python manage.py collectstatic` during deployment.

For fully automatic WhatsApp messages, create a Meta WhatsApp Cloud API app and configure `WHATSAPP_ACCESS_TOKEN` and `WHATSAPP_PHONE_NUMBER_ID`. Without them, the green WhatsApp button still opens a properly formatted message addressed to the customer's saved phone number.
