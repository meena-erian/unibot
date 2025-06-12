from django.contrib import admin
from .models import Bot
from django import forms
from django_ace import AceWidget

# Register your models here.

class BotAdminForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = '__all__'
        widgets = {
            'code': AceWidget(mode='python', theme='twilight', width='600px', height='300px'),
        }

class BotAdmin(admin.ModelAdmin):
    form = BotAdminForm

    def get_changeform_initial_data(self, request):
        return {'code': Bot.get_default_code()}

admin.site.register(Bot, BotAdmin)
