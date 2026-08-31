from .models import CompanySetting


def company_settings(request):
    return {"company": CompanySetting.objects.first() or CompanySetting()}
