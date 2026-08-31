from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.models import CompanySetting


class Command(BaseCommand):
    help = "Create or update the company profile and initial administrator."

    def add_arguments(self, parser):
        parser.add_argument("--username", default="admin")
        parser.add_argument("--password", required=True, help="Use a strong password; it is stored securely as a hash.")
        parser.add_argument("--email", default="")
        parser.add_argument("--company", default="GasFlow")
        parser.add_argument("--phone", default="")
        parser.add_argument("--address", default="")
        parser.add_argument("--currency", default="$")

    def handle(self, *args, **options):
        if len(options["password"]) < 8:
            raise CommandError("The administrator password must contain at least 8 characters.")

        company, _ = CompanySetting.objects.get_or_create(pk=1)
        company.name = options["company"]
        company.phone = options["phone"]
        company.address = options["address"]
        company.currency = options["currency"]
        company.save()

        User = get_user_model()
        user, created = User.objects.get_or_create(username=options["username"])
        user.email = options["email"]
        user.is_staff = True
        user.is_superuser = True
        user.is_active = True
        user.set_password(options["password"])
        user.save()
        action = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"Administrator '{user.username}' {action}; company profile saved."))
