from django.db import models
import os
from django.conf import settings
from unicom.models.request_category import RequestCategory

# Create your models here.

class Bot(models.Model):
    id = models.BigAutoField(primary_key=True)
    name = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    code = models.TextField()
    request_category = models.OneToOneField(RequestCategory, on_delete=models.CASCADE, null=True, blank=True)

    def __str__(self):
        return self.name

    @staticmethod
    def get_default_code():
        template_path = os.path.join(settings.BASE_DIR, 'unibot', 'templates', 'unibot', 'default_bot.py')
        with open(template_path, 'r') as f:
            return f.read()

    def save(self, *args, **kwargs):
        creating = self.pk is None
        super().save(*args, **kwargs)
        if creating and not self.request_category:
            rc = RequestCategory.objects.create(
                name=self.category,
                sequence=1000 + self.id
            )
            self.request_category = rc
            super().save(update_fields=['request_category'])

    def delete(self, *args, **kwargs):
        rc = self.request_category
        super().delete(*args, **kwargs)
        if rc:
            rc.delete()
