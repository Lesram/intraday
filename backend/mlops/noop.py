"""
No-op Model Manager for Light Mode
Provides stub implementations when heavy ML modules are disabled
"""

class NoopModelManager:
    """No-op model manager that does nothing but satisfies interfaces"""
    
    def __init__(self):
        pass
        
    def predict(self, *args, **kwargs):
        """Return dummy prediction"""
        return {"prediction": 0.5, "confidence": 0.8}
        
    def train(self, *args, **kwargs):
        """No-op training"""
        return {"status": "complete", "accuracy": 0.85}
        
    def save(self, *args, **kwargs):
        """No-op save"""
        return True
        
    def load(self, *args, **kwargs):
        """No-op load"""
        return True
        
    def get_metrics(self):
        """Return dummy metrics"""
        return {"accuracy": 0.85, "precision": 0.82, "recall": 0.78}

def get_model_manager():
    """Factory function for getting model manager"""
    return NoopModelManager()
