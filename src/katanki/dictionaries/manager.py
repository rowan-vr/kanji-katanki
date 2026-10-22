"""Load selected local sources through manifest-selected, reusable adapters."""

from hashlib import sha256
from pathlib import Path

from .adapters.kanjidic2_xml import KanjidicXml
from .adapters.kanjivg_svg import KanjiVgSvg
from .registry import bundled_path, bundled_sources, list_datasets, verify_bundle

ADAPTERS = {"kanjidic2_xml": KanjidicXml, "kanjivg_svg": KanjiVgSvg}


class DictionaryManager:
    def __init__(self, sources: dict[str, Path] | None = None):
        self.manifests = list_datasets()
        sources = bundled_sources() if sources is None else sources
        known = {manifest.id for manifest in self.manifests}
        if sources.keys() - known:
            raise ValueError("Unknown dataset selection.")
        self.providers = {}
        self.provenance: list[str] = []
        for manifest in self.manifests:
            if manifest.id not in sources:
                continue
            path = sources[manifest.id]
            is_bundled = manifest.bundled is not None and path.resolve() == bundled_path(
                manifest.bundled["path"]
            )
            if is_bundled:
                verify_bundle(manifest)
            compression = {".gz": "gzip", ".zip": "zip"}.get(path.suffix.lower(), "none")
            if compression not in manifest.compression:
                raise ValueError(f"{manifest.name} does not support {compression} input.")
            provider = ADAPTERS[manifest.format](path)
            for capability in manifest.capabilities:
                if capability in self.providers:
                    raise ValueError(f"Multiple selected providers for {capability}.")
                self.providers[capability] = provider
            version = (
                manifest.bundled["version"]
                if is_bundled
                else getattr(provider, "version", "local SVG files")
            )
            fingerprint = ""
            if hasattr(provider, "source_bytes"):
                fingerprint = f"; SHA-256 {sha256(provider.source_bytes).hexdigest()}"
            self.provenance.append(
                f"{manifest.name}: {version}{fingerprint}; {path}; source {manifest.source}; "
                f"{manifest.attribution}; {manifest.license_name}; {manifest.license_url}"
                + ("; bundled SHA-256 " + manifest.bundled["sha256"] if is_bundled else "")
            )

    def status(self) -> tuple[str, ...]:
        return tuple(sorted(self.providers))

    def lookup_kanji(self, character):
        provider = self.providers.get("kanji")
        return provider.lookup_kanji(character) if provider else None

    def lookup_strokes(self, character):
        provider = self.providers.get("strokes")
        return provider.lookup_strokes(character) if provider else None

    def source_details(self) -> tuple[str, ...]:
        lines = list(self.provenance)
        provider = self.providers.get("strokes")
        if provider is not None:
            lines.extend(
                f"KanjiVG {char}: SHA-256 {value}" for char, value in provider.hashes.items()
            )
        return tuple(lines)

    def close(self):
        for provider in {id(provider): provider for provider in self.providers.values()}.values():
            if hasattr(provider, "close"):
                provider.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()
