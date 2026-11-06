from idp2aws.files import write_file


class TestWriteFile:
    def test_replaces_content_and_sets_mode(self, tmp_path):
        path = tmp_path / "credentials"
        path.write_text("old")
        path.chmod(0o644)

        write_file(path, "new", mode=0o600)

        assert path.read_text() == "new"
        assert path.stat().st_mode & 0o777 == 0o600
        assert [item.name for item in tmp_path.iterdir()] == ["credentials"]

    def test_creates_missing_folder(self, tmp_path):
        path = tmp_path / "new" / "file"

        write_file(path, "text")

        assert path.read_text() == "text"

    def test_writes_through_a_symlink(self, tmp_path):
        target = tmp_path / "real"
        target.write_text("old")
        link = tmp_path / "link"
        link.symlink_to(target)

        write_file(link, "new")

        assert link.is_symlink()
        assert target.read_text() == "new"
