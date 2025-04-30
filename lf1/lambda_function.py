import json
import boto3
import json
import traceback
import requests
import os
import urllib.parse

rekognition_client = boto3.client('rekognition')
s3_client = boto3.client('s3')

def get_custom_labels(bucket, key):
    try:
        response = s3_client.head_object(Bucket=bucket, Key=key)
        print("s3 head object response:", response)
        
        if 'customlabels' in response['Metadata']:
            custom_labels = [label.strip().lower() for label in response['Metadata']['customlabels'].split(',')]
            print(f"Custom labels found: {custom_labels}")
            return custom_labels
        
        print("No custom labels found in metadata")
        return []
        
    except Exception as e:
        print(f"Error retrieving custom labels: {str(e)}")
        return []
        
def ingest_photo_to_es(object_key, bucket, timestamp, labels):

    es_host = os.environ['OS_URL']
    index_name = 'photos'
    url = f"{es_host}/{index_name}/_doc"
    print(f"Hitting ES url {url}")
    username = os.environ['OS_USERNAME']
    password = os.environ['OS_PASSWORD']
    headers = {
      'Content-Type': 'application/json'
    }
    
    photo_data = {
        "objectKey": object_key,
        "bucket": bucket,
        "createdTimestamp": timestamp,
        "labels": labels
    }

    ingestion_response = requests.post(url, auth=(username, password), data=json.dumps(photo_data), headers=headers)
    print("ES Index Response Log: ", json.dumps(ingestion_response.text))


def lambda_handler(event, context):
    
    print("request log: ", json.dumps(event))

    for record in event['Records']:
        bucket_name = record['s3']['bucket']['name']
        object_key = urllib.parse.unquote_plus(record['s3']['object']['key'])
        timestamp = record['eventTime']
        print("Obj timestamp --->", timestamp)
        
        try:
            custom_labels = get_custom_labels(bucket_name, object_key)

            response = rekognition_client.detect_labels(
                Image={
                    'S3Object': {
                        'Bucket': bucket_name,
                        'Name': object_key
                    }
                },
                MaxLabels=10 
            )
            
            print(f"Rekognition labels for {object_key}:")
            image_label_names = [label['Name'].lower() for label in response['Labels']]
            print(f"Image labels parsed --->", image_label_names )

            all_labels = list(set(image_label_names + custom_labels))
            print(f"Combined labels: {all_labels}")
            
            ingest_photo_to_es(object_key, bucket_name, timestamp, all_labels )
            
        
        except Exception as e:
            print(f"Error processing {object_key} from {bucket_name}: {traceback.format_exc()}")
            raise


    return {
        'statusCode': 200,
        'message': 'success'
    }
