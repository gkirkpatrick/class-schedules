"""Bitmask utilities for efficient time slot operations in precheck diagnostics."""

from typing import Iterator


class TimeMaskBuilder:
    """Build and manage bitmasks for time slots.

    Maps (day, period) coordinates to bit positions for efficient set operations.
    Supports up to 64 slots via int.bit_count(), or arbitrary size via Python's unlimited int.
    """

    def __init__(self, num_days: int, num_periods: int):
        """Initialize time mask builder.

        Args:
            num_days: Number of days in the cycle
            num_periods: Number of periods per day
        """
        self.num_days = num_days
        self.num_periods = num_periods
        self.total_slots = num_days * num_periods

    def slot_to_index(self, day: int, period: int) -> int:
        """Convert (day, period) to bit index.

        Args:
            day: Day number (0-indexed)
            period: Period number (0-indexed)

        Returns:
            Bit index for this slot
        """
        return day * self.num_periods + period

    def index_to_slot(self, idx: int) -> tuple[int, int]:
        """Convert bit index to (day, period).

        Args:
            idx: Bit index

        Returns:
            Tuple of (day, period)
        """
        day = idx // self.num_periods
        period = idx % self.num_periods
        return (day, period)

    def create_day_mask(self, day: int) -> int:
        """Create bitmask for all periods on a specific day.

        Args:
            day: Day number (0-indexed)

        Returns:
            Bitmask with bits set for all periods on this day
        """
        mask = 0
        for period in range(self.num_periods):
            mask |= 1 << self.slot_to_index(day, period)
        return mask

    def create_period_mask(self, period: int) -> int:
        """Create bitmask for specific period across all days.

        Args:
            period: Period number (0-indexed)

        Returns:
            Bitmask with bits set for this period on all days
        """
        mask = 0
        for day in range(self.num_days):
            mask |= 1 << self.slot_to_index(day, period)
        return mask

    def create_lunch_mask(self, start_period: int, span: int) -> int:
        """Create bitmask for lunch window (all days, specified periods).

        Args:
            start_period: Starting period of lunch window (0-indexed)
            span: Number of consecutive periods in lunch window

        Returns:
            Bitmask with bits set for lunch periods on all days
        """
        mask = 0
        for day in range(self.num_days):
            for offset in range(span):
                period = start_period + offset
                if 0 <= period < self.num_periods:
                    mask |= 1 << self.slot_to_index(day, period)
        return mask

    def create_recess_mask(self, recess_period: int | None) -> int:
        """Create bitmask for recess period (all days, one period).

        Args:
            recess_period: Period number for recess (0-indexed), or None

        Returns:
            Bitmask with bits set for recess period on all days, or 0 if None
        """
        if recess_period is None:
            return 0
        return self.create_period_mask(recess_period)

    def create_slot_mask(self, day: int, period: int) -> int:
        """Create bitmask for a single slot.

        Args:
            day: Day number (0-indexed)
            period: Period number (0-indexed)

        Returns:
            Bitmask with single bit set
        """
        return 1 << self.slot_to_index(day, period)

    def bitcount(self, mask: int) -> int:
        """Count set bits in mask.

        Args:
            mask: Bitmask

        Returns:
            Number of set bits
        """
        return mask.bit_count()

    def mask_overlaps(self, mask1: int, mask2: int) -> bool:
        """Check if two masks have any overlapping bits.

        Args:
            mask1: First bitmask
            mask2: Second bitmask

        Returns:
            True if masks overlap
        """
        return (mask1 & mask2) != 0

    def iter_set_bits(self, mask: int) -> Iterator[tuple[int, int]]:
        """Iterate over all set bits in mask, yielding (day, period).

        Args:
            mask: Bitmask

        Yields:
            (day, period) tuples for each set bit
        """
        idx = 0
        while mask:
            if mask & 1:
                yield self.index_to_slot(idx)
            mask >>= 1
            idx += 1

    def get_available_slots(
        self,
        full_mask: int,
        blocked_mask: int = 0
    ) -> int:
        """Get available slots by removing blocked slots.

        Args:
            full_mask: Initial availability mask
            blocked_mask: Slots to block (e.g., lunch, recess)

        Returns:
            Mask with blocked slots removed
        """
        return full_mask & ~blocked_mask

    def count_slots_per_day(self, mask: int) -> dict[int, int]:
        """Count available slots for each day.

        Args:
            mask: Availability bitmask

        Returns:
            Dictionary mapping day -> slot count
        """
        counts = {}
        for day in range(self.num_days):
            day_mask = self.create_day_mask(day)
            counts[day] = self.bitcount(mask & day_mask)
        return counts

    def create_full_week_mask(self) -> int:
        """Create mask with all slots set.

        Returns:
            Bitmask with all bits set for the entire week
        """
        return (1 << self.total_slots) - 1
