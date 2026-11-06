"""
URL configuration for hr_system project.
"""

from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.contrib.staticfiles.urls import staticfiles_urlpatterns
from django.urls import include, path

from . import views
from .forms import BootstrapAuthenticationForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', auth_views.LoginView.as_view(
        template_name='login.html', authentication_form=BootstrapAuthenticationForm,
    ), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    path('', views.dashboard, name='dashboard'),
    path('candidates/', include('candidates.urls')),
    path('vacancies/', include('vacancies.urls')),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    # runserver отдаёт static/ автоматически сам, gunicorn — нет
    urlpatterns += staticfiles_urlpatterns()
