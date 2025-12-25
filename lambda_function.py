import os
import json
from google.auth.transport.requests import Request
from google.auth import load_credentials_from_dict
from googleapiclient.discovery import build

def lambda_handler(event, context):
    print("Lambda handler started")

    project_number = os.environ["GOOGLE_PROJECT_NUMBER"]
    pool_id = os.environ["GOOGLE_POOL_ID"]
    provider_id = os.environ["GOOGLE_PROVIDER_ID"]
    service_account_email = os.environ["SERVICE_ACCOUNT_EMAIL"]
    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    print("Env vars loaded")
    print(f"Project number: {project_number}, pool_id: {pool_id}, provider_id: {provider_id}")
    print(f"Service account: {service_account_email}")
    print(f"Spreadsheet ID: {spreadsheet_id}")

    audience = (
        f"//iam.googleapis.com/projects/{project_number}/"
        f"locations/global/workloadIdentityPools/{pool_id}/providers/{provider_id}"
    )
    print(f"Audience: {audience}")

    external_account_config = {
        "type": "external_account",
        "audience": audience,
        "subject_token_type": "urn:ietf:params:aws:token-type:aws4_request",
        "token_url": "https://sts.googleapis.com/v1/token",
        "service_account_impersonation_url": (
            "https://iamcredentials.googleapis.com/v1/projects/-/"
            f"serviceAccounts/{service_account_email}:generateAccessToken"
        ),
        "credential_source": {
            "environment_id": "aws1",
            "region_url": "http://169.254.169.254/latest/meta-data/placement/availability-zone",
            "url": "http://169.254.169.254/latest/meta-data/iam/security-credentials",
            "regional_cred_verification_url": (
                "https://sts.{region}.amazonaws.com"
                "?Action=GetCallerIdentity&Version=2011-06-15"
            ),
        },
    }

    print("External account config built")

    creds, _ = load_credentials_from_dict(
        external_account_config,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    print("Credentials object created, refreshing...")
    creds.refresh(Request())
    print("Credentials refreshed")

    print("Building Sheets client")
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    print("Calling Sheets API to update Test!A1")
    body = {"values": [["Lambda via Workload Identity Federation 🎉 FROM PyCharm"]]}
    result = sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range="Test!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()

    print("Sheets API result:", json.dumps(result))
    print("Lambda handler finished")

    return {"statusCode": 200, "body": "ok"}
