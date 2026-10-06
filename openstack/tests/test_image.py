from contextlib import redirect_stderr, redirect_stdout
from hashlib import md5, sha256
from io import StringIO
from pathlib import Path
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from snakemake_executor_plugin_guix_openstack.image import (
    DIGEST_PROPERTY,
    PUBLISHER,
    PUBLISHER_PROPERTY,
    ImageEnsureError,
    ensure_image,
    main,
)


class FakeCloud:
    def __init__(self, *, project="project-id", region="GRA11", images=None,
                 upload_status="ACTIVE"):
        self.project = project
        self.region = region
        self.images = list(images or [])
        self.uploads = []
        self.gets = []
        self.closed = False
        self.upload_error = None
        self.upload_status = upload_status

    def image_scope(self):
        return self.project, self.region

    def list_images(self, *, name):
        return [image for image in self.images if image.name == name]

    def get_image(self, image_id):
        self.gets.append(image_id)
        return next((image for image in self.images if image.id == image_id), None)

    def create_image(self, **kwargs):
        self.uploads.append(kwargs)
        image = SimpleNamespace(
            id="new-image", name=kwargs["name"], status=self.upload_status,
            owner=self.project, visibility="private", disk_format="qcow2",
            container_format="bare", size=Path(kwargs["filename"]).stat().st_size,
            checksum=kwargs["md5"], hash_algo="sha256", hash_value=kwargs["sha256"],
            properties=kwargs["properties"], region=self.region,
        )
        self.images.append(image)
        if self.upload_error:
            raise self.upload_error
        return image

    def close(self):
        self.closed = True


class ImageEnsureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "worker.qcow2"
        self.data = b"QFI\xfb" + b"small test qcow2 payload"
        self.path.write_bytes(self.data)
        self.digest = sha256(self.data).hexdigest()
        self.md5 = md5(self.data, usedforsecurity=False).hexdigest()
        self.name = f"guix-worker-{self.digest[:16]}"

    def image(self, **overrides):
        values = dict(
            id="existing-image", name=self.name, status="ACTIVE", owner="project-id",
            visibility="private", disk_format="qcow2", container_format="bare",
            size=len(self.data), checksum=self.md5, hash_algo="sha256",
            hash_value=self.digest,
            properties={DIGEST_PROPERTY: self.digest, PUBLISHER_PROPERTY: PUBLISHER},
            region="GRA11",
        )
        values.update(overrides)
        return SimpleNamespace(**values)

    def ensure(self, cloud, **kwargs):
        return ensure_image(cloud, self.path, name_prefix="guix-worker",
                            region="GRA11", timeout=1, **kwargs)

    def test_reuses_exact_active_private_image_without_upload(self):
        cloud = FakeCloud(images=[self.image()])
        self.assertEqual(self.ensure(cloud), "existing-image")
        self.assertEqual(cloud.uploads, [])
        self.assertEqual(cloud.gets, ["existing-image"])

    def test_uploads_absent_image_with_versioned_private_metadata_and_wait(self):
        cloud = FakeCloud()
        with redirect_stderr(StringIO()):
            result = self.ensure(cloud)
        self.assertEqual(result, "new-image")
        self.assertEqual(len(cloud.uploads), 1)
        upload = cloud.uploads[0]
        self.assertEqual(upload["name"], self.name)
        self.assertEqual(upload["visibility"], "private")
        self.assertEqual(upload["disk_format"], "qcow2")
        self.assertEqual(upload["container_format"], "bare")
        self.assertEqual(upload["properties"], {
            DIGEST_PROPERTY: self.digest, PUBLISHER_PROPERTY: PUBLISHER,
        })
        self.assertEqual(upload["sha256"], self.digest)
        self.assertEqual(upload["md5"], self.md5)
        self.assertTrue(upload["validate_checksum"])
        self.assertTrue(upload["wait"])
        self.assertTrue(upload["allow_duplicates"])
        self.assertEqual(cloud.gets, ["new-image"])

    def test_duplicate_name_is_an_error_without_upload_or_delete(self):
        cloud = FakeCloud(images=[self.image(), self.image(id="duplicate")])
        with self.assertRaisesRegex(ImageEnsureError, "multiple images"):
            self.ensure(cloud)
        self.assertEqual(cloud.uploads, [])

    def test_conflicting_metadata_or_validation_mismatch_is_an_error(self):
        cloud = FakeCloud(images=[self.image(properties={DIGEST_PROPERTY: "wrong"})])
        with self.assertRaisesRegex(ImageEnsureError, "name conflict"):
            self.ensure(cloud)
        cloud = FakeCloud(images=[self.image(owner="other-project")])
        with self.assertRaisesRegex(ImageEnsureError, "owner"):
            self.ensure(cloud)
        cloud = FakeCloud(images=[self.image(region="OTHER")])
        with self.assertRaisesRegex(ImageEnsureError, "region"):
            self.ensure(cloud)
        cloud = FakeCloud(images=[self.image(checksum="wrong", hash_value="wrong")])
        with self.assertRaisesRegex(ImageEnsureError, "Glance checksum"):
            self.ensure(cloud)
        cloud = FakeCloud(images=[self.image(disk_format="raw")])
        with self.assertRaisesRegex(ImageEnsureError, "disk format"):
            self.ensure(cloud)

    def test_scope_must_resolve_to_the_requested_project_and_region(self):
        cloud = FakeCloud(project=None)
        with self.assertRaisesRegex(ImageEnsureError, "project ID"):
            self.ensure(cloud)
        cloud = FakeCloud(region="OTHER")
        with self.assertRaisesRegex(ImageEnsureError, "resolved 'OTHER'"):
            self.ensure(cloud)

    def test_non_active_and_failed_images_are_reported_without_deletion(self):
        cloud = FakeCloud(images=[self.image(status="ERROR")])
        with self.assertRaisesRegex(ImageEnsureError, "status ERROR"):
            self.ensure(cloud)
        self.assertEqual(cloud.uploads, [])
        cloud = FakeCloud(upload_status="ERROR")
        with redirect_stderr(StringIO()), self.assertRaisesRegex(ImageEnsureError, "created ID new-image"):
            self.ensure(cloud)
        self.assertEqual(len(cloud.images), 1)

    def test_pending_image_waits_until_active_or_timeout(self):
        cloud = FakeCloud(images=[self.image(status="queued")])
        active = self.image(status="ACTIVE")
        cloud.get_image = lambda image_id: active
        with patch("snakemake_executor_plugin_guix_openstack.image.time.sleep"):
            self.assertEqual(self.ensure(cloud), "existing-image")
        cloud = FakeCloud(images=[self.image(status="uploading")])
        with patch("snakemake_executor_plugin_guix_openstack.image.time.monotonic",
                   side_effect=[0, 0, 2]):
            with self.assertRaisesRegex(ImageEnsureError, "timed out"):
                self.ensure(cloud)

    def test_upload_exception_queries_for_lost_response_and_never_deletes(self):
        cloud = FakeCloud()
        cloud.upload_error = TimeoutError("response lost")
        with redirect_stderr(StringIO()), self.assertRaisesRegex(
                ImageEnsureError, "matching image record") as error:
            self.ensure(cloud)
        self.assertIn("openstack image delete new-image", str(error.exception))
        self.assertEqual(len(cloud.images), 1)
        self.assertEqual(len(cloud.uploads), 1)

    def test_quota_or_policy_rejection_is_reported_without_cleanup(self):
        cloud = FakeCloud()
        cloud.create_image = lambda **kwargs: (_ for _ in ()).throw(
            RuntimeError("image quota exceeded")
        )
        with redirect_stderr(StringIO()), self.assertRaisesRegex(ImageEnsureError, "quota exceeded"):
            self.ensure(cloud)
        self.assertEqual(cloud.images, [])

    def test_bad_qcow2_file_is_rejected_before_cloud_access(self):
        self.path.write_bytes(b"not qcow2")
        cloud = FakeCloud()
        with self.assertRaisesRegex(ImageEnsureError, "not qcow2"):
            self.ensure(cloud)
        self.assertEqual(cloud.uploads, [])

    def test_cli_prints_id_and_closes_cloud(self):
        cloud = FakeCloud(images=[self.image()])
        out, err = StringIO(), StringIO()
        with patch("snakemake_executor_plugin_guix_openstack.image.OpenStackCloud", return_value=cloud), \
                redirect_stdout(out), redirect_stderr(err):
            result = main(["ensure", "--file", str(self.path), "--region", "GRA11"])
        self.assertEqual(result, 0)
        self.assertEqual(out.getvalue().strip(), "existing-image")
        self.assertIn("project-id", err.getvalue())
        self.assertTrue(cloud.closed)

    def test_openstacksdk_460_create_image_contract(self):
        try:
            from openstack.image.v2._proxy import Proxy
        except ImportError:
            self.skipTest("openstacksdk is not available in this test environment")
        import inspect
        parameters = inspect.signature(Proxy.create_image).parameters
        for parameter in ("filename", "sha256", "md5", "disk_format", "container_format",
                          "allow_duplicates", "wait", "timeout", "validate_checksum"):
            self.assertIn(parameter, parameters)


if __name__ == "__main__":
    unittest.main()
