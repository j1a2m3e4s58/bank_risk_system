from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('export-csv/', views.export_risks_csv, name='export-csv'),

    path('export-csv-clear/', views.export_risks_csv_and_clear, name='export-csv-clear'),
    path('clear-risks/', views.clear_all_risks, name='clear-risks'),

    path('ai-extract/', views.ai_extract_risks, name='ai-extract'),
    path('ai-extract/save/', views.ai_extract_save_drafts, name='ai-extract-save'),
    path('ai-extract/save-approve/', views.ai_extract_save_and_approve, name='ai-extract-save-approve'),

    path('draft/<int:risk_id>/edit/', views.edit_draft_risk, name='edit-draft-risk'),
    path('drafts/approve-all/', views.bulk_approve_drafts, name='bulk-approve-drafts'),
]
