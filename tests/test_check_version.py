import pytest

import check_version
from idp2aws import __version__


class TestPackageVersion:
    def test_is_semver(self):
        assert check_version.parse(__version__) is not None

    def test_matches_init_file(self):
        assert check_version.read_version() == __version__


class TestParse:
    @pytest.mark.parametrize("version", ["1.2", "1.2.3.4", "01.2.3", "1.2.3rc1", "v1.2.3"])
    def test_rejects_non_semver(self, version):
        assert check_version.parse(version) is None

    def test_reads_numbers(self):
        assert check_version.parse("10.0.3") == (10, 0, 3)


class TestCheck:
    def test_first_release_can_be_any_semver(self):
        assert not check_version.check("v0.2.0", "0.2.0", [])

    @pytest.mark.parametrize("version", ["1.4.3", "1.5.0", "2.0.0"])
    def test_next_versions_are_allowed(self, version):
        assert not check_version.check(f"v{version}", version, ["1.4.1", "1.4.2"])

    @pytest.mark.parametrize("version", ["1.4.4", "1.5.1", "2.1.0", "1.4.1", "3.0.0"])
    def test_skipped_or_older_versions_are_refused(self, version):
        errors = check_version.check(f"v{version}", version, ["1.4.2"])

        assert errors
        assert "Use one of: 1.4.3, 1.5.0, 2.0.0." in errors[0]

    def test_tag_must_match_version(self):
        errors = check_version.check("v1.0.1", "1.0.0", [])

        assert errors == ["Tag 'v1.0.1' does not match the version. Use 'v1.0.0'."]

    def test_released_version_is_refused(self):
        errors = check_version.check("v1.0.0", "1.0.0", ["1.0.0"])

        assert errors == ["Version 1.0.0 is already on PyPI."]

    def test_non_semver_version_is_refused(self):
        errors = check_version.check("v1.0", "1.0", [])

        assert "is not MAJOR.MINOR.PATCH" in errors[0]

    def test_old_non_semver_releases_are_ignored(self):
        assert not check_version.check("v1.0.1", "1.0.1", ["0.9b1", "1.0.0"])
