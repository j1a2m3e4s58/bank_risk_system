from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required, permission_required
from django.http import HttpResponseForbidden
from django.utils import timezone
from django.http import HttpResponse
import csv
import re
from .models import RiskAssessment, ReportConfiguration

# ========= ZERO_OCCURRENCE_HELPER_START =========
def is_zero_occurrence(value) -> bool:
    if value is None:
        return True

    v = str(value).strip().lower()

    ZERO_WORDS = [
        "0", "0.0", "zero", "nil", "none", "no", "n/a", "",
        "always updated", "timelines met", "on time", "no issues", "ok"
    ]

    return v in ZERO_WORDS
# ========= ZERO_OCCURRENCE_HELPER_END =========


# ========= UNIQUE_ID_GLOBAL_START =========
def make_unique_reference_id(base_ref):
    ref = base_ref
    bump = 1
    while RiskAssessment.objects.filter(reference_id=ref).exists():
        ref = f"{base_ref}-{bump}"
        bump += 1
    return ref
# ========= UNIQUE_ID_GLOBAL_END =========



# ========= RISK_OWNER_SUGGEST_START =========
def suggest_risk_owner(area_name):
    a = (area_name or "").strip().lower()

    if "microfinance" in a:
        return "Head of Microfinance"
    if "credit" in a:
        return "Head of Credit"
    if "finance" in a:
        return "Head of Finance"
    if a == "it" or " ict" in f" {a} " or " it " in f" {a} " or "information technology" in a:
        return "Head of IT"
    if "operations" in a or "teller" in a or "customer service" in a:
        return "Head of Operations"
    if "compliance" in a:
        return "Compliance Officer"
    if "audit" in a:
        return "Internal Auditor"
    if "treasury" in a:
        return "Treasury Manager"
    if "hr" in a or "human resource" in a:
        return "Head of HR"
    if "legal" in a:
        return "Legal Officer"

    return "Department Head"
# ========= RISK_OWNER_SUGGEST_END =========


# ========= SMART_SCORING_START =========
def score_probability_from_occurrence(occurrence_value):
    """
    occurrence_value can be '', '0', ' 200', '10', etc.
    Returns one of: Very Low, Low, Medium, High, Very High
    """
    try:
        n = int(str(occurrence_value).strip())
    except Exception:
        n = 0

    if n <= 0:
        return "Very Low"
    if n <= 2:
        return "Low"
    if n <= 5:
        return "Medium"
    if n <= 20:
        return "High"
    return "Very High"


def score_impact_from_text(related_risk_text):
    """
    Keyword-based impact scoring from Related Risk / Description text.
    Returns: Very Low/Low/Medium/High/Very High (we mostly use Medium+)
    """
    t = (related_risk_text or "").lower()

    very_high_keys = [
        "robbery", "fraud", "theft", "pilfer", "unauthorized", "suppression",
        "money laundering", "aml", "cft", "penalty", "regulatory", "impersonation",
        "asset loss", "loss of funds", "e-money", "identity theft"
    ]
    high_keys = [
        "reputational", "customer complaint", "complaints", "data privacy", "information leakage",
        "service", "downtime"
    ]

    for k in very_high_keys:
        if k in t:
            return "Very High"

    for k in high_keys:
        if k in t:
            return "High"

    return "Medium"


def default_controls_for_area(area_name):
    a = (area_name or "").lower()
    if "teller" in a or "customer service" in a or "operations" in a:
        return "Maker-checker, daily call-over, cash limits, CCTV monitoring, ID verification"
    if "credit" in a or "microfinance" in a:
        return "Approval workflow controls, KYC verification, monitoring visits, collections follow-up"
    if "it" in a or "ict" in a:
        return "Access control, system monitoring, change management, alerting, backups"
    if "compliance" in a or "aml" in a:
        return "Transaction monitoring, reporting controls, periodic compliance review"
    return "Standard Controls"
# ========= SMART_SCORING_END =========


# --- LOGIN REDIRECT ---
def redirect_to_login(request):
    return redirect('/accounts/login/')


# --- DASHBOARD ---
@login_required
def dashboard(request):
    risks = RiskAssessment.objects.all().order_by('reference_id')


    selected_area = request.GET.get("area", "").strip()
    available_areas = list(
        RiskAssessment.objects.exclude(area_name__isnull=True)
        .exclude(area_name__exact="")
        .values_list("area_name", flat=True)
        .distinct()
    )
    if selected_area:
        risks = risks.filter(area_name=selected_area)

    filter_type = request.GET.get("filter", "all").strip()
    if filter_type == "draft":
        risks = risks.filter(description__startswith="[DRAFT]")
    elif filter_type == "approved":
        risks = risks.exclude(description__startswith="[DRAFT]")

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
        'available_areas': available_areas,
        'selected_area': selected_area,
        'filter_type': filter_type,
    }
    return render(request, 'risks/dashboard.html', context)


# --- EXPORT CSV ---
@login_required
def export_risks_csv(request):
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="risk_register.csv"'
    writer = csv.writer(response)
    writer.writerow(['ID', 'Area', 'Description', 'Root Cause', 'Consequences', 'Risk Owner', 'Inherent Probability', 'Inherent Impact', 'Inherent Rating', 'Residual Probability', 'Residual Impact', 'Residual Rating'])

    for risk in RiskAssessment.objects.all().order_by('-created_at'):
        writer.writerow([
            risk.reference_id,
            risk.area_name,
            risk.description,
            risk.caused_by,
            risk.consequences,
            risk.risk_owner,
            risk.inherent_probability,
            risk.inherent_impact,
            risk.inherent_rating,
            risk.residual_probability,
            risk.residual_impact,
            risk.residual_rating
        ])
    return response


# --- OFFICIAL REPORT ---
@login_required
def official_report(request):
    if not request.user.is_superuser and not request.user.has_perm('risks.view_reportconfiguration'):
        return HttpResponseForbidden("<h1>Access Denied</h1><p>You do not have permission to view this official document.</p>")

    config, created = ReportConfiguration.objects.get_or_create(id=1)

    if request.method == "POST" and request.user.is_superuser:
        new_summary = request.POST.get('executive_summary')
        if new_summary:
            config.executive_summary = new_summary
            config.save()

    risks = RiskAssessment.objects.all().order_by('area_name', 'reference_id')


    # group by area_name for headings
    grouped = {}
    for r in risks:
        key = r.area_name or "UNSPECIFIED"
        grouped.setdefault(key, []).append(r)

    context = {
        'risks': risks,
        'grouped_risks': grouped,
        'config': config,
        'generated_at': timezone.now(),
        'generated_by': request.user.username,
        'is_admin': request.user.is_superuser
    }
    return render(request, 'admin/official_report.html', context)


# ========= AI EXTRACT (Preview) =========
@login_required
def ai_extract_risks(request):
    def _split_row(line):
        if "\t" in line:
            return [p.strip() for p in line.split("\t") if p.strip()]
        return [p.strip() for p in re.split(r"\s{2,}", line.strip()) if p.strip()]

    def _parse_pasted_text(raw_text):
        lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

        area_name = ""
        reporting_period = ""

        for ln in lines[:5]:
            if "Reporting Period:" in ln:
                left, right = ln.split("Reporting Period:", 1)
                area_name = left.strip()
                reporting_period = right.strip()
                break
        if not area_name and lines:
            area_name = lines[0].strip()

        header_idx = -1
        for i, ln in enumerate(lines):
            if "Key Risk Indicator" in ln and ("No Occurrence" in ln or "Number of Occurrance" in ln or "No Occurrence" in ln):
                header_idx = i
                break
        if header_idx == -1:
            for i, ln in enumerate(lines):
                if "Key Risk Indicator" in ln and "KRI Description" in ln:
                    header_idx = i
                    break

        data_lines = lines[header_idx + 1:] if header_idx != -1 and header_idx + 1 < len(lines) else lines[1:]

        extracted = []
        counter = 1
       
        for ln in data_lines:
            if "Key Risk Indicator" in ln:
                continue

            parts = _split_row(ln)
            if len(parts) < 4:
                continue

            kri = parts[0] if len(parts) >= 1 else ""
            kri_desc = parts[1] if len(parts) >= 2 else ""
            related_risk = parts[2] if len(parts) >= 3 else ""
            process = parts[3] if len(parts) >= 4 else ""
            occurrence = parts[4] if len(parts) >= 5 else ""

            base_ref = f"RISK-{area_name[:12].upper().replace(' ', '-')}-{counter:03d}"
            base_ref = re.sub(r"[^A-Z0-9\-]", "", base_ref)
            reference_id = make_unique_reference_id(base_ref)

            prob = score_probability_from_occurrence(occurrence)
            impact = score_impact_from_text(related_risk + " " + process)

            extracted.append({
                "reference_id": reference_id,
                "area_name": area_name,
                "reporting_period": reporting_period,
                "risk_owner": suggest_risk_owner(area_name),
                "risk_description": (related_risk.strip() or kri.strip() or "TBD"),
                "root_cause": kri_desc.strip(),
                "trigger": f"When {kri.strip().lower()} happens or is detected." if kri.strip() else "",
                "consequences": related_risk.strip(),
                "inherent_probability": prob,
                "inherent_impact": impact,
                "inherent_rating": "-",
                "control_descriptions": default_controls_for_area(area_name),
                "control_owner": suggest_risk_owner(area_name),
                "residual_probability": prob,
                "residual_impact": impact,
                "residual_rating": "-",
                "source_kri": kri,
                "source_kri_description": kri_desc,
                "source_related_risk": related_risk,
                "source_process": process,
                "source_occurrence": occurrence,
            })
            counter += 1

        return area_name, reporting_period, extracted

    context = {"raw_text": "", "area_name": "", "reporting_period": "", "results": [], "error": ""}

    if request.method == "POST":
        raw_text = request.POST.get("raw_text", "")
        context["raw_text"] = raw_text

        if not raw_text.strip():
            context["error"] = "Please paste your KRI table text first."
        else:
            area_name, reporting_period, results = _parse_pasted_text(raw_text)
            context["area_name"] = area_name
            context["reporting_period"] = reporting_period
            context["results"] = results
            if not results:
                context["error"] = "I could not detect any table rows. Make sure you pasted the KRI table with rows."

    return render(request, "risks/ai_extract.html", context)


# ========= SAVE DRAFTS =========
@login_required
def ai_extract_save_drafts(request):
    if request.method != "POST":
        return redirect("ai-extract")

    raw_text = request.POST.get("raw_text", "").strip()
    if not raw_text:
        return redirect("ai-extract")

    def _split_row(line):
        if "\t" in line:
            return [p.strip() for p in line.split("\t") if p.strip()]
        return [p.strip() for p in re.split(r"\s{2,}", line.strip()) if p.strip()]

    def _make_unique_reference_id(base_ref):
        ref = base_ref
        bump = 1
        while RiskAssessment.objects.filter(reference_id=ref).exists():
            ref = f"{base_ref}-{bump}"
            bump += 1
        return ref

    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]

    area_name = ""
    for ln in lines[:5]:
        if "Reporting Period:" in ln:
            left, _right = ln.split("Reporting Period:", 1)
            area_name = left.strip()
            break
    if not area_name and lines:
        area_name = lines[0].strip()

    header_idx = -1
    for i, ln in enumerate(lines):
        if "Key Risk Indicator" in ln and "KRI Description" in ln:
            header_idx = i
            break

    data_lines = lines[header_idx + 1:] if header_idx != -1 and header_idx + 1 < len(lines) else lines[1:]

    counter = 1
    for ln in data_lines:
        parts = _split_row(ln)
        if len(parts) < 4:
            continue

        kri = parts[0] if len(parts) >= 1 else ""
        kri_desc = parts[1] if len(parts) >= 2 else ""
        related_risk = parts[2] if len(parts) >= 3 else ""
        occurrence = parts[4] if len(parts) >= 5 else ""
        kri = parts[0] if len(parts) >= 1 else ""
        kri_desc = parts[1] if len(parts) >= 2 else ""
        related_risk = parts[2] if len(parts) >= 3 else ""
        process = parts[3] if len(parts) >= 4 else ""
        occ = parts[4] if len(parts) >= 5 else ""

        # ===== SKIP ZERO OCCURRENCE RISKS =====
        if is_zero_occurrence(occ):
            continue
        # =====================================


        base_ref = f"RISK-{area_name[:12].upper().replace(' ', '-')}-{counter:03d}"
        base_ref = re.sub(r"[^A-Z0-9\-]", "", base_ref)
        reference_id = _make_unique_reference_id(base_ref)

        prob = score_probability_from_occurrence(occurrence)
        impact = score_impact_from_text(related_risk)

        description_text = "[DRAFT] " + (related_risk.strip() or kri.strip() or "TBD")

        try:
            RiskAssessment.objects.create(
                reference_id=make_unique_reference_id(f"RISK-{area_name[:12].upper().replace(' ', '-')}-{counter:03d}"),
                area_name=area_name,
                description=description_text,
                caused_by=kri_desc.strip(),
                consequences=related_risk.strip(),
                risk_owner=suggest_risk_owner(area_name),
                inherent_probability=prob,
                inherent_impact=impact,
                residual_probability=prob,
                residual_impact=impact,
                controls="Maker-checker, recovery tracking, escalation matrix, legal oversight",
                control_owner=suggest_risk_owner(area_name),
                updated_by=request.user
            )
        except Exception:
            pass

        counter += 1

    return redirect("dashboard")


# ========= SAVE & APPROVE =========
@login_required
def ai_extract_save_and_approve(request):
    
    if request.method != "POST":
        return redirect("ai-extract")

    raw_text = request.POST.get("raw_text", "")
    if not raw_text or not raw_text.strip():
        return redirect("ai-extract")

    import re

    def split_row(line):
        if "\t" in line:
            return [p.strip() for p in line.split("\t") if p.strip()]
        return [p.strip() for p in re.split(r"\s{2,}", line.strip()) if p.strip()]

    def make_unique_reference_id(base_ref):
        ref = base_ref
        bump = 1
        while RiskAssessment.objects.filter(reference_id=ref).exists():
            ref = f"{base_ref}-{bump}"
            bump += 1
        return ref

    def likelihood_from_occurrence(value):
        v = str(value).strip().lower()

        # percentage like 10%
        if v.endswith("%"):
            try:
                pct = float(v.replace("%", "").strip())
            except ValueError:
                pct = 0.0
            if pct <= 0:
                return "Very Low"
            if pct < 5:
                return "Medium"
            if pct < 10:
                return "High"
            return "Very High"

        # frequency phrases
        if any(x in v for x in ["daily", "per day", "every day"]):
            return "Very High"
        if any(x in v for x in ["weekly", "per week", "frequently", "often"]):
            return "High"
        if any(x in v for x in ["monthly", "per month"]):
            return "Medium"
        if any(x in v for x in ["quarterly", "per quarter"]):
            return "Low"
        if any(x in v for x in ["annually", "annual", "per year"]):
            return "Low"

        # numeric
        try:
            n = int(v)
        except ValueError:
            # blank/unknown text -> Medium is safer than Low
            return "Medium"

        if n <= 0:
            return "Very Low"
        if n == 1:
            return "Low"
        if 2 <= n <= 3:
            return "Medium"
        if 4 <= n <= 9:
            return "High"
        return "Very High"

    def impact_from_text(text):
        t = (text or "").lower()

        very_high = [
            "money laundering", "aml", "cft", "sanction", "regulatory", "penalty",
            "fraud", "theft", "misappropriation", "terrorist financing",
            "data breach", "privacy breach", "identity theft", "loss of funds"
        ]
        high = [
            "legal", "contract", "reputational", "litigation", "complaint to the regulator",
            "regulatory scrutiny", "enforcement"
        ]
        medium = [
            "operational", "process", "delay", "reporting", "documentation", "control breakdown",
            "governance", "recommendation", "overdue corrective"
        ]

        if any(k in t for k in very_high):
            return "Very High"
        if any(k in t for k in high):
            return "High"
        if any(k in t for k in medium):
            return "Medium"
        if any(k in t for k in ["vault", "insurance", "cash exposure", "cash vault"]):
            return "High"

        return "Medium"

    def reduce_level(level):
        order = ["Very Low", "Low", "Medium", "High", "Very High"]
        if level not in order:
            level = "Medium"
        return order[max(order.index(level) - 1, 0)]

    # ---------- PARSE LINES ----------
    lines = [ln.strip() for ln in raw_text.splitlines() if ln.strip()]
    if not lines:
        return redirect("ai-extract")

    # Parse area name safely from first line
    first = lines[0]
    if "Reporting Period:" in first:
        area_name = first.split("Reporting Period:", 1)[0].strip()
    else:
        area_name = first.strip()

    # Find header safely (no StopIteration)
    header_idx = -1
    for i, ln in enumerate(lines):
        if "Key Risk Indicator" in ln:
            header_idx = i
            break

    data_lines = lines[header_idx + 1:] if header_idx != -1 else lines[1:]

    OWNER_MAP = {
        "COMPLIANCE": "Compliance Manager",
        "AML": "Compliance Manager",
        "AUDIT": "Internal Auditor",
        "CREDIT": "Head of Credit",
        "LOAN RECOVERY": "Head of Credit",
        "SUSU": "Head of Operations",
        "OPERATIONAL": "Head of Operations",
        "IT": "Head of IT",
        "FINANCE": "Head of Finance",
        "TREASURY": "Head of Treasury",
    }

    # ========= COORDINATOR_MAP_START =========
    COORDINATOR_MAP = {
        # Compliance / AML
        "aml": "Compliance Officer",
        "cft": "Compliance Officer",
        "money laundering": "Compliance Officer",
        "sanction": "Compliance Officer",
        "regulatory": "Compliance Officer",
        "fic": "Compliance Officer",
        "bog": "Compliance Officer",

        # Fraud / theft
        "fraud": "Fraud & Investigations Officer",
        "theft": "Fraud & Investigations Officer",
        "misappropriation": "Fraud & Investigations Officer",
        "robbery": "Security Coordinator",

        # IT / systems
        "system": "IT Support Lead",
        "downtime": "IT Support Lead",
        "alert": "IT Support Lead",
        "verification system": "IT Support Lead",

        # Treasury / liquidity
        "liquidity": "Treasury Coordinator",
        "reserve": "Treasury Coordinator",
        "clearing": "Treasury Coordinator",
        "settlement": "Treasury Coordinator",

        # Customer / service
        "complaint": "Customer Service Coordinator",
        "reputational": "Customer Service Coordinator",

        # HR / people
        "staff": "HR Coordinator",
        "training": "HR Coordinator",
        "competency": "HR Coordinator",

        "__default__": "Risk & Compliance Coordinator",
    }
    # ========= COORDINATOR_MAP_END =========

    counter = 1

    for ln in data_lines:
        # ===== SKIP TABLE HEADER ROW =====
        if "kri description" in ln.lower() and "related risk" in ln.lower():
            continue
        # ================================

        parts = split_row(ln)
        if len(parts) < 3:
            continue

        kri = parts[0] if len(parts) >= 1 else ""
        kri_desc = parts[1] if len(parts) >= 2 else ""
        related_risk = parts[2] if len(parts) >= 3 else ""
        process = parts[3] if len(parts) >= 4 else ""
        occ = parts[4] if len(parts) >= 5 else ""

        # ========= OWNER_SELECT_START =========
        owner = "Department Head"
        for k, v in OWNER_MAP.items():
            if k in area_name.upper():
                owner = v
                break
        # ========= OWNER_SELECT_END =========

        # ========= COORDINATOR_SELECT_START =========
        combined_text = f"{kri} {kri_desc} {related_risk} {process}".lower()

        coordinator = COORDINATOR_MAP.get("__default__", "Risk Coordinator")
        for key, coord_name in COORDINATOR_MAP.items():
            if key != "__default__" and key in combined_text:
                coordinator = coord_name
                break
        # ========= COORDINATOR_SELECT_END =========

        # (then continue with your skip-zero check, scoring, and create())

        # ===== SKIP ZERO OCCURRENCE RISKS =====
        if is_zero_occurrence(occ):
            continue
        # =====================================


        inherent_prob = likelihood_from_occurrence(occ)
        inherent_impact = impact_from_text(" ".join([related_risk, kri, kri_desc, process]))

        residual_prob = reduce_level(inherent_prob)
        residual_impact = reduce_level(inherent_impact)

        base_ref = f"RISK-{area_name[:12].upper().replace(' ', '-')}-{counter:03d}"
        base_ref = re.sub(r"[^A-Z0-9\-]", "", base_ref)
        reference_id = make_unique_reference_id(base_ref)

        # Safe create: never crash whole request
        try:
            RiskAssessment.objects.create(
                reference_id=reference_id,
                area_name=area_name,
                description=related_risk or kri or "TBD",
                caused_by=kri_desc,
                consequences=related_risk,
                risk_owner=owner,
                risk_coordinator_name=coordinator,   # ✅ HERE
                inherent_probability=inherent_prob,
                inherent_impact=inherent_impact,
                residual_probability=residual_prob,
                residual_impact=residual_impact,
                controls="Standard Controls",
                control_owner=owner,
                updated_by=request.user
            )
        except Exception:
            pass

        counter += 1

    return redirect("dashboard")




@login_required
def edit_draft_risk(request, risk_id):
    risk = get_object_or_404(RiskAssessment, id=risk_id)

    if request.method == "POST":
        risk.area_name = request.POST.get("area_name", risk.area_name)
        risk.description = request.POST.get("description", risk.description)
        risk.caused_by = request.POST.get("caused_by", risk.caused_by)
        risk.consequences = request.POST.get("consequences", risk.consequences)
        risk.risk_owner = request.POST.get("risk_owner", risk.risk_owner)
        risk.controls = request.POST.get("controls", risk.controls)
        risk.control_owner = request.POST.get("control_owner", risk.control_owner)

        if request.POST.get("inherent_probability"):
            risk.inherent_probability = request.POST.get("inherent_probability")
        if request.POST.get("inherent_impact"):
            risk.inherent_impact = request.POST.get("inherent_impact")
        if request.POST.get("residual_probability"):
            risk.residual_probability = request.POST.get("residual_probability")
        if request.POST.get("residual_impact"):
            risk.residual_impact = request.POST.get("residual_impact")

        risk.updated_by = request.user
        risk.save()
        return redirect("dashboard")

    return render(request, "risks/edit_draft_risk.html", {
        "risk": risk,
        "prob_choices": RiskAssessment.PROBABILITY_CHOICES,
        "impact_choices": RiskAssessment.IMPACT_CHOICES,
    })


# ========= BULK APPROVE =========
@login_required
def bulk_approve_drafts(request):
    if not request.user.is_staff:
        return redirect("dashboard")

    drafts = RiskAssessment.objects.filter(description__startswith="[DRAFT]")
    for risk in drafts:
        risk.description = risk.description.replace("[DRAFT] ", "", 1)
        risk.save()

    return redirect("dashboard")
# ========= EXPORT_AND_CLEAR_START =========
@login_required
def export_risks_csv_and_clear(request):
    """
    Staff-only: exports CSV then clears all risks.
    """
    if not request.user.is_staff:
        return redirect("dashboard")

    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = 'attachment; filename="risk_register_and_cleared.csv"'
    writer = csv.writer(response)

    writer.writerow([
        'ID', 'Area', 'Description', 'Root Cause', 'Consequences', 'Risk Owner',
        'Inherent Probability', 'Inherent Impact', 'Inherent Rating',
        'Residual Probability', 'Residual Impact', 'Residual Rating'
    ])

    risks_qs = RiskAssessment.objects.all().order_by('-created_at')
    for risk in risks_qs:
        writer.writerow([
            risk.reference_id,
            risk.area_name,
            risk.description,
            risk.caused_by,
            risk.consequences,
            risk.risk_owner,
            risk.inherent_probability,
            risk.inherent_impact,
            risk.inherent_rating,
            risk.residual_probability,
            risk.residual_impact,
            risk.residual_rating
        ])

    RiskAssessment.objects.all().delete()
    return response
# ========= EXPORT_AND_CLEAR_END =========
# ========= CLEAR_RISKS_START =========
@login_required
def clear_all_risks(request):
    """
    Staff-only: clear all risks and redirect back to dashboard.
    Only works on POST (button form) so nobody clears by mistake.
    """
    if not request.user.is_staff:
        return redirect("dashboard")

    if request.method == "POST":
        RiskAssessment.objects.all().delete()
        return redirect("/?cleared=1")

    return redirect("dashboard")
# ========= CLEAR_RISKS_END =========


