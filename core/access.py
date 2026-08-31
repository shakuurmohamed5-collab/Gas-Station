from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied

from .models import EmployeeProfile


def employee_required(view_func):
    @wraps(view_func)
    def authorized_view(request, *args, **kwargs):
        if not request.user.is_superuser and not EmployeeProfile.objects.filter(user=request.user).exists():
            raise PermissionDenied("This account has not been authorized by an administrator.")
        return view_func(request, *args, **kwargs)

    return login_required(authorized_view)


def admin_required(view_func):
    @wraps(view_func)
    def administrator_view(request, *args, **kwargs):
        if not request.user.is_superuser:
            raise PermissionDenied("Administrator access is required.")
        return view_func(request, *args, **kwargs)

    return login_required(administrator_view)
