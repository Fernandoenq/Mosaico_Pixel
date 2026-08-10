import boto3
import os
import json
from dotenv import load_dotenv

load_dotenv()

bucket_name = os.getenv("S3_BUCKET")
if not bucket_name:
    print("S3_BUCKET not found")
    exit(1)

try:
    s3 = boto3.client(
        "s3",
        aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
        aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
        region_name=os.getenv("AWS_REGION"),
    )
    res = s3.list_objects_v2(Bucket=bucket_name)
    if 'Contents' in res:
        print(f"Success, found {len(res['Contents'])} items.")
    else:
        print("Success, but no contents.")
except Exception as e:
    print(f"Error: {e}")
