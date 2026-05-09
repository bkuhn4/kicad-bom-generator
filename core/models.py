from __future__ import annotations
from dataclasses import dataclass, field
from typing import List


@dataclass
class PackagingVariant:
    packaging_type: str       # e.g. "Tape & Reel (TR)", "Cut Tape (CT)", "DigiReel®"
    part_number: str
    stock: int = 0
    unit_price: float = 0.0


@dataclass
class BomRow:
    references: str = ""
    description: str = ""
    package: str = ""
    mf_part_number: str = ""
    manufacturer: str = ""

    digikey_variants: List[PackagingVariant] = field(default_factory=list)
    digikey_selected_packaging: str = ""

    mouser_variants: List[PackagingVariant] = field(default_factory=list)
    mouser_selected_packaging: str = ""

    lcsc_pn: str = ""
    lcsc_stock: int = 0

    notes: str = ""
    lookup_status: str = "idle"   # idle | loading | found | not_found | error
    lookup_error: str = ""

    # ------------------------------------------------------------------ #
    # Derived properties
    # ------------------------------------------------------------------ #

    @property
    def digikey_pn(self) -> str:
        for v in self.digikey_variants:
            if v.packaging_type == self.digikey_selected_packaging:
                return v.part_number
        return self.digikey_variants[0].part_number if self.digikey_variants else ""

    @property
    def mouser_pn(self) -> str:
        for v in self.mouser_variants:
            if v.packaging_type == self.mouser_selected_packaging:
                return v.part_number
        return self.mouser_variants[0].part_number if self.mouser_variants else ""

    @property
    def digikey_stock(self) -> int:
        for v in self.digikey_variants:
            if v.packaging_type == self.digikey_selected_packaging:
                return v.stock
        return self.digikey_variants[0].stock if self.digikey_variants else 0

    @property
    def mouser_stock(self) -> int:
        for v in self.mouser_variants:
            if v.packaging_type == self.mouser_selected_packaging:
                return v.stock
        return self.mouser_variants[0].stock if self.mouser_variants else 0

    def digikey_packaging_options(self) -> List[str]:
        return [v.packaging_type for v in self.digikey_variants]

    def mouser_packaging_options(self) -> List[str]:
        return [v.packaging_type for v in self.mouser_variants]
