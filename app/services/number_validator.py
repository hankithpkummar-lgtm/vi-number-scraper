"""
HCS Number Validator — Exact port of GAS v6 / gas-engine.ts validation pipeline.
Replaces scraper.py's inline validate_number() with the real GAS validation rules.

Usage:
  from app.services.number_validator import NumberValidator
  v = NumberValidator()
  result = v.validate("9876543210")
  if result.valid:
      print(f"Root: {result.root}, Compound: {result.compound}, Free: {result.is_free}")
"""

import hashlib
import random
from dataclasses import dataclass, field
from typing import List, Optional


# ─── CONSTANTS (exact copy from gas-engine.ts) ──────────────────────

PLANET_MAP: dict[int, str] = {
    1: "Sun", 2: "Moon", 3: "Jupiter", 4: "Rahu",
    5: "Mercury", 6: "Venus", 7: "Ketu", 8: "Saturn", 9: "Mars",
}

LUCKY_ROOTS: List[int] = [1, 3, 5, 6]

BLOCKED_X6_PAIRS: List[str] = ["16", "26", "36", "46", "56", "76", "86"]

GOOD_PAIRS: List[str] = [
    "11", "13", "31", "15", "51", "17", "71", "19", "91",
    "33", "35", "53", "37", "73", "39", "93",
    "55", "57", "75", "59", "95", "79", "97", "99",
]

FRIENDLY: dict[int, List[int]] = {
    1: [3, 5, 6, 9], 2: [1, 3, 5, 9], 3: [1, 2, 5, 6, 9],
    4: [1, 5, 9], 5: [1, 3, 6, 9], 6: [1, 3, 5],
    7: [1, 3, 5], 8: [1, 3, 5], 9: [1, 3, 5],
}

GOOD_COMPOUNDS: dict[int, List[int]] = {
    1: [46, 64, 37, 55],
    3: [66, 39, 30],
    5: [41, 32, 50, 59],
    6: [42, 24, 33, 60],
}

# ─── RESULT DATACLASSES ──────────────────────────────────────────────


@dataclass
class ClassificationResult:
    is_free: bool
    reason: str  # "invalid" | "contains_zero" | "blocked_prefix_7090" | "zero_in_last_6" | "paid"


@dataclass
class ValidationResult:
    valid: bool = False
    reason: str = ""
    normalized: str = ""
    root: int = 0
    compound: int = 0
    hash_str: str = ""
    dedup_key: str = ""
    is_free: bool = False
    classification: str = ""
    price: int = 0


# ─── VALIDATOR CLASS ─────────────────────────────────────────────────


class NumberValidator:
    """
    Complete number validation pipeline — exact port of GAS v6 addNumber() + gas-engine.ts.
    Use this BEFORE sending any number to GAS for storage.
    """

    # ─── PHASE 1: NORMALIZE ───────────────────────────────────────

    @staticmethod
    def normalize_phone(input_str: str) -> str:
        """
        Normalize a phone number to 10 digits.
        Exact port of gas-engine.ts normalizePhone().
        """
        if not input_str:
            return ""
        digits = "".join(ch for ch in str(input_str) if ch.isdigit())
        if len(digits) > 10:
            if digits.startswith("91") and len(digits) == 12:
                digits = digits[2:]
            elif digits.startswith("0") and len(digits) == 11:
                digits = digits[1:]
        if len(digits) == 11 and digits.startswith("0"):
            digits = digits[1:]
        if len(digits) != 10:
            return ""
        if digits[0] in ("0", "1"):
            return ""
        return digits

    # ─── PHASE 2: COMPUTATIONS ────────────────────────────────────

    @staticmethod
    def compute_root(digits: str) -> int:
        """Sum digits recursively until single digit. Exact port of computeRoot()."""
        total = sum(int(d) for d in digits)
        while total > 9:
            total = sum(int(d) for d in str(total))
        return total

    @staticmethod
    def compute_compound(digits: str) -> int:
        """Sum all digits. Exact port of computeCompound()."""
        return sum(int(d) for d in digits)

    @staticmethod
    def compute_single_total(n: int) -> int:
        """Reduce to single digit. Exact port of computeSingleTotal()."""
        while n > 9:
            n = sum(int(d) for d in str(n))
        return n

    @staticmethod
    def get_hash(normalized: str) -> str:
        """Simple hash for dedup tracking. Exact port of getHash()."""
        import hashlib
        h = int(hashlib.sha1(normalized.encode()).hexdigest()[:8], 16)
        return f"h_{abs(h) & 0x7FFFFFFF:08x}"

    @staticmethod
    def get_dedup_key(normalized: str) -> str:
        """Last 6 digits for dedup matching. Exact port of getDedupKey()."""
        return normalized[-6:] if len(normalized) >= 6 else normalized

    # ─── PHASE 3: CLASSIFICATION ──────────────────────────────────

    @classmethod
    def classify(cls, number: str) -> ClassificationResult:
        """
        Determine if a number is free or paid.
        Exact port of getNumberClassification().
        """
        normalized = cls.normalize_phone(number)
        if not normalized:
            return ClassificationResult(is_free=False, reason="invalid")
        if "0" in normalized:
            return ClassificationResult(is_free=True, reason="contains_zero")
        if normalized.startswith("7090"):
            return ClassificationResult(is_free=True, reason="blocked_prefix_7090")
        last6 = normalized[-6:]
        if "0" in last6:
            return ClassificationResult(is_free=True, reason="zero_in_last_6")
        return ClassificationResult(is_free=False, reason="paid")

    # ─── PHASE 4: VALIDATION PIPELINE ─────────────────────────────

    @classmethod
    def validate_for_storage(cls, normalized: str) -> ValidationResult:
        """
        THE COMPLETE VALIDATION PIPELINE — exact port of gas-engine.ts validateNumberForStorage().
        Run this BEFORE sending any number to GAS.

        Rules (in order):
        1. Must be 10 digits
        2. Block 7090 prefix
        3. Block zero in last 6 digits
        4. Block X6 pairs (16,26,36,46,56,76,86) — allow 96 at end, 969 anywhere
        5. Root must be in [1, 3, 5, 6] (lucky)
        6. No digits 2, 4, 8
        7. No double zero (00)
        """
        result = ValidationResult(normalized=normalized)

        # 1. Format check
        if not normalized or len(normalized) != 10:
            return ValidationResult(valid=False, reason="Invalid format — must be 10 digits")

        # 2. Block 7090 prefix
        if normalized.startswith("7090"):
            return ValidationResult(valid=False, reason="Contains 7090 prefix — blocked")

        # 3. Block zero in last 6 digits
        last6 = normalized[-6:]
        if "0" in last6:
            return ValidationResult(valid=False, reason="Zero in last 6 digits — blocked")

        # 4. Block X6 pairs with 96/969 exceptions
        for pi in range(len(normalized) - 1):
            pair = normalized[pi:pi + 2]
            if pair in BLOCKED_X6_PAIRS:
                # Allow 96 at the very end
                if pair == "96" and pi == len(normalized) - 2:
                    continue
                # Allow 969 anywhere
                if pair == "96" and pi + 2 < len(normalized) and normalized[pi + 2] == "9":
                    continue
                # Allow 69 if preceded by 9 (part of 969)
                if pair == "69" and pi > 0 and normalized[pi - 1] == "9":
                    continue
                return ValidationResult(valid=False, reason=f"Blocked pair {pair}")

        # 5. Root must be lucky [1, 3, 5, 6]
        root = cls.compute_root(normalized)
        if root not in LUCKY_ROOTS:
            return ValidationResult(valid=False, reason=f"Total {root} not in lucky [1,3,5,6]")

        # 6. No digits 2, 4, 8
        if any(d in normalized for d in "248"):
            return ValidationResult(valid=False, reason="Contains digits 2, 4, or 8 — blocked")

        # 7. No double zero
        if "00" in normalized:
            return ValidationResult(valid=False, reason="Contains 00 — blocked")

        # ─── ALL CHECKS PASSED ────────────────────────────────────
        compound = cls.compute_compound(normalized)
        classification = cls.classify(normalized)

        return ValidationResult(
            valid=True,
            normalized=normalized,
            root=root,
            compound=compound,
            hash_str=cls.get_hash(normalized),
            dedup_key=cls.get_dedup_key(normalized),
            is_free=classification.is_free,
            classification=classification.reason,
            price=cls.get_random_pricing() if not classification.is_free else 0,
        )

    # ─── PHASE 5: PRE-VALIDATE (convenience wrapper) ──────────────

    @classmethod
    def pre_validate(cls, raw_number: str) -> ValidationResult:
        """
        One-call: normalize + validate + compute + classify.
        Exact port of gas-engine.ts preValidateNumber().
        Returns a ValidationResult with all fields populated if valid.
        """
        normalized = cls.normalize_phone(raw_number)
        if not normalized:
            return ValidationResult(valid=False, reason="Invalid phone number format")
        return cls.validate_for_storage(normalized)

    # ─── PRICING ──────────────────────────────────────────────────

    @staticmethod
    def get_random_pricing(min_price: int = 2399, max_price: int = 5099) -> int:
        """
        Generate pricing that reduces to 3 or 5 (lucky totals).
        Exact port of gas-engine.ts getRandomPricing().
        """
        price = random.randint(min_price, max_price)
        price_total = sum(int(d) for d in str(price))
        single = price_total
        while single > 9:
            single = sum(int(d) for d in str(single))
        if single in (3, 5):
            return price
        return 2399  # fallback

    # ─── EXACT VALIDITY CHECK (matches GAS v6 addNumber get route) ─

    @classmethod
    def is_valid_for_gas(cls, raw_number: str) -> bool:
        """
        Quick boolean check — does this number pass ALL GAS v6 filters?
        Replaces scraper.py's validate_number() with the EXACT GAS logic.
        """
        result = cls.pre_validate(raw_number)
        return result.valid


# ─── BATCH VALIDATION ────────────────────────────────────────────────


def validate_batch(numbers: List[str]) -> List[ValidationResult]:
    """
    Validate a batch of raw numbers.
    Returns list of ValidationResult (valid=True for ones that should be stored).
    """
    validator = NumberValidator()
    return [validator.pre_validate(n) for n in numbers]


def filter_valid(numbers: List[str]) -> List[ValidationResult]:
    """Return only valid numbers from a list of raw numbers."""
    return [r for r in validate_batch(numbers) if r.valid]


# ─── TEST WITH KNOWN CASES ──────────────────────────────────────────

if __name__ == "__main__":
    v = NumberValidator()

    test_cases = [
        # ── Valid cases ──
        ("9999999991", True, 1),     # 99x4 + 91, no zeros/bads, root=1 lucky
        ("9135791357", True, 5),     # All lucky digits 1,3,5,7,9 → root=5
        ("9191919191", True, 5),     # 91 good pair, root=5
        ("9999999996", True, 6),     # root=6, 96 at very end → allowed
        ("9999969999", True, 6),     # 969 anywhere → allowed, root=6

        # ── Blocked cases ──
        ("7090123456", False, None), # 7090 prefix — blocked
        ("9876504321", False, None), # Zero in last 6
        ("1234567890", False, None), # starts with 1
        ("0", False, None),          # too short
        ("", False, None),           # empty
        ("9876543210", False, None), # Zero in last 6 (6543210)
        ("9876512345", False, None), # has 2
        ("9876543216", False, None), # X6 pair (76 inside)
        ("9876596900", False, None), # 969 allowed but has 0 in last6
        ("9897969594", False, None), # contains 8 and 4
        ("9999999999", False, None), # root 9 not lucky
        ("7777777777", False, None), # root 7 not lucky
        ("8888888888", False, None), # has 8
        ("9876540098", False, None), # double zero (00)
        ("919876594321", False, None), # 91 prefix → 9876594321 → has 4
        ("9999999916", False, None), # 16 in middle → X6 pair blocked
        ("9999999969", True, 6),     # 969 at end → root=6, 96 is at pos 8 (second-to-last pair), so 96 is at end? No, 69 is at end. Let me check...
        # Actually: 9999999969 → digits: 9,9,9,9,9,9,9,9,6,9. Pairs: 99,99,99,99,99,99,99,99,96,69.
        # 96 at pos 8 (second-to-last) → that's not at the very end → but pos 8 + 2 = 10 = len, YES it's the last pair.
        # So 96 at very end → allowed!
        #   root = 9+9+9+9+9+9+9+9+6+9 = 87 → 15 → 6 → lucky!
    ]

    print("=" * 70)
    print("HCS Number Validator — Test Suite")
    print("=" * 70)
    passed = 0
    failed = 0
    for raw, expected_valid, expected_root in test_cases:
        result = v.pre_validate(raw)
        ok = result.valid == expected_valid
        if ok and expected_root is not None:
            ok = result.root == expected_root
        status = "✅ PASS" if ok else "❌ FAIL"
        if ok:
            passed += 1
        else:
            failed += 1
        details = f"root={result.root}" if result.valid else f"reason={result.reason}"
        expected = f"exp: valid={expected_valid}"
        if expected_root:
            expected += f" root={expected_root}"
        print(f"  {status} | {raw:15s} | {details:40s} | {expected}")

    print("=" * 70)
    print(f"  Results: {passed} passed, {failed} failed out of {len(test_cases)}")
    print("=" * 70)
