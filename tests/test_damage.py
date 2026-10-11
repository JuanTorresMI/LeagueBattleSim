"""Resistance and penetration math.

Order (League Wiki, Armor penetration): % reduction, then % penetration, then flat
penetration (lethality), floored at 0; reduction can push resists below zero, and
penetration never applies to negative resists."""
import pytest

from engine import eff_resist, resist_mult, rend_raw


def test_resist_multiplier():
    assert resist_mult(0) == 1.0
    assert resist_mult(100) == pytest.approx(0.5)
    assert resist_mult(-100) == pytest.approx(1.5)


def test_reduction_then_percent_pen_then_flat_pen():
    # 100 armor, 30% reduction, 35% pen, 10 lethality: 100 -> 70 -> 45.5 -> 35.5
    assert eff_resist(100, 0.30, 0.35, 10) == pytest.approx(35.5)
    # the other orders would give different answers
    assert eff_resist(100, 0.30, 0.35, 10) != pytest.approx((100 - 10) * 0.70 * 0.65)
    assert eff_resist(100, 0.30, 0.35, 10) != pytest.approx((100 * 0.70 - 10) * 0.65)


def test_flat_pen_floors_at_zero():
    assert eff_resist(10, 0, 0, 18) == 0.0


def test_pen_does_not_apply_to_negative_resist():
    assert eff_resist(-20, 0.0, 0.35, 18) == -20
    assert eff_resist(-20, 0.5, 0.35, 18) == -10


def test_rend_scaling():
    # rank 5, 100 AD, 0 AP: first spear 45 + 70, each extra 35 + 50
    assert rend_raw(100, 0, 5, 1) == pytest.approx(115)
    assert rend_raw(100, 0, 5, 3) == pytest.approx(115 + 2 * 85)
    assert rend_raw(100, 50, 1, 2) == pytest.approx(5 + 70 + 32.5 + 7 + 20 + 25)
    assert rend_raw(100, 0, 0, 3) == 0
    assert rend_raw(100, 0, 5, 0) == 0
