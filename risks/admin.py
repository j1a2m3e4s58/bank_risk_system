from django.contrib import admin
from django.utils.html import format_html
from .models import RiskAssessment, AISettings


# ========= AI SETTINGS ADMIN =========
@admin.register(AISettings)
class AISettingsAdmin(admin.ModelAdmin):
    list_display = ("enable_ai", "updated_at")


# ========= RISK ASSESSMENT ADMIN =========
@admin.register(RiskAssessment)
class RiskAssessmentAdmin(admin.ModelAdmin):
    list_display = (
        'reference_id',
        'area_name',
        'short_description',
        'risk_owner',
        'inherent_rating_colored',
        'residual_rating_colored',
        'updated_at',
        'updated_by',
        'risk_coordinator_name',

    )

    list_filter = ('area_name', 'inherent_rating', 'residual_rating', 'risk_owner')
    search_fields = ('reference_id', 'description', 'area_name', 'risk_owner')
    readonly_fields = ('inherent_rating', 'residual_rating', 'created_at', 'updated_at', 'updated_by')

    fieldsets = (
        ('Risk Identification', {
    'fields': (
        ('reference_id', 'area_name'),
        'risk_owner',
        'risk_coordinator_name',
    ),

            'description': "Basic identification details.",
        }),
        ('Risk Details', {
            'fields': ('description', 'caused_by', 'consequences'),
        }),
        ('Inherent Risk (Before Controls)', {
            'fields': (('inherent_probability', 'inherent_impact', 'inherent_rating'),),
            'description': "Select Probability and Impact.",
        }),
        ('Risk Mitigation', {
            'fields': ('controls', 'control_owner'),
        }),
        ('Residual Risk (After Controls)', {
            'fields': (('residual_probability', 'residual_impact', 'residual_rating'),),
            'description': "Select Probability and Impact.",
        }),
        ('Audit Trail', {
            'fields': ('updated_by', 'updated_at', 'created_at'),
            'classes': ('collapse',),
            'description': "System tracking information.",
        }),
    )

    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)

    # ====== COLORED BADGES ======
    def color_badge(self, rating):
        colors = {
            'Critical': '#d32f2f',
            'Severe': '#f57c00',
            'Moderate': '#fbc02d',
            'Sustainable': '#388e3c',
        }
        color = colors.get(rating, '#777')
        return format_html(
            '<div style="background-color:{}; color:white; padding:5px 10px; border-radius:4px; '
            'font-weight:bold; text-align:center; width:100px;">{}</div>',
            color, rating
        )

    def inherent_rating_colored(self, obj):
        return self.color_badge(obj.inherent_rating)
    inherent_rating_colored.short_description = "Inherent"
    inherent_rating_colored.admin_order_field = 'inherent_rating'

    def residual_rating_colored(self, obj):
        return self.color_badge(obj.residual_rating)
    residual_rating_colored.short_description = "Residual"
    residual_rating_colored.admin_order_field = 'residual_rating'

    def short_description(self, obj):
        return obj.description[:40] + "..." if len(obj.description) > 40 else obj.description
    short_description.short_description = "Description"

    class Media:
        css = {'all': ('risks/admin_overrides.css',)}


# ========= ADMIN SITE BRANDING =========
admin.site.site_header = "Bank Risk Management System"
admin.site.site_title = "Risk Admin Portal"
admin.site.index_title = "System Dashboard"
