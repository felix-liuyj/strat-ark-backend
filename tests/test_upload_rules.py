"""OSS 上传规则测试。"""

import unittest

from libs.upload_rules import (
    build_upload_object_key,
    list_upload_directories,
    validate_object_key_directory,
    validate_oss_url,
    validate_upload_request,
)


class UploadRulesTest(unittest.TestCase):
    def test_known_directories_are_listed(self) -> None:
        self.assertIn("avatars", list_upload_directories())
        self.assertIn("materials", list_upload_directories())

    def test_empty_mime_type_is_resolved_by_extension(self) -> None:
        upload = validate_upload_request("avatars", "avatar.PNG", "")
        self.assertEqual("avatars", upload.directory)
        self.assertEqual("png", upload.extension)
        self.assertEqual("image/png", upload.content_type)

    def test_octet_stream_is_resolved_by_extension(self) -> None:
        upload = validate_upload_request("materials", "plan.pdf", "application/octet-stream")
        self.assertEqual("application/pdf", upload.content_type)

    def test_rejects_unknown_directory(self) -> None:
        with self.assertRaises(ValueError):
            validate_upload_request("tmp", "avatar.png")

    def test_rejects_extension_outside_directory_rule(self) -> None:
        with self.assertRaises(ValueError):
            validate_upload_request("avatars", "payload.zip")

    def test_build_object_key_uses_whitelisted_directory(self) -> None:
        object_key = build_upload_object_key("reports", "pdf")
        self.assertRegex(object_key, r"^reports/[0-9a-f]{32}\.pdf$")

    def test_confirm_object_key_rejects_traversal(self) -> None:
        with self.assertRaises(ValueError):
            validate_object_key_directory("avatars/../payload.png")

    def test_confirm_object_key_returns_normalized_key(self) -> None:
        object_key = validate_object_key_directory("/avatars/abcd1234.png")
        self.assertEqual("avatars/abcd1234.png", object_key)

    def test_validate_oss_url_requires_https_and_expected_host(self) -> None:
        object_key = validate_oss_url(
            "https://bucket.oss-cn-shanghai.aliyuncs.com/reports/result.pdf",
            "bucket.oss-cn-shanghai.aliyuncs.com",
        )
        self.assertEqual("reports/result.pdf", object_key)

    def test_validate_oss_url_rejects_foreign_host(self) -> None:
        with self.assertRaises(ValueError):
            validate_oss_url("https://evil.example.com/reports/result.pdf", "bucket.example.com")


if __name__ == "__main__":
    unittest.main()
