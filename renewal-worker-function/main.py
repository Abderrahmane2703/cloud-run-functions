import os
import json
import logging
import base64
import psycopg2
from datetime import datetime
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def renewal_worker_function(event, context):
    """
    Cloud Run Function entry point for Gmail watch renewal worker
    Triggered by Pub/Sub messages from gmail-watch-renewal topic
    
    This function:
    1. Receives individual watch renewal request from Pub/Sub
    2. Calls Gmail API to renew the watch
    3. Updates database with new watch details
    """
    try:
        # Decode Pub/Sub message
        if 'data' not in event:
            logger.error("No data in Pub/Sub message")
            return
        
        message_data = base64.b64decode(event['data']).decode('utf-8')
        renewal_request = json.loads(message_data)
        
        logger.info(f"Processing Gmail watch renewal for user {renewal_request.get('user_id')} ({renewal_request.get('email')})")
        
        # Validate required fields
        required_fields = ['account_id', 'user_id', 'email', 'access_token', 'refresh_token']
        for field in required_fields:
            if field not in renewal_request:
                raise ValueError(f"Missing required field: {field}")
        
        # Renew Gmail watch
        renewal_result = renew_gmail_watch(
            renewal_request['access_token'],
            renewal_request['refresh_token']
        )
        
        if renewal_result.get('success'):
            # Update database with new watch details
            update_watch_in_database(
                renewal_request['account_id'],
                renewal_result['history_id'],
                renewal_result['expiration']
            )
            
            logger.info(f"Successfully renewed Gmail watch for user {renewal_request['user_id']}")
        else:
            logger.error(f"Failed to renew Gmail watch for user {renewal_request['user_id']}: {renewal_result.get('error')}")
            # Don't raise exception - let the message be acknowledged to avoid infinite retries
            # Log the error for monitoring
        
    except Exception as e:
        logger.error(f"Renewal worker function failed: {str(e)}")
        # Don't re-raise - acknowledge the message to prevent infinite retries
        # In production, you might want to send to a dead letter queue

def renew_gmail_watch(access_token, refresh_token):
    """
    Renew Gmail watch using the Gmail API
    """
    try:
        # Get environment variables
        project_id = os.getenv('GCP_PROJECT_ID')
        email_reply_topic = os.getenv('GCP_PUB_SUB_EMAIL_REPLY_TOPIC_ID')
        client_id = os.getenv('GOOGLE_CLIENT_ID')
        client_secret = os.getenv('GOOGLE_CLIENT_SECRET')
        
        # Check required variables (email_reply_topic is optional)
        if not all([project_id, client_id, client_secret]):
            raise ValueError("Missing required environment variables")
        
        # Create Gmail API client
        credentials = Credentials(
            token=access_token,
            refresh_token=refresh_token,
            token_uri="https://oauth2.googleapis.com/token",
            client_id=client_id,
            client_secret=client_secret,
            scopes=[
                'https://www.googleapis.com/auth/gmail.readonly',
                'https://www.googleapis.com/auth/gmail.send'
            ]
        )
        
        service = build('gmail', 'v1', credentials=credentials)
        
        # Setup watch request - only include topic if provided
        watch_request = {
            'labelIds': ['INBOX'],
            'labelFilterAction': 'include'
        }
        
        # Add topic only if email_reply_topic is provided
        if email_reply_topic:
            topic_name = f"projects/{project_id}/topics/{email_reply_topic}"
            watch_request['topicName'] = topic_name
            logger.info(f"Setting up Gmail watch with topic: {topic_name}")
        else:
            logger.info("Setting up Gmail watch without topic (expiration monitoring only)")
        
        # Call the Gmail API watch method
        result = service.users().watch(userId='me', body=watch_request).execute()
        
        logger.info(f"Gmail watch renewal successful: {result}")
        
        return {
            'success': True,
            'history_id': result.get('historyId'),
            'expiration': result.get('expiration')
        }
        
    except HttpError as e:
        logger.error(f"Gmail API error during renewal: {str(e)}")
        return {
            'success': False,
            'error': f"Gmail API error: {str(e)}"
        }
    except Exception as e:
        logger.error(f"Failed to renew Gmail watch: {str(e)}")
        return {
            'success': False,
            'error': f"Failed to renew Gmail watch: {str(e)}"
        }

def update_watch_in_database(account_id, history_id, expiration_ms):
    """
    Update Gmail watch details in the database
    """
    try:
        database_url = os.getenv('DATABASE_URL')
        if not database_url:
            raise ValueError("Missing DATABASE_URL environment variable")
        
        conn = psycopg2.connect(database_url)
        
        # Convert expiration from milliseconds to datetime
        expiration_dt = datetime.fromtimestamp(int(expiration_ms) / 1000)
        
        with conn.cursor() as cursor:
            cursor.execute(
                '''
                UPDATE gmail_mailbox_watches 
                SET 
                    history_id = %s,
                    watch_expiration = %s
                WHERE account_id = %s AND is_active = true
                ''',
                (history_id, expiration_dt, account_id)
            )
            
            if cursor.rowcount > 0:
                conn.commit()
                logger.info(f"Updated Gmail watch in database: account_id={account_id}, history_id={history_id}, expiration={expiration_dt}")
            else:
                logger.warning(f"No active Gmail watch found for account_id={account_id}")
        
    except Exception as e:
        logger.error(f"Failed to update watch in database: {str(e)}")
        raise
    finally:
        if 'conn' in locals():
            conn.close()

# Cloud Run entry point
if __name__ == "__main__":
    import functions_framework
    
    @functions_framework.cloud_event
    def main(cloud_event):
        return renewal_worker_function(cloud_event.data, cloud_event)