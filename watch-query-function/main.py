import os
import json
import logging
import psycopg2
from datetime import datetime, timedelta
from google.cloud import pubsub_v1
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def watch_query_function(request):
    """
    Cloud Run Function entry point for Gmail watch query
    Triggered by Cloud Scheduler via HTTP
    
    This function:
    1. Queries database for Gmail watches expiring within 2 hours
    2. Publishes renewal messages to Pub/Sub topic
    3. Returns operation summary
    """
    try:
        logger.info("Gmail watch query function triggered by Cloud Scheduler")
        
        # Get environment variables
        project_id = os.getenv('GCP_PROJECT_ID')
        topic_id = os.getenv('GCP_PUB_SUB_GMAIL_WATCH_RENEWAL_TOPIC_ID')
        database_url = os.getenv('DATABASE_URL')
        
        if not all([project_id, topic_id, database_url]):
            raise ValueError("Missing required environment variables")
        
        # Query expiring watches
        expiring_watches = get_expiring_watches(database_url)
        
        if not expiring_watches:
            logger.info("No expiring Gmail watches found")
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'success': True,
                    'message': 'No expiring watches found',
                    'watches_processed': 0
                })
            }
        
        # Publish renewal messages to Pub/Sub
        published_count = publish_renewal_messages(project_id, topic_id, expiring_watches)
        
        logger.info(f"Published {published_count} renewal messages")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'success': True,
                'message': f'Published {published_count} renewal messages',
                'watches_processed': published_count
            })
        }
        
    except Exception as e:
        logger.error(f"Error in watch query function: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'success': False,
                'error': str(e)
            })
        }

def get_expiring_watches(database_url, hours_ahead=2):
    """
    Query database for Gmail watches expiring within specified hours
    
    Args:
        database_url (str): PostgreSQL connection string
        hours_ahead (int): Hours ahead to check for expiring watches
    
    Returns:
        list: List of expiring watch records
    """
    try:
        # Calculate expiration threshold
        expiration_threshold = datetime.utcnow() + timedelta(hours=hours_ahead)
        
        # Connect to database
        conn = psycopg2.connect(database_url)
        cursor = conn.cursor()
        
        # Query for expiring watches
        query = """
        SELECT user_id, email, watch_id, expiration_time
        FROM gmail_watches 
        WHERE expiration_time <= %s 
        AND is_active = true
        ORDER BY expiration_time ASC
        """
        
        cursor.execute(query, (expiration_threshold,))
        watches = cursor.fetchall()
        
        # Convert to list of dictionaries
        watch_list = []
        for watch in watches:
            watch_list.append({
                'user_id': watch[0],
                'email': watch[1],
                'watch_id': watch[2],
                'expiration_time': watch[3].isoformat() if watch[3] else None
            })
        
        cursor.close()
        conn.close()
        
        logger.info(f"Found {len(watch_list)} expiring watches")
        return watch_list
        
    except Exception as e:
        logger.error(f"Database query error: {str(e)}")
        raise

def publish_renewal_messages(project_id, topic_id, watches):
    """
    Publish renewal messages to Pub/Sub topic
    
    Args:
        project_id (str): GCP project ID
        topic_id (str): Pub/Sub topic ID
        watches (list): List of expiring watches
    
    Returns:
        int: Number of messages published
    """
    try:
        publisher = pubsub_v1.PublisherClient()
        topic_path = publisher.topic_path(project_id, topic_id)
        
        published_count = 0
        
        for watch in watches:
            # Create renewal message
            message_data = {
                'user_id': watch['user_id'],
                'email': watch['email'],
                'watch_id': watch['watch_id'],
                'action': 'renew_watch',
                'timestamp': datetime.utcnow().isoformat()
            }
            
            # Publish message
            message_json = json.dumps(message_data)
            future = publisher.publish(topic_path, message_json.encode('utf-8'))
            
            # Wait for publish to complete
            message_id = future.result()
            logger.info(f"Published renewal message {message_id} for user {watch['user_id']}")
            
            published_count += 1
        
        return published_count
        
    except Exception as e:
        logger.error(f"Pub/Sub publish error: {str(e)}")
        raise

# Cloud Run entry point
if __name__ == "__main__":
    import functions_framework
    
    @functions_framework.http
    def main(request):
        return watch_query_function(request)