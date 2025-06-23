from django.contrib import admin
from .models import Bot, Tool
from django import forms
from django_ace import AceWidget
from reversion.admin import VersionAdmin

# Register your models here.

class BotAdminForm(forms.ModelForm):
    class Meta:
        model = Bot
        fields = '__all__'
        widgets = {
            'code': AceWidget(mode='python', theme='twilight', width='600px', height='300px'),
        }

class BotAdmin(VersionAdmin):
    form = BotAdminForm

    def get_changeform_initial_data(self, request):
        return {'code': Bot.get_default_code()}

class ToolAdminForm(forms.ModelForm):
    class Meta:
        model = Tool
        fields = '__all__'
        widgets = {
            'code': AceWidget(mode='python', theme='twilight', width='600px', height='300px'),
        }

class ToolAdmin(VersionAdmin):
    form = ToolAdminForm

    def get_changeform_initial_data(self, request):
        return {'code': Tool.get_default_code()}

admin.site.register(Bot, BotAdmin)
admin.site.register(Tool, ToolAdmin)
