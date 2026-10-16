"""Publish only companion JS presentations, never Python definitions or data."""
from pathlib import Path
from django.conf import settings
from django.contrib.staticfiles.finders import BaseFinder
from django.core.files.storage import FileSystemStorage


class ToolPresentationFinder(BaseFinder):
    def __init__(self, *args, **kwargs):
        self.root = Path(getattr(settings, 'UNIBOT_DEFINITIONS_DIR', Path(settings.BASE_DIR) / 'data/definitions')) / 'tools'
        self.storage = FileSystemStorage(location=self.root)
        self.storage.prefix = 'unibot/definitions'
        super().__init__(*args, **kwargs)

    def find(self, path, all=False, **kwargs):
        prefix = 'unibot/definitions/'
        name = path.removeprefix(prefix)
        if path.startswith(prefix) and '/' not in name and name.endswith('.presentation.js'):
            candidate = self.root / name
            if candidate.is_file() and not candidate.is_symlink():
                return [str(candidate)] if all or kwargs.get('find_all') else str(candidate)
        return [] if all or kwargs.get('find_all') else None

    def list(self, ignore_patterns):
        for path in self.root.glob('*.presentation.js'):
            if path.is_file() and not path.is_symlink():
                yield path.name, self.storage
