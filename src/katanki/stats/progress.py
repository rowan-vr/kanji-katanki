"""Collection-independent progress snapshots, with separate evidence by mode."""

from dataclasses import asdict, dataclass

STATES = ("missing", "new", "learning", "young", "mature", "relearning")
# Conservative aggregation: relearning is always visible, then least advanced.
PRIORITY = {
    state: index for index, state in enumerate(("relearning", "new", "learning", "young", "mature"))
}
MODES = ("recognition", "writing")


@dataclass(frozen=True)
class CardEvidence:
    character: str
    mode: str
    card_id: int
    note_id: int
    state: str
    interval: int
    reviews: int
    lapses: int
    suspended: bool = False
    buried: bool = False


@dataclass(frozen=True)
class ProgressSnapshot:
    cards: tuple[CardEvidence, ...]
    # Preserve the distinction between an absent note and a note without cards.
    notes: tuple[tuple[str, str, int], ...] = ()
    warnings: tuple[str, ...] = ()

    def state(self, character: str, mode: str) -> str:
        return min(
            (
                card.state
                for card in self.cards
                if card.character == character and card.mode == mode
            ),
            key=PRIORITY.__getitem__,
            default="missing",
        )

    def payload(self, targets: tuple[str, ...]) -> dict:
        targets = tuple(dict.fromkeys(targets))
        grouped = {}
        for card in self.cards:
            grouped.setdefault((card.character, card.mode), []).append(card)
        rows = []
        for character in targets:
            row = {"character": character}
            for mode in MODES:
                evidence = grouped.get((character, mode), ())
                row[mode] = min(
                    (c.state for c in evidence), key=PRIORITY.__getitem__, default="missing"
                )
            rows.append(row)
        return {
            "rows": rows,
            "counts": {
                mode: {state: sum(row[mode] == state for row in rows) for state in STATES}
                for mode in MODES
            },
            "warnings": self.warnings,
        }

    def details(self, character: str) -> dict:
        return {
            mode: {
                "state": self.state(character, mode),
                "note_ids": sorted(
                    {nid for char, kind, nid in self.notes if char == character and kind == mode}
                ),
                "cards": [
                    asdict(c) for c in self.cards if c.character == character and c.mode == mode
                ],
            }
            for mode in MODES
        }


def card_state(card_type: int, interval: int) -> str:
    """Temporary queue flags and filtered-deck placement do not redefine learning."""
    if card_type == 2:
        return "mature" if interval >= 21 else "young"
    if card_type not in (0, 1, 3):
        raise ValueError("Unsupported Anki card type.")
    return {0: "new", 1: "learning", 3: "relearning"}[card_type]
