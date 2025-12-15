from django.shortcuts import render, redirect
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.db.models import Count
from django.http import HttpResponse
import csv
from .models import RiskAssessment, ReportConfiguration

# --- LOGIN REDIRECT ---
def redirect_to_login(request):
    return redirect('/accounts/login/')

# --- DASHBOARD ---
@login_required
def dashboard(request):
    risks = RiskAssessment.objects.all().order_by('-created_at')
    
    # Matrix Helpers
    probabilities = ['Very High', 'High', 'Medium', 'Low', 'Very Low']
    impacts = ['Very Low', 'Low', 'Medium', 'High', 'Very High']

    def get_matrix_counts(risk_type):
        matrix_grid = {p: {i: 0 for i in impacts} for p in probabilities}
        for r in risks:
            if risk_type == 'inherent':
                p, i = r.inherent_probability, r.inherent_impact
            else:
                p, i = r.residual_probability, r.residual_impact
            
            if p in matrix_grid and i in matrix_grid[p]:
                matrix_grid[p][i] += 1
        return matrix_grid

    context = {
        'risks': risks,
        'total_risks': risks.count(),
        'critical_risks': risks.filter(residual_rating='Critical').count(),
        'user': request.user,
        'probabilities': probabilities,
        'impacts': impacts,
        'inherent_matrix': get_matrix_counts('inherent'),
        'residual_matrix': get_matrix_counts('residual'),
    }
    return render(request, 'risks/dashboard.html', context)

# --- EXPORT CSV ---
@login_required
def export_risks_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="risk_register.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Description', 'Inherent Rating', 'Residual Rating'])
    for risk in RiskAssessment.objects.all():
        writer.writerow([risk.reference_id, risk.description, risk.inherent_rating, risk.residual_rating])
    return response

# --- OFFICIAL REPORT (UPDATED) ---
@login_required
def official_report(request):
    # 1. PERMISSION CHECK
    # Admin (Superuser) allows access.
    # OR User must have specific permission "risks.view_reportconfiguration"
    if not request.user.is_superuser and not request.user.has_perm('risks.view_reportconfiguration'):
        return HttpResponseForbidden("<h1>Access Denied</h1><p>You do not have permission to view this official document.</p>")

    # 2. GET OR CREATE THE SETTINGS (Singleton)
    config, created = ReportConfiguration.objects.get_or_create(id=1)

    # 3. HANDLE EDITING (Admins Only)
    if request.method == "POST" and request.user.is_superuser:
        new_summary = request.POST.get('executive_summary')
        if new_summary:
            config.executive_summary = new_summary
            config.save()

    # 4. FETCH DATA
    risks = RiskAssessment.objects.all().order_by('-created_at')
    
    context = {
        'risks': risks,
        'config': config,  # Pass the settings to the template
        'generated_at': timezone.now(),
        'generated_by': request.user.username,
        'is_admin': request.user.is_superuser # Flag to show/hide edit box
    }
    return render(request, 'admin/official_report.html', context)