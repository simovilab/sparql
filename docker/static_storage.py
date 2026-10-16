"""Compatibility fix for absolute static names in the pinned UI templates."""

from whitenoise.storage import CompressedManifestStaticFilesStorage


class NormalizedManifestStorage(CompressedManifestStaticFilesStorage):
    def url(self, name, *args, **kwargs):
        return super().url(name.lstrip("/"), *args, **kwargs)
