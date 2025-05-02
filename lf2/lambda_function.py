import json
import os
import requests
import traceback
import boto3
import uuid

s3_client = boto3.client('s3')
lex_client = boto3.client('lexv2-runtime')
BOT_ID = 'F5Y9URYTJS'
BOT_ALIAS_ID = 'TSTALIASID'
LOCALE_ID = 'en_US'


def search_elasticsearch(query_string):
    print("query string: ", query_string)
    es_host = os.environ['OS_URL']
    index = 'photos'
    url = f"{es_host}/{index}/_search"
    username = os.environ['OS_USERNAME']
    password = os.environ['OS_PASSWORD']
    headers = {
        'Content-Type': 'application/json'
    }
    keywords = query_string
    # query = {
    #     "query": {
    #         "bool": {
    #             "should": [
    #                 {"match": {"labels": {"query": keyword, "fuzziness": "AUTO"}}}
    #                 for keyword in keywords
    #             ]
    #         }
    #     }
    # }
    query = {
      "query": {
        "bool": {
          "should": [
            { "match": { "labels": keyword } }
            for keyword in keywords
          ],
          # at least one should‐clause must match:
          "minimum_should_match": 1
        }
      }
    }

    print("ES Query ---> ", query)


  
    try:
       
        response = requests.get(url, auth=(username, password), headers=headers, data=json.dumps(query))
        print("es helper: raw response: ", response.text)

        results = []
        for hit in response.json()['hits']['hits']:
     
            results.append(generate_presigned_url(hit['_source']['bucket'], hit['_source']['objectKey']))

        return results

    except Exception as e:
        print("Error querying OpenSearch: ", traceback.format_exc())
        return []


def invoke_lex(user_prompt):
    """Invoke Lex to extract keywords from SearchIntent."""
    if not user_prompt:
        return []
        
    try:
        response = lex_client.recognize_text(
            botId=BOT_ID,
            botAliasId=BOT_ALIAS_ID,
            localeId=LOCALE_ID,
            sessionId=str(uuid.uuid4()),
            text=user_prompt
        )
        
        print("Lex Response:", json.dumps(response, indent=2))
        
        keywords = []
        if ('interpretations' in response and 
            len(response['interpretations']) > 0 and 
            'intent' in response['interpretations'][0]):
            
            intent = response['interpretations'][0]['intent']
            
            if intent['name'] == 'SearchIntent':
                slots = intent.get('slots', {})

                if (slots.get('Labels') and 
                    slots['Labels'].get('value') and 
                    slots['Labels']['value'].get('interpretedValue')):
                    keywords.append(slots['Labels']['value']['interpretedValue'].lower())
                
                if (slots.get('AdditionalKeyword') and 
                    slots['AdditionalKeyword'] and  
                    slots['AdditionalKeyword'].get('value') and 
                    slots['AdditionalKeyword']['value'].get('interpretedValue')):
                    keywords.append(slots['AdditionalKeyword']['value']['interpretedValue'].lower())
        
        print(f"Extracted keywords from SearchIntent: {keywords}")
        return keywords
        
    except Exception as e:
        print(f"Error invoking Lex: {str(e)}")
        print(traceback.format_exc())
        return []


def generate_presigned_url(bucket_name, object_key, expiration=3600):
    url = s3_client.generate_presigned_url(
        'get_object',
        Params={'Bucket': bucket_name, 'Key': object_key},
        ExpiresIn=expiration
    )
    return url

def lambda_handler(event, context):
    headers = {
        'Content-Type': 'application/json',
        'Access-Control-Allow-Origin': '*', 
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Methods': 'GET,OPTIONS'
    }

    try:
        print("Request log: ", json.dumps(event))

        query_params = event.get("queryStringParameters") or {}
        search_prompt = query_params.get('q')
        print("query params: ", query_params)
        print("search prompt: ", search_prompt)


        if not search_prompt:
            return {
                "statusCode": 400,
                "headers": headers,
                "body": json.dumps({
                    "message": "Missing search query",
                    "image_urls": []
                })
            }

        keywords = invoke_lex(search_prompt)
        print("Extracted keywords --->", keywords)

        es_results = search_elasticsearch(keywords)
        print("es_results: ", es_results)

        if not es_results:
            return {
                "statusCode": 200,
                "headers": headers,
                "body": json.dumps({
                    "message": "No matching images found",
                    "image_urls": []
                })
            }

        return {
            "statusCode": 200,
            "headers": headers,
            "body": json.dumps({
                "message": "success",
                "image_urls": es_results
            })
        }

    except Exception as e:
        print(f"Error in lambda_handler: {str(e)}")
        print(traceback.format_exc())
        return {
            "statusCode": 500,
            "headers": headers,
            "body": json.dumps({
                "message": "Internal server error",
                "image_urls": []
            })
        }
