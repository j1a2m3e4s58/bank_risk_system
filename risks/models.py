from django.db import models
from django.utils import timezone
from django.conf import settings


class RiskAssessment(models.Model):
    # --- DROPDOWN CHOICES ---
    PROBABILITY_CHOICES = [
        ('Very High', 'Very High'),
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
        ('Very Low', 'Very Low'),
    ]

    IMPACT_CHOICES = [
        ('Very High', 'Very High'),
        ('High', 'High'),
        ('Medium', 'Medium'),
        ('Low', 'Low'),
        ('Very Low', 'Very Low'),
    ]

    RATING_CHOICES = [
        ('Critical', 'Critical'),
        ('Severe', 'Severe'),
        ('Moderate', 'Moderate'),
        ('Sustainable', 'Sustainable'),
    ]

    # --- IDENTIFICATION ---
    reference_id = models.CharField(max_length=20, unique=True, help_text="Unique ID (e.g., RISK-001)")
    area_name = models.CharField(max_length=100, blank=True, null=True, help_text="Department or Area (e.g. IT, Finance)")
    description = models.TextField(verbose_name="Risk Description")

    # --- NEW SEPARATE FIELDS ---
    caused_by = models.TextField(verbose_name="Root Cause", blank=True, default="", help_text="What triggers this risk?")
    consequences = models.TextField(verbose_name="Consequences", blank=True, default="", help_text="What happens if this risk occurs?")

    risk_owner = models.CharField(max_length=100, help_text="Person responsible for this risk")

    # ========= RISK_COORDINATOR_FIELD_START =========
    risk_coordinator = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Coordinator for monitoring / reporting"
    )
    # ========= RISK_COORDINATOR_FIELD_END =========

    # ========= RISK_COORDINATOR_NAME_FIELD_START =========
    risk_coordinator_name = models.CharField(
        max_length=100,
        blank=True,
        default="",
        help_text="Coordinator responsible for follow-up / reporting"
    )
    # ========= RISK_COORDINATOR_NAME_FIELD_END =========



    # --- INHERENT RISK (Before Controls) ---
    inherent_probability = models.CharField(max_length=20, choices=PROBABILITY_CHOICES)
    inherent_impact = models.CharField(max_length=20, choices=IMPACT_CHOICES)
    inherent_rating = models.CharField(max_length=20, choices=RATING_CHOICES, blank=True, editable=False)

    # --- CONTROLS ---
    controls = models.TextField(verbose_name="Control Descriptions", blank=True)
    control_owner = models.CharField(max_length=100, blank=True)

    # --- RESIDUAL RISK (After Controls) ---
    residual_probability = models.CharField(max_length=20, choices=PROBABILITY_CHOICES)
    residual_impact = models.CharField(max_length=20, choices=IMPACT_CHOICES)
    residual_rating = models.CharField(max_length=20, choices=RATING_CHOICES, blank=True, editable=False)

    # --- AUDIT TRAIL ---
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='risks_updated'
    )

    def calculate_rating(self, prob, impact):
        """Standard 5x5 Matrix Logic"""
        # 1. Critical (Red)
        if (prob == 'Very High' and impact in ['Very High', 'High', 'Medium']) or \
           (prob == 'High' and impact in ['Very High', 'High']) or \
           (prob == 'Medium' and impact == 'Very High'):
            return 'Critical'

        # 2. Severe (Orange)
        if (prob == 'Very High' and impact == 'Low') or \
           (prob == 'High' and impact == 'Medium') or \
           (prob == 'Medium' and impact == 'High') or \
           (prob == 'Low' and impact == 'Very High'):
            return 'Severe'

        # 3. Moderate (Yellow)
        if (prob == 'Very High' and impact == 'Very Low') or \
           (prob == 'High' and impact == 'Low') or \
           (prob == 'Medium' and impact in ['Medium', 'Low']) or \
           (prob == 'Low' and impact in ['High', 'Medium']) or \
           (prob == 'Very Low' and impact in ['Very High', 'High']):
            return 'Moderate'

        # 4. Sustainable (Green)
        return 'Sustainable'

    def save(self, *args, **kwargs):
        self.inherent_rating = self.calculate_rating(self.inherent_probability, self.inherent_impact)
        self.residual_rating = self.calculate_rating(self.residual_probability, self.residual_impact)
        super().save(*args, **kwargs)

        # ========= AUTO_FILL_PROPERTIES_START =========
    @property
    def control_description(self):
        # official_report.html expects this name
        return self.controls or "Standard Controls"

    @property
    def risk_coordinator(self):
        # official_report.html expects this name
        return self.risk_coordinator_name or "-"
    # ========= AUTO_FILL_PROPERTIES_END =========


    def __str__(self):
        return f"{self.reference_id} - {self.description[:30]}"


# --- NEW REPORT CONFIGURATION MODEL ---
class ReportConfiguration(models.Model):
    """Stores the editable text for the Official Report"""
    executive_summary = models.TextField(default="This document contains the official record of identified operational and financial risks.")
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "Official Report Settings"

    class Meta:
        # This creates the specific permission we need: 'risks.view_reportconfiguration'
        verbose_name = "Report Settings"


# ========= AI_SETTINGS_START =========
class AISettings(models.Model):
    enable_ai = models.BooleanField(default=False)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return "AI Settings"
# ========= AI_SETTINGS_END =========
