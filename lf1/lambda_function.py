import json
import boto3
import base64
import os
import requests
import datetime

s3_client = boto3.client('s3')
rekognition_client = boto3.client('rekognition')

def lambda_handler(event, context):
    print("Event received:", json.dumps(event))
    
    # Extract path param for image key
    object_key = event["pathParameters"]["object"]
    print("Uploading object key:", object_key)
    
    # Decode base64 image content
    image_data = base64.b64decode(event["body"])
    
    # Optional custom labels
    custom_labels = []
    if "headers" in event and "x-amz-meta-customlabels" in event["headers"]:
        custom_labels = [label.strip().lower() for label in event["headers"]["x-amz-meta-customlabels"].split(",")]
    print("Custom labels from header:", custom_labels)

    # Upload to S3
    bucket = "photo-album-frontend-2025"
    s3_client.put_object(
        Bucket=bucket,
        Key=object_key,
        Body=image_data,
        ContentType="image/png",
        Metadata={"customlabels": ",".join(custom_labels)}
    )
    print(f"Uploaded {object_key} to {bucket}")

    # Run Rekognition on uploaded image
    rekognition_response = rekognition_client.detect_labels(
        Image={"S3Object": {"Bucket": bucket, "Name": object_key}},
        MaxLabels=10
    )
    
    rekognition_labels = [label["Name"].lower() for label in rekognition_response["Labels"]]
    print("Rekognition labels:", rekognition_labels)

    # Combine custom and Rekognition labels
    combined_labels = list(set(rekognition_labels + custom_labels))
    print("All combined labels:", combined_labels)

    # Build document for OpenSearch
    doc = {
        "objectKey": object_key,
        "bucket": bucket,
        "createdTimestamp": datetime.datetime.utcnow().isoformat(),
        "labels": combined_labels
    }

    # Index into OpenSearch
    es_url = os.environ["OS_URL"]
    es_username = os.environ["OS_USERNAME"]
    es_password = os.environ["OS_PASSWORD"]
    index_url = f"{es_url}/photos/_doc"

    headers = {"Content-Type": "application/json"}
    es_response = requests.post(index_url, auth=(es_username, es_password), json=doc, headers=headers)
    
    print("OpenSearch index response:", es_response.status_code, es_response.text)

    return {
        "statusCode": 200,
        "body": json.dumps({"message": f"Successfully uploaded and indexed {object_key}"})
    }
