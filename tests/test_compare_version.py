import pytest

from compare_version import CompareVersion


class TestEqualVersions:
    def test_equal_versions_eq_true(self):
        assert CompareVersion.vr_compare("1.0-1", "EQ", "1.0-1") is True

    def test_equal_versions_ge_le_true(self):
        assert CompareVersion.vr_compare("1.0-1", "GE", "1.0-1") is True
        assert CompareVersion.vr_compare("1.0-1", "LE", "1.0-1") is True

    def test_equal_versions_strict_operators_false(self):
        assert CompareVersion.vr_compare("1.0-1", "GT", "1.0-1") is False
        assert CompareVersion.vr_compare("1.0-1", "LT", "1.0-1") is False

    def test_equal_versions_unknown_operator_false(self):
        assert CompareVersion.vr_compare("1.0-1", "XX", "1.0-1") is False

    def test_equal_with_default_epoch(self):
        assert CompareVersion.vr_compare("1.0", "EQ", "0:1.0") is True

    def test_equal_version_without_release_stripped(self):
        assert CompareVersion.vr_compare("1.0", "EQ", "1.0") is True


class TestNumericComparison:
    def test_greater_minor(self):
        assert CompareVersion.vr_compare("1.1-1", "GT", "1.0-1") is True

    def test_lower_minor(self):
        assert CompareVersion.vr_compare("1.0-1", "LT", "1.1-1") is True

    def test_greater_release(self):
        assert CompareVersion.vr_compare("1.0-2", "GT", "1.0-1") is True

    def test_ge_and_le(self):
        assert CompareVersion.vr_compare("2.0-1", "GE", "1.0-1") is True
        assert CompareVersion.vr_compare("1.0-1", "LE", "2.0-1") is True

    def test_wrong_direction_is_false(self):
        assert CompareVersion.vr_compare("1.0-1", "GT", "2.0-1") is False
        assert CompareVersion.vr_compare("2.0-1", "LT", "1.0-1") is False
        assert CompareVersion.vr_compare("1.0-2", "EQ", "1.0-1") is False

    def test_epoch_takes_precedence(self):
        assert CompareVersion.vr_compare("2:1.0-1", "GT", "1:2.0-1") is True
        assert CompareVersion.vr_compare("1:1.0-1", "GT", "2:1.0-1") is False


class TestDifferentLength:
    def test_longer_version_is_greater(self):
        assert CompareVersion.vr_compare("1.0.1-1", "GT", "1.0-1") is True

    def test_shorter_version_is_lower(self):
        assert CompareVersion.vr_compare("1.0-1", "LT", "1.0.1-1") is True

    def test_longer_with_non_matching_operator_is_false(self):
        assert CompareVersion.vr_compare("1.0.1-1", "LT", "1.0-1") is False
        assert CompareVersion.vr_compare("1.0-1", "GT", "1.0.1-1") is False

    def test_extra_release_segment_decides(self):
        assert CompareVersion.vr_compare("1.0-1.1", "GT", "1.0-1") is True


class TestLeadingZerosAndLetters:
    def test_leading_zero_compared_as_string(self):
        assert CompareVersion.vr_compare("1.1", "GT", "1.01") is True
        assert CompareVersion.vr_compare("1.01", "GT", "1.1") is False

    def test_letter_suffix_compared_as_string(self):
        assert CompareVersion.vr_compare("1.0a", "GT", "1.0") is True
        assert CompareVersion.vr_compare("1.0a", "EQ", "1.0a") is True


class TestOperatorEdgeCases:
    @pytest.mark.parametrize(
        "x_version,y_version",
        [
            ("1.0-1", "0.9-1"),
            ("1:1.0-1", "0:0.9-1"),
        ],
    )
    def test_unknown_operator_never_matches(self, x_version, y_version):
        assert CompareVersion.vr_compare(x_version, "NE", y_version) is False
