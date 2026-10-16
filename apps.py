from django.apps import AppConfig


class UnibotConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'unibot'

    def ready(self):
        from unicom.interactions import register_interaction_resolver
        from unibot.interactions import resolve_interaction
        register_interaction_resolver('unibot', resolve_interaction)
