from django.urls import path
from .views import index,Login,create_single_badge,bulk_upload_preview,bulk_upload_save,validate_email
from .views import get_columns,bulk_update_session,bulk_task_status


urlpatterns=[
    path('',index,name="home"),
    path('login/',Login,name="login"),
    path("badge/create/", create_single_badge, name="create_single_badge"),
    path("bulk-upload-preview/", bulk_upload_preview, name="bulk_upload_preview"),
    path("bulk-upload-save/", bulk_upload_save, name="bulk_upload_save"),
    path("validate-email/", validate_email, name="validate_email"),
    path("get-columns/",get_columns,name="get_columns"),
     path('bulk-update-session/', bulk_update_session, name='bulk_update_session'),
     path("bulk-task-status/<str:task_id>/", bulk_task_status, name="bulk_task_status"),
]