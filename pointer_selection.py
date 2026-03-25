from __future__ import annotations

from dataclasses import dataclass, field


ALLOWED_MSD_PRECEDING_BYTES = {
    0x00,
    0x01,
    0x02,
    0x03,
    0x04,
    0x05,
    0x06,
    0x07,
    0x08,
    0x09,
    0x0A,
    0x0B,
    0x0C,
    0x0D,
    0x0E,
    0x0F,
    0x10,
    0x11,
    0x12,
    0x13,
    0x14,
    0x15,
    0x16,
    0x17,
    0x18,
    0x19,
    0x1A,
    0x1B,
    0x1C,
    0x1D,
    0x1E,
    0x1F,
    0x20,
    0x21,
    0x22,
    0x23,
    0x24,
    0x2B,
    0x39,
    0xFF,
}

POINTER_NEIGHBOR_WINDOW = 0x40
TEXT_COHERENCE_WINDOW = 0x1000
AUTO_DISAMBIGUATION_MIN_SCORE = 7
AUTO_DISAMBIGUATION_MIN_MARGIN = 3


@dataclass
class PointerCandidate:
    pointer_location: int
    text_location: int
    families: set[str] = field(default_factory=set)
    chain_lengths: set[int] = field(default_factory=set)
    source_details: list[dict[str, int | str | bool | None]] = field(default_factory=list)
    within_targets: bool = False
    in_msd_range: bool | None = None
    before_be_prefix: bool = False
    preceding_byte: int | None = None
    preceding_byte_allowed: bool | None = None

    def add_source(
        self,
        *,
        family: str,
        chain_length: int | None,
        within_targets: bool,
        in_msd_range: bool | None,
        before_be_prefix: bool,
        preceding_byte: int | None,
        preceding_byte_allowed: bool | None,
    ) -> None:
        self.families.add(family)
        if chain_length is not None:
            self.chain_lengths.add(chain_length)
        self.source_details.append(
            {
                "family": family,
                "chain_length": chain_length,
                "preceding_byte": None if preceding_byte is None else f"0x{preceding_byte:02x}",
                "preceding_byte_allowed": preceding_byte_allowed,
                "in_msd_range": in_msd_range,
                "before_be_prefix": before_be_prefix,
            }
        )
        self.within_targets = self.within_targets or within_targets
        self.before_be_prefix = self.before_be_prefix or before_be_prefix
        if preceding_byte is not None and self.preceding_byte is None:
            self.preceding_byte = preceding_byte
        if preceding_byte_allowed is not None and self.preceding_byte_allowed is None:
            self.preceding_byte_allowed = preceding_byte_allowed
        if in_msd_range is not None:
            self.in_msd_range = (self.in_msd_range or False) or in_msd_range

    def to_dict(self) -> dict[str, object]:
        return {
            "pointer_location": f"0x{self.pointer_location:05x}",
            "text_location": f"0x{self.text_location:05x}",
            "families": sorted(self.families),
            "chain_lengths": sorted(self.chain_lengths),
            "within_targets": self.within_targets,
            "in_msd_range": self.in_msd_range,
            "before_be_prefix": self.before_be_prefix,
            "preceding_byte": None if self.preceding_byte is None else f"0x{self.preceding_byte:02x}",
            "preceding_byte_allowed": self.preceding_byte_allowed,
            "sources": self.source_details,
        }


def add_candidate(
    candidate_map: dict[int, dict[int, PointerCandidate]],
    *,
    text_location: int,
    pointer_location: int,
    family: str,
    chain_length: int | None,
    within_targets: bool,
    in_msd_range: bool | None,
    before_be_prefix: bool,
    preceding_byte: int | None,
    preceding_byte_allowed: bool | None,
) -> None:
    by_pointer = candidate_map.setdefault(text_location, {})
    candidate = by_pointer.setdefault(
        pointer_location,
        PointerCandidate(pointer_location=pointer_location, text_location=text_location),
    )
    candidate.add_source(
        family=family,
        chain_length=chain_length,
        within_targets=within_targets,
        in_msd_range=in_msd_range,
        before_be_prefix=before_be_prefix,
        preceding_byte=preceding_byte,
        preceding_byte_allowed=preceding_byte_allowed,
    )


def score_candidates_for_text(
    text_location: int,
    candidate_map: dict[int, dict[int, PointerCandidate]],
    allowed_pointer_locations: set[int] | None = None,
) -> list[dict[str, object]]:
    by_pointer = candidate_map.get(text_location, {})
    if allowed_pointer_locations is None:
        candidates = list(by_pointer.values())
    else:
        candidates = [
            candidate
            for pointer_location, candidate in by_pointer.items()
            if pointer_location in allowed_pointer_locations
        ]

    scored: list[dict[str, object]] = []
    for candidate in candidates:
        score = 0
        reasons: list[str] = []

        if candidate.within_targets:
            score += 1
            reasons.append("within target set")

        if candidate.in_msd_range:
            score += 4
            reasons.append("within MSD pointer range")

        if candidate.before_be_prefix:
            score += 3
            reasons.append("preceded by BE direct-range prefix")

        if candidate.preceding_byte_allowed is True:
            score += 2
            reasons.append("allowed MSD preceding byte")
        elif candidate.preceding_byte_allowed is False:
            score -= 2
            reasons.append("unexpected MSD preceding byte")

        family_bonus = max(0, len(candidate.families) - 1)
        if family_bonus:
            score += family_bonus
            reasons.append(f"matched {len(candidate.families)} pointer families")

        if "plain-table" in candidate.families:
            score += 5
            reasons.append("plain pointer table entry")

        if "separated-table" in candidate.families:
            score += 4
            reasons.append("separated pointer table entry")

        pointer_neighbors = 0
        coherent_neighbors = 0
        incoherent_neighbors = 0
        exact_pointer_reuse = 0

        for other_text_location, other_by_pointer in candidate_map.items():
            if other_text_location == text_location:
                continue

            if candidate.pointer_location in other_by_pointer:
                exact_pointer_reuse += 1

            nearest_pointer_distance = min(
                abs(other_candidate.pointer_location - candidate.pointer_location)
                for other_candidate in other_by_pointer.values()
            )
            if nearest_pointer_distance > POINTER_NEIGHBOR_WINDOW:
                continue

            pointer_neighbors += 1
            if abs(other_text_location - text_location) <= TEXT_COHERENCE_WINDOW:
                coherent_neighbors += 1
            else:
                incoherent_neighbors += 1

        if pointer_neighbors:
            pointer_neighbor_bonus = min(pointer_neighbors, 4)
            score += pointer_neighbor_bonus
            reasons.append(f"{pointer_neighbors} nearby pointer neighbors")

        if coherent_neighbors:
            coherence_bonus = min(coherent_neighbors * 2, 8)
            score += coherence_bonus
            reasons.append(f"{coherent_neighbors} nearby same-file text neighbors")

        if incoherent_neighbors:
            incoherence_penalty = min(incoherent_neighbors * 2, 6)
            score -= incoherence_penalty
            reasons.append(f"{incoherent_neighbors} nearby cross-context text neighbors")

        if exact_pointer_reuse:
            reuse_penalty = exact_pointer_reuse * 3
            score -= reuse_penalty
            reasons.append(f"shared exact pointer with {exact_pointer_reuse} other text locations")

        scored.append(
            {
                "pointer_location": candidate.pointer_location,
                "score": score,
                "reasons": reasons,
                "pointer_neighbors": pointer_neighbors,
                "coherent_neighbors": coherent_neighbors,
                "incoherent_neighbors": incoherent_neighbors,
                "exact_pointer_reuse": exact_pointer_reuse,
            }
        )

    scored.sort(key=lambda item: (-item["score"], item["pointer_location"]))
    return scored


def choose_best_pointer_location(
    text_location: int,
    candidate_map: dict[int, dict[int, PointerCandidate]],
    allowed_pointer_locations: set[int] | None = None,
) -> tuple[int | None, list[dict[str, object]]]:
    scored = score_candidates_for_text(
        text_location,
        candidate_map,
        allowed_pointer_locations=allowed_pointer_locations,
    )
    if len(scored) < 2:
        return None, scored

    best = scored[0]
    second = scored[1]
    if best["score"] < AUTO_DISAMBIGUATION_MIN_SCORE:
        return None, scored
    if best["score"] - second["score"] < AUTO_DISAMBIGUATION_MIN_MARGIN:
        return None, scored
    return best["pointer_location"], scored
