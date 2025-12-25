import os
import json
import requests
from google.auth.transport.requests import Request
from google.auth import load_credentials_from_dict
from googleapiclient.discovery import build

def get_google_creds():
    """Build Google credentials using Workload Identity Federation (AWS → GCP)."""
    project_number = os.environ["GOOGLE_PROJECT_NUMBER"]
    pool_id = os.environ["GOOGLE_POOL_ID"]
    provider_id = os.environ["GOOGLE_PROVIDER_ID"]
    service_account_email = os.environ["SERVICE_ACCOUNT_EMAIL"]

    audience = (
        f"//iam.googleapis.com/projects/{project_number}/"
        f"locations/global/workloadIdentityPools/{pool_id}/providers/{provider_id}"
    )

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

    creds, _ = load_credentials_from_dict(
        external_account_config,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )
    creds.refresh(Request())
    return creds

def fetch_canvas_assignments():
    """Fetch assignments from Canvas for the configured course IDs."""
    base_url = os.environ["CANVAS_BASE_URL"].rstrip("/")
    token = os.environ["CANVAS_TOKEN"]
    course_ids = [
        c.strip() for c in os.environ["COURSE_IDS"].split(",") if c.strip()
    ]

    headers = {"Authorization": f"Bearer {token}"}
    all_rows = []

    # Header row for RawAssignments sheet
    header = [
        "course_id",
        "course_name",
        "assignment_id",
        "assignment_name",
        "due_at",
        "points_possible",
        "html_url",
    ]
    all_rows.append(header)

    for course_id in course_ids:
        # Fetch course details to get course name
        course_resp = requests.get(
            f"{base_url}/api/v1/courses/{course_id}",
            headers=headers,
            timeout=15,
        )
        course_resp.raise_for_status()
        course = course_resp.json()
        course_name = course.get("name", f"Course {course_id}")

        # Fetch assignments with pagination
        url = f"{base_url}/api/v1/courses/{course_id}/assignments"
        params = {"per_page": 100}

        while url:
            resp = requests.get(url, headers=headers, params=params, timeout=30)
            resp.raise_for_status()
            assignments = resp.json()

            for a in assignments:
                all_rows.append([
                    str(course_id),
                    course_name,
                    str(a.get("id", "")),
                    a.get("name", ""),
                    a.get("due_at", ""),
                    a.get("points_possible", ""),
                    a.get("html_url", ""),
                ])

            # Pagination: next link
            # After first request, params should not be reused (URL already has them)
            params = None
            url = resp.links.get("next", {}).get("url")

    return all_rows

def lambda_handler(event, context):
    print("Lambda handler started")

    spreadsheet_id = os.environ["SPREADSHEET_ID"]

    # 1) Get Canvas assignments into rows
    print("Fetching Canvas assignments...")
    rows = fetch_canvas_assignments()
    print(f"Fetched {len(rows) - 1} assignments (plus header)")

    # 2) Get Google creds via WIF
    print("Getting Google credentials...")
    creds = get_google_creds()
    print("Google credentials ready")

    # 3) Build Sheets client
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    # 4) Overwrite RawAssignments!A1 with fresh data
    print("Writing to RawAssignments!A1")
    body = {"values": rows}
    result = sheet.values().update(
        spreadsheetId=spreadsheet_id,
        range="RawAssignments!A1",
        valueInputOption="RAW",
        body=body,
    ).execute()

    print("Sheets API update result:", json.dumps(result))
    print("Lambda handler finished")

    return {
        "statusCode": 200,
        "body": json.dumps(
            {"rows_written": len(rows), "assignments": len(rows) - 1}
        ),
    }
