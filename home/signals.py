from django.db.models.signals import post_save
from django.dispatch import receiver
from .models import Prescription
from .analysis_pipeline import run_llm_analysis

@receiver(post_save, sender=Prescription)
def trigger_analysis(sender, instance, created, **kwargs):
    if instance.transcribed_text and not instance.llm_analyzed:
        try:
            run_llm_analysis(instance)
        except Exception as e:
            print(f"[LLM ERROR] Failed analysis for Prescription {instance.id}: {e}")
