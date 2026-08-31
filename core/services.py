import json
import re
from urllib import error, parse, request

from django.conf import settings

from .models import WhatsAppLog


def normalized_phone(phone):
    return re.sub(r"[^0-9]", "", phone or "")


def sale_message(sale, company):
    currency = company.currency
    if sale.balance:
        payment_line = f"Paid: {currency}{sale.amount_paid:,.2f}\nBalance due: {currency}{sale.balance:,.2f}"
    else:
        payment_line = "Payment status: PAID IN FULL"
    return (
        f"Hello {sale.customer.name},\n\n"
        f"Thank you for your purchase from {company.name}.\n"
        f"Invoice: {sale.invoice_number}\n"
        f"Total: {currency}{sale.total:,.2f}\n"
        f"{payment_line}\n\n"
        f"For questions, contact {company.phone or 'our office'}."
    )


def whatsapp_link(phone, message):
    return f"https://wa.me/{normalized_phone(phone)}?text={parse.quote(message)}"


def send_sale_whatsapp(sale, user, company):
    message = sale_message(sale, company)
    log = WhatsAppLog.objects.create(customer=sale.customer, sale=sale, message=message, sent_by=user)
    if not settings.WHATSAPP_ACCESS_TOKEN or not settings.WHATSAPP_PHONE_NUMBER_ID:
        log.status = "link"
        log.save(update_fields=["status", "updated_at"])
        return {"sent": False, "link": whatsapp_link(sale.customer.phone, message), "log": log}

    endpoint = f"https://graph.facebook.com/{settings.WHATSAPP_API_VERSION}/{settings.WHATSAPP_PHONE_NUMBER_ID}/messages"
    payload = json.dumps(
        {
            "messaging_product": "whatsapp",
            "to": normalized_phone(sale.customer.phone),
            "type": "text",
            "text": {"preview_url": False, "body": message},
        }
    ).encode("utf-8")
    req = request.Request(
        endpoint,
        data=payload,
        headers={"Authorization": f"Bearer {settings.WHATSAPP_ACCESS_TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with request.urlopen(req, timeout=15) as response:
            body = response.read().decode("utf-8")
        log.status = "sent"
        log.provider_response = body
        log.save(update_fields=["status", "provider_response", "updated_at"])
        return {"sent": True, "link": "", "log": log}
    except (error.URLError, error.HTTPError, TimeoutError) as exc:
        log.status = "failed"
        log.provider_response = str(exc)
        log.save(update_fields=["status", "provider_response", "updated_at"])
        return {"sent": False, "link": whatsapp_link(sale.customer.phone, message), "log": log}
