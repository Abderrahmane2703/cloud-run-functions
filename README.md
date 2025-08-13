# Cloud Run Functions

This directory contains Cloud Run functions for the Email Sender application.

## Functions

### 1. Watch Query Function
**Path:** `watch-query-function/`
**Purpose:** Queries the database for Gmail watches that are expiring within 2 hours and publishes renewal messages to Pub/Sub.

**Environment Variables Required:**
- `GCP_PROJECT_ID`: Your Google Cloud Project ID
- `GCP_PUB_SUB_GMAIL_WATCH_RENEWAL_TOPIC_ID`: Pub/Sub topic ID for Gmail watch renewals
- `DATABASE_URL`: PostgreSQL database connection string

### 2. Renewal Worker Function
**Path:** `renewal-worker-function/`
**Purpose:** Processes individual Gmail watch renewal requests from Pub/Sub, calls Gmail API to renew watches, and updates the database.

**Environment Variables Required:**
- `GCP_PROJECT_ID`: Your Google Cloud Project ID
- `GCP_PUB_SUB_EMAIL_REPLY_TOPIC_ID`: Pub/Sub topic ID for email replies
- `DATABASE_URL`: PostgreSQL database connection string
- `GOOGLE_CLIENT_ID`: Google OAuth2 client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth2 client secret

## Deployment

### Automatic Deployment via GitHub Actions

The functions are automatically deployed when:
1. Code is pushed to the `main` branch
2. Changes are made to files in the `cloud-run-functions/` directory
3. Manual workflow dispatch is triggered

### Required GitHub Secrets

Set up the following secrets in your GitHub repository:

- `GCP_SA_KEY`: Google Cloud Service Account key (JSON format)
- `GCP_PROJECT_ID`: Your Google Cloud Project ID
- `GCP_PUB_SUB_GMAIL_WATCH_RENEWAL_TOPIC_ID`: Pub/Sub topic for watch renewals
- `GCP_PUB_SUB_EMAIL_REPLY_TOPIC_ID`: Pub/Sub topic for email replies
- `DATABASE_URL`: PostgreSQL database connection string
- `GOOGLE_CLIENT_ID`: Google OAuth2 client ID
- `GOOGLE_CLIENT_SECRET`: Google OAuth2 client secret

### Manual Deployment

You can also deploy manually using the gcloud CLI:

```bash
# Deploy Watch Query Function
gcloud run deploy watch-query-function \
  --source=./cloud-run-functions/watch-query-function \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=your-project-id,GCP_PUB_SUB_GMAIL_WATCH_RENEWAL_TOPIC_ID=your-topic-id,DATABASE_URL=your-database-url"

# Deploy Renewal Worker Function
gcloud run deploy renewal-worker-function \
  --source=./cloud-run-functions/renewal-worker-function \
  --region=us-central1 \
  --platform=managed \
  --allow-unauthenticated \
  --set-env-vars="GCP_PROJECT_ID=your-project-id,GCP_PUB_SUB_EMAIL_REPLY_TOPIC_ID=your-topic-id,DATABASE_URL=your-database-url,GOOGLE_CLIENT_ID=your-client-id,GOOGLE_CLIENT_SECRET=your-client-secret"
```

## Testing

### Watch Query Function
Test the function by making a GET request:
```bash
curl https://watch-query-function-[hash]-uc.a.run.app
```

### Renewal Worker Function
This function is triggered by Pub/Sub messages and doesn't have a direct HTTP endpoint for testing.

## Monitoring

Monitor the functions in the Google Cloud Console:
1. Go to Cloud Run
2. Select your function
3. Check the Logs tab for execution details
4. Monitor metrics in the Metrics tab

## Architecture

```
Cloud Scheduler → Watch Query Function → Pub/Sub Topic → Renewal Worker Function → Gmail API
                                    ↓                                      ↓
                              Database Query                        Database Update
```

1. **Cloud Scheduler** triggers the Watch Query Function periodically
2. **Watch Query Function** queries the database for expiring Gmail watches
3. For each expiring watch, it publishes a message to the **Pub/Sub Topic**
4. **Renewal Worker Function** processes each message from Pub/Sub
5. **Renewal Worker Function** calls the Gmail API to renew the watch
6. **Renewal Worker Function** updates the database with new watch details