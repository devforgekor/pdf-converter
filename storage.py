"""
OCI Object Storage 연동

참조 소스:
- Oracle Cloud Infrastructure Python SDK: https://github.com/oracle/oci-python-sdk
- Object Storage 예제: https://github.com/oracle/oci-python-sdk/blob/master/examples/object_storage/
- PAR(Pre-Authenticated Request) 문서: https://docs.oracle.com/en-us/iaas/Content/Object/Tasks/usingpreauthenticatedrequests.htm
"""
import os
import oci
from datetime import datetime, timedelta
from typing import Optional


class ObjectStorage:
    def __init__(self):
        self._client = None
        self._namespace = None
        self._bucket = os.getenv("OCI_BUCKET", "kuhwa-file-storage")

    def _get_client(self):
        if self._client is None:
            # 인스턴스 자격증(Instance Principals) 사용 — 서버에 OCI API 키를 두지 않는다.
            # 전제: dynamic group `kuhwa-instance`
            #       + policy `kuhwa-instance-principals` (manage object-family in tenancy)
            self._signer = oci.auth.signers.InstancePrincipalsSecurityTokenSigner()
            self.config = {"region": self._signer.region}
            self._client = oci.object_storage.ObjectStorageClient(
                config={}, signer=self._signer, region=self._signer.region
            )
        return self._client

    def _get_namespace(self):
        if self._namespace is None:
            self._namespace = self._get_client().get_namespace().data
        return self._namespace

    @property
    def client(self):
        return self._get_client()

    @property
    def namespace(self):
        return self._get_namespace()

    @property
    def bucket(self):
        return self._bucket

    def upload_file(self, object_name: str, content: bytes, content_type: str = "application/octet-stream") -> str:
        self.client.put_object(
            namespace_name=self.namespace,
            bucket_name=self.bucket,
            object_name=object_name,
            put_object_body=content,
            content_type=content_type,
        )
        return object_name

    def download_file(self, object_name: str) -> bytes:
        response = self.client.get_object(
            namespace_name=self.namespace,
            bucket_name=self.bucket,
            object_name=object_name,
        )
        return response.data.content

    def delete_file(self, object_name: str):
        try:
            self.client.delete_object(
                namespace_name=self.namespace,
                bucket_name=self.bucket,
                object_name=object_name,
            )
        except oci.exceptions.ServiceError:
            pass

    def get_par_url(self, object_name: str, expires_in_hours: int = 24) -> str:
        par = self.client.create_preauthenticated_request(
            namespace_name=self.namespace,
            bucket_name=self.bucket,
            create_preauthenticated_request_details=oci.object_storage.models.CreatePreauthenticatedRequestDetails(
                name=f"download-{object_name}",
                access_type="ObjectRead",
                object_name=object_name,
                time_expires=datetime.utcnow() + timedelta(hours=expires_in_hours),
            ),
        )
        region = self.config["region"]
        return f"https://objectstorage.{region}.oraclecloud.com{par.data.access_uri}"

    def file_exists(self, object_name: str) -> bool:
        try:
            self.client.head_object(
                namespace_name=self.namespace,
                bucket_name=self.bucket,
                object_name=object_name,
            )
            return True
        except oci.exceptions.ServiceError:
            return False


storage = ObjectStorage()
