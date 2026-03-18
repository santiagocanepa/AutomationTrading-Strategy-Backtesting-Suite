"""Tests for archetype factory — dynamic generation from combinatorial matrix."""

from __future__ import annotations

import pytest

from suitetrading.risk.archetypes._factory import (
    FACTORY_MATRIX,
    _archetype_name,
    _is_valid_combo,
    generate_factory_archetypes,
    get_factory_archetype_count,
)
from suitetrading.risk.contracts import RiskConfig


class TestFactoryNameGeneration:
    def test_basic_name(self):
        name = _archetype_name("roc", "fullrisk", "atr", "signal", None)
        assert name == "roc_fullrisk"

    def test_ftm_suffix(self):
        name = _archetype_name("roc", "fullrisk", "firestorm_tm", "signal", None)
        assert name == "roc_fullrisk_ftm"

    def test_policy_suffix(self):
        name = _archetype_name("roc", "fullrisk", "atr", "policy", None)
        assert name == "roc_fullrisk_tpol"

    def test_htf_suffix(self):
        name = _archetype_name("roc", "fullrisk", "atr", "signal", ("macd", "1d"))
        assert name == "roc_fullrisk_htf_macd"

    def test_all_suffixes(self):
        name = _archetype_name("roc", "fullrisk_pyr", "firestorm_tm", "policy", ("ema", "1d"))
        assert name == "roc_fullrisk_pyr_ftm_tpol_htf_ema"


class TestFactoryValidation:
    def test_same_entry_and_htf_invalid(self):
        assert not _is_valid_combo("macd", "atr", "signal", ("macd", "1d"))

    def test_different_entry_and_htf_valid(self):
        assert _is_valid_combo("roc", "atr", "signal", ("macd", "1d"))

    def test_no_htf_always_valid(self):
        assert _is_valid_combo("roc", "atr", "signal", None)


class TestFactoryGeneration:
    def test_generates_archetypes(self):
        registry, indicators = generate_factory_archetypes()
        assert len(registry) > 100

    def test_all_build_valid_config(self):
        registry, _ = generate_factory_archetypes()
        # Test a sample (not all, to keep test fast)
        sample_names = list(registry.keys())[:20]
        for name in sample_names:
            cls = registry[name]
            instance = cls()
            cfg = instance.build_config()
            assert isinstance(cfg, RiskConfig)

    def test_all_have_indicator_config(self):
        registry, indicators = generate_factory_archetypes()
        for name in registry:
            assert name in indicators, f"Missing indicator config for {name}"
            assert "entry" in indicators[name]
            assert "exit" in indicators[name]

    def test_count_matches_generation(self):
        count = get_factory_archetype_count()
        registry, _ = generate_factory_archetypes()
        assert count == len(registry)

    def test_no_duplicate_names(self):
        registry, _ = generate_factory_archetypes()
        names = list(registry.keys())
        assert len(names) == len(set(names))

    def test_ftm_archetypes_use_firestorm_stop(self):
        registry, _ = generate_factory_archetypes()
        ftm_names = [n for n in registry if "_ftm" in n]
        assert len(ftm_names) > 0
        for name in ftm_names[:5]:
            cfg = registry[name]().build_config()
            assert cfg.stop.model == "firestorm_tm"

    def test_policy_archetypes_use_policy_trailing(self):
        registry, _ = generate_factory_archetypes()
        pol_names = [n for n in registry if "_tpol" in n]
        assert len(pol_names) > 0
        for name in pol_names[:5]:
            cfg = registry[name]().build_config()
            assert cfg.trailing.trailing_mode == "policy"
