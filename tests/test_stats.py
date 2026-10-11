"""Base stats and the stat engine against the League Wiki.

Source: https://wiki.leagueoflegends.com/en-us/Module:ChampionData/data (Kalista,
patch 16.20): HP 560 +114, AD 57 +4.75, armor 24 +5.2, MR 33 +1.1,
AS 0.694 +4.5% (ratio 0.694)."""
import pytest

from engine import (AD_GROWTH_OVERRIDE, CHAMPS, RunePage, build_stats, growth, lvl_scale,
                    statline)

# level -> (HP, AD, armor, MR, attack speed)
KALISTA_WIKI = {
    1: (560, 57, 24, 33, 0.694),
    18: (2498, 137.75, 112.4, 51.7, 0.694 * (1 + 0.045 * 17)),
}
NO_RUNES = RunePage("Lethal Tempo", "Alacrity", 0, "Coup de Grace")


def test_growth_curve_endpoints():
    assert growth(1) == 0
    assert growth(18) == pytest.approx(17)        # stat(18) = base + 17 x per-level
    assert growth(2) == pytest.approx(0.72)


def test_lvl_scale_follows_growth_curve():
    assert lvl_scale(40, 174.12, 1) == 40
    assert lvl_scale(40, 174.12, 18) == pytest.approx(174.12)
    assert lvl_scale(0, 17, 9) == pytest.approx(growth(9))


@pytest.mark.parametrize("level", sorted(KALISTA_WIKI))
def test_kalista_base_stats_match_wiki(level):
    hp, ad, armor, mr, aspd = KALISTA_WIKI[level]
    st = build_stats("Kalista", level, [], NO_RUNES)
    assert st.hp == pytest.approx(hp)
    assert st.ad == pytest.approx(ad)
    assert st.armor == pytest.approx(armor)
    assert st.mr == pytest.approx(mr)
    # Alacrity at 0 stacks still gives its flat 3% AS, so compare without it
    assert st.attack_speed(-NO_RUNES.alacrity_as()) == pytest.approx(aspd)


def test_ad_growth_override_is_needed():
    # Data Dragon 16.20.1 reports 0 AD growth; the override supplies the wiki value
    assert CHAMPS["Kalista"]["stats"]["attackdamageperlevel"] == 0
    assert AD_GROWTH_OVERRIDE["Kalista"] == 4.75


def test_attack_speed_cap():
    st = build_stats("Kalista", 18, [], NO_RUNES)
    assert st.attack_speed(10.0) == 2.5


def test_item_stats_and_description_extras():
    # Infinity Edge: crit from Data Dragon, +30% crit damage from the description table
    st = build_stats("Kalista", 13, ["3031"], NO_RUNES)
    assert st.crit_damage == pytest.approx(2.30)
    # Lord Dominik's armor pen
    assert build_stats("Kalista", 13, ["3036"], NO_RUNES).armor_pen == pytest.approx(0.35)


def test_statline_reference_build():
    line = statline("Kalista", 13, ["3032", "3031", "3036", "3006"], RunePage("Press the Attack", "Alacrity", 7, "Cut Down"))
    assert line["crit dmg %"] == 230
    assert line["armor pen %"] == 35.0
    assert line["HP"] == round(560 + 114 * growth(13))
