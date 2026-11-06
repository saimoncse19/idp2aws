from datetime import datetime, timezone

import pytest

from idp2aws import settings

URL = "https://accounts.google.com/o/saml2/initsso?idpid=X&spid=Y"


@pytest.fixture
def config_path(tmp_path):
    path = tmp_path / "config.toml"
    settings.create_config(settings.Settings(URL), path)
    return path


class TestLoadSettings:
    def test_shared_settings(self, config_path):
        result = settings.load_settings("dev", config_path)

        assert result == settings.Settings(URL, "chrome", 1, None)

    def test_profile_overrides_shared_settings(self, config_path):
        with config_path.open("a") as file:
            file.write('[profiles.prod]\nrole_arn = "arn:role"\nsession_hours = 4\n')

        result = settings.load_settings("prod", config_path)

        assert result == settings.Settings(URL, "chrome", 4, "arn:role")

    def test_missing_file_says_how_to_start(self, tmp_path):
        with pytest.raises(settings.SettingsError, match="idp2aws setup"):
            settings.load_settings("dev", tmp_path / "missing.toml")

    def test_unknown_key(self, config_path):
        with config_path.open("a") as file:
            file.write('[profiles.dev]\ncolour = "blue"\n')

        with pytest.raises(settings.SettingsError, match="colour"):
            settings.load_settings("dev", config_path)

    @pytest.mark.parametrize(
        ("line", "error"),
        [
            ('session_hours = "4"', "session_hours must be a whole number"),
            ("session_hours = 13", "session_hours must be a whole number"),
            ("session_hours = true", "session_hours must be a whole number"),
            ('browser = "firefox"', "browser must be one of chrome, chromium, msedge"),
            ('start_url = "http://idp"', "start_url must be an https:// URL"),
            ("role_arn = 1", "role_arn must be text"),
        ],
    )
    def test_bad_value(self, config_path, line, error):
        with config_path.open("a") as file:
            file.write(f"[profiles.dev]\n{line}\n")

        with pytest.raises(settings.SettingsError, match=error):
            settings.load_settings("dev", config_path)

    def test_not_toml(self, tmp_path):
        path = tmp_path / "config.toml"
        path.write_text("start_url = \n")

        with pytest.raises(settings.SettingsError, match="not valid TOML"):
            settings.load_settings("dev", path)


class TestCreateConfig:
    def test_lists_configured_profiles(self, config_path):
        with config_path.open("a") as file:
            file.write("[profiles.prod]\n[profiles.dev]\n")

        assert settings.configured_profiles(config_path) == ["dev", "prod"]

    def test_does_not_overwrite(self, config_path):
        with pytest.raises(settings.SettingsError, match="already exists"):
            settings.create_config(settings.Settings(URL), config_path)


class TestProfiles:
    def test_save_and_load(self, tmp_path):
        path = tmp_path / "profiles.json"
        dev = settings.Profile("dev", "arn:dev", datetime(2026, 1, 1, tzinfo=timezone.utc))
        prod = settings.Profile("prod", "arn:prod", datetime(2026, 1, 2, tzinfo=timezone.utc))

        settings.save_profile(dev, path)
        settings.save_profile(prod, path)

        assert settings.load_profiles(path) == {"dev": dev, "prod": prod}

    def test_no_file_means_no_profiles(self, tmp_path):
        assert not settings.load_profiles(tmp_path / "missing.json")
