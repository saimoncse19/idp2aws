from datetime import datetime, timedelta, timezone

import pytest

from idp2aws import aws


@pytest.fixture
def credentials_path(tmp_path, monkeypatch):
    path = tmp_path / "credentials"
    monkeypatch.setenv("AWS_SHARED_CREDENTIALS_FILE", str(path))
    return path


def make_credentials(hours_left=1):
    return aws.Credentials(
        access_key_id="ASIAEXAMPLE",
        secret_access_key="secret",
        session_token="token",
        expiration=datetime.now(timezone.utc) + timedelta(hours=hours_left),
    )


class TestSaveCredentials:
    def test_writes_only_the_standard_keys(self, credentials_path):
        saved = make_credentials()

        aws.save_credentials("dev", saved)

        assert aws.load_credentials("dev", saved.expiration) == saved
        assert credentials_path.read_text().count(" = ") == 3
        assert credentials_path.stat().st_mode & 0o777 == 0o600

    def test_makes_existing_file_private(self, credentials_path):
        credentials_path.write_text("")
        credentials_path.chmod(0o644)

        aws.save_credentials("dev", make_credentials())

        assert credentials_path.stat().st_mode & 0o777 == 0o600

    def test_keeps_other_profiles(self, credentials_path):
        credentials_path.write_text("[other]\naws_access_key_id = AKIA\n")

        aws.save_credentials("dev", make_credentials())

        assert "[other]" in credentials_path.read_text()


class TestLoadCredentials:
    def test_missing_or_incomplete_profile(self, credentials_path):
        credentials_path.write_text("[other]\naws_access_key_id = AKIA\n")
        expiration = datetime.now(timezone.utc)

        assert aws.load_credentials("other", expiration) is None
        assert aws.load_credentials("missing", expiration) is None


class TestCredentials:
    def test_is_expired(self):
        assert make_credentials(hours_left=-1).is_expired
        assert not make_credentials(hours_left=1).is_expired

    def test_keys_close_to_expiry_count_as_expired(self):
        assert make_credentials(hours_left=2 / 60).is_expired


class TestGetStsRegion:
    @pytest.mark.parametrize(
        ("destination", "region"),
        [
            ("https://signin.aws.amazon.com/saml", "us-east-1"),
            ("https://signin.amazonaws-us-gov.com/saml", "us-gov-west-1"),
            ("https://signin.amazonaws.cn/saml", "cn-north-1"),
            (None, "us-east-1"),
        ],
    )
    def test_region_follows_partition(self, destination, region):
        assert aws.get_sts_region(destination) == region
