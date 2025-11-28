from django.urls import path
from . import views

app_name = 'runner'

urlpatterns = [
    path('<uuid:access_code>/', views.lobby_view, name='lobby'),
    path('<uuid:access_code>/take/', views.exam_runner_view, name='take'),
]
