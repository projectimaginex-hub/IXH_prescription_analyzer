from django.db.models.signals import post_save
from django.dispatch import receiver
# Temporarily comment out all problematic imports:
from .models import Prescription # <-- COMMENT OUT
from .analysis_pipeline import run_llm_analysis # <-- COMMENT OUT

# We will import these *inside* the function instead
from django.apps import apps # New import

@receiver(post_save, sender='home.Prescription') # Use string reference for sender
def trigger_analysis(sender, instance, created, **kwargs):
    # Perform imports inside the function to avoid circular dependency on load
    from .models import Prescription # <-- IMPORT MODEL HERE
    from .analysis_pipeline import run_llm_analysis # <-- IMPORT FUNCTION HERE
    
    # We must ensure we only run on a final save, not the initial creation
    # that happens before the Prescription object is fully set up.
    if created and instance.transcribed_text:
        try:
            # Check if this instance already has analysis data (optional optimization)
            if not getattr(instance, 'llm_analyzed', False):
                 run_llm_analysis(instance)
        except Exception as e:
            print(f"[LLM ERROR] Failed analysis for Prescription {instance.id}: {e}")