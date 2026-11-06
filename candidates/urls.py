from django.urls import path

from . import views

app_name = 'candidates'

urlpatterns = [
    path('', views.candidate_list, name='list'),
    path('ai-search/', views.ai_search, name='ai_search'),
    path('upload/', views.cv_upload, name='upload'),
    path('<int:pk>/', views.candidate_detail, name='detail'),
    path('<int:pk>/status-badge/', views.candidate_status_badge, name='status_badge'),
]
