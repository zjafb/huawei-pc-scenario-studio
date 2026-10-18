"""Read-only local readiness check. Never displays credentials or calls APIs."""
from __future__ import annotations

import json
import os
import sys
from io import BytesIO
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from PIL import Image
from app.images import select_images
from app.whitelist import Task, build_fact_pool
from app import catalog


def configured(names, service, filename):
    return any(os.environ.get(n, "").strip() for n in names) or bool(
        (Path.home() / ".config" / service / filename).is_file()
        and (Path.home() / ".config" / service / filename).read_text(encoding="utf-8").strip())


def main():
    credentials = {
        "model_token": configured(("MODELSCOPE_API_KEY", "MODELSCOPE_TOKEN"), "modelscope", "api_key"),
        "model_id": configured(("MODELSCOPE_MODEL",), "modelscope", "model_id"),
        "ima_client_id": configured(("IMA_OPENAPI_CLIENTID", "IMA_CLIENT_ID"), "ima", "client_id"),
        "ima_key": configured(("IMA_OPENAPI_APIKEY", "IMA_API_KEY"), "ima", "api_key"),
    }
    products=catalog.products();image_hashes=set();source_count=0
    for product in products:
        source_count+=bool(catalog.facts_for(product))
        for asset in catalog.assets_for(product):
            raw,digest=catalog.read_verified(asset['file'])
            if digest!=asset['sha256']:raise ValueError('Image review pin does not match original.')
            with Image.open(BytesIO(raw)) as picture:picture.verify()
            image_hashes.add(digest)
    result = {"credential_presence_only": credentials,"products":len(products),
              "complete_profiles":sum(p['level']=='specification' for p in products),
              "discovery_profiles":sum(p['level']=='discovery' for p in products),
              "verified_source_documents":source_count,"verified_image_originals":len(image_hashes),
              "cache_generation_ready": credentials["model_token"] and credentials["model_id"]
              and bool(products) and source_count==len(products),
              "network_requests": 0, "remote_freshness": "unverified", "cloud_deployment": "unverified"}
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["cache_generation_ready"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
