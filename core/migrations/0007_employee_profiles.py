from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


def create_profiles_for_existing_employees(apps, schema_editor):
    User = apps.get_model(*settings.AUTH_USER_MODEL.split("."))
    EmployeeProfile = apps.get_model("core", "EmployeeProfile")
    for user in User.objects.filter(is_superuser=False, is_active=True):
        EmployeeProfile.objects.get_or_create(user_id=user.pk, defaults={"job_title": "Employee"})


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("core", "0006_three_simple_products"),
    ]

    operations = [
        migrations.CreateModel(
            name="EmployeeProfile",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("phone", models.CharField(blank=True, max_length=30)),
                ("job_title", models.CharField(blank=True, default="Employee", max_length=80)),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name="employee_profile", to=settings.AUTH_USER_MODEL)),
            ],
            options={"ordering": ["user__first_name", "user__username"]},
        ),
        migrations.RunPython(create_profiles_for_existing_employees, migrations.RunPython.noop),
    ]
