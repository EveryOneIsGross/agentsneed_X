#!/usr/bin/env python3
"""
Twitter CLI - Command line interface for Twitter API operations
Uses OAuth1Session for authentication and Twitter API v2 endpoints

example.env

```env
# Twitter API Credentials
TWITTER_API_KEY=
TWITTER_API_SECRET=
TWITTER_ACCESS_TOKEN=
TWITTER_ACCESS_TOKEN_SECRET=
TWITTER_BEARER_TOKEN=


# Customer / Client Credentials
TWITTER_CLIENT_ID=
TWITTER_CLIENT_SECRET=
```

"""

import argparse
from datetime import datetime
import json
import sys
import os
from typing import Optional, Dict, Any
from requests_oauthlib import OAuth1Session
from dotenv import load_dotenv
import time

class TwitterAuth:
    """Handle Twitter authentication with PIN-based OAuth flow and token caching"""
    def __init__(self):
        load_dotenv()
        self.consumer_key = os.getenv('TWITTER_API_KEY')
        self.consumer_secret = os.getenv('TWITTER_API_SECRET')
        self.token_cache_file = os.path.join(os.path.expanduser('~'), '.twitter_tokens.json')

        if not all([self.consumer_key, self.consumer_secret]):
            raise ValueError("Missing required Twitter API credentials in .env file")

    def _load_cached_tokens(self) -> tuple[str, str] | None:
        """Load cached tokens if they exist"""
        try:
            if os.path.exists(self.token_cache_file):
                with open(self.token_cache_file, 'r') as f:
                    tokens = json.load(f)
                return tokens.get('access_token'), tokens.get('access_token_secret')
        except Exception as e:
            print(f"Warning: Failed to load cached tokens: {e}")
        return None

    def _save_tokens(self, access_token: str, access_token_secret: str):
        """Save tokens to cache file"""
        try:
            with open(self.token_cache_file, 'w') as f:
                json.dump({
                    'access_token': access_token,
                    'access_token_secret': access_token_secret
                }, f)
        except Exception as e:
            print(f"Warning: Failed to cache tokens: {e}")

    def get_oauth(self) -> OAuth1Session:
        """Create OAuth1Session instance with PIN-based verification and caching"""
        cached_tokens = self._load_cached_tokens()
        if cached_tokens:
            access_token, access_token_secret = cached_tokens
            # Just create the session without validation
            return OAuth1Session(
                self.consumer_key,
                client_secret=self.consumer_secret,
                resource_owner_key=access_token,
                resource_owner_secret=access_token_secret
            )

        # If no cached tokens or they're invalid, do the full OAuth flow
        # Request token step
        request_token_url = "https://api.twitter.com/oauth/request_token?oauth_callback=oob&x_auth_access_type=write"
        oauth = OAuth1Session(self.consumer_key, client_secret=self.consumer_secret)
        
        try:
            fetch_response = oauth.fetch_request_token(request_token_url)
        except ValueError:
            raise ValueError("Failed to get request token. Check your API key and secret.")

        resource_owner_key = fetch_response.get("oauth_token")
        resource_owner_secret = fetch_response.get("oauth_token_secret")

        # Get authorization URL
        base_authorization_url = "https://api.twitter.com/oauth/authorize"
        authorization_url = oauth.authorization_url(base_authorization_url)
        print("\n🔑 Please go to this URL to authorize the application:")
        print(f"\n{authorization_url}\n")
        
        # Get PIN from user
        verifier = input("Enter the PIN from the website: ").strip()

        # Get access token
        access_token_url = "https://api.twitter.com/oauth/access_token"
        oauth = OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=resource_owner_key,
            resource_owner_secret=resource_owner_secret,
            verifier=verifier
        )

        oauth_tokens = oauth.fetch_access_token(access_token_url)
        access_token = oauth_tokens["oauth_token"]
        access_token_secret = oauth_tokens["oauth_token_secret"]

        # Cache the tokens
        self._save_tokens(access_token, access_token_secret)
        print("✅ Authentication tokens cached for future use")

        # Create final OAuth session
        return OAuth1Session(
            self.consumer_key,
            client_secret=self.consumer_secret,
            resource_owner_key=access_token,
            resource_owner_secret=access_token_secret
        )

class TwitterAPI:
    """Twitter API wrapper with support for media uploads, replies, and likes"""
    def __init__(self):
        self.auth = TwitterAuth()
        self.oauth = self.auth.get_oauth()
        self.api_base = "https://api.twitter.com/2"

    def _make_request(self, method: str, endpoint: str, **kwargs) -> Dict[str, Any]:
        """Make API request with error handling and rate limiting"""
        url = f"{self.api_base}/{endpoint}"
        try:
            # Add default headers if not present
            if 'headers' not in kwargs:
                kwargs['headers'] = {}
            kwargs['headers'].update({
                "User-Agent": "v2TwitterPython"
            })
            
            response = getattr(self.oauth, method)(url, **kwargs)
            
            # Handle rate limiting
            if response.status_code == 429:
                reset_time = int(response.headers.get('x-rate-limit-reset', 0))
                current_time = int(datetime.now().timestamp())
                sleep_time = max(reset_time - current_time, 0)
                
                if sleep_time > 0:
                    print(f"Rate limited. Waiting {sleep_time} seconds...")
                    time.sleep(sleep_time)
                    # Retry the request
                    return self._make_request(method, endpoint, **kwargs)
            
            # Add more detailed error handling for API v2 specific errors
            if response.status_code != 200:
                error_data = response.json()
                if 'errors' in error_data:
                    return {"error": error_data['errors'][0]['message']}
                elif 'error' in error_data:
                    return {"error": error_data['error']['message']}
                return {"error": f"API returned status code {response.status_code}: {response.text}"}
                
            response.raise_for_status()
            return response.json()
        except Exception as e:
            return {"error": str(e)}

    def upload_media(self, media_path: str) -> Dict[str, Any]:
        """Upload media to Twitter"""
        try:
            # Twitter v1.1 API endpoint for media upload
            url = "https://upload.twitter.com/1.1/media/upload.json"
            
            # Read file in binary mode
            with open(media_path, 'rb') as file:
                files = {'media': file}
                response = self.oauth.post(url, files=files)
                response.raise_for_status()
                return {"media_id": response.json()['media_id_str']}
        except Exception as e:
            return {"error": str(e)}

    def create_tweet(self, text: str, media_path: Optional[str] = None, reply_to_id: Optional[str] = None) -> Dict[str, Any]:
        """Create a new tweet, optionally with media or as a reply"""
        if len(text) > 280:
            return {"error": "Tweet exceeds 280 character limit"}
        
        payload = {"text": text}
        
        # Add media if provided
        if media_path:
            if not os.path.exists(media_path):
                return {"error": f"Media file not found: {media_path}"}
                
            # Check file size (Twitter limit is 5MB for images, 15MB for videos)
            file_size = os.path.getsize(media_path)
            if file_size > 15 * 1024 * 1024:  # 15MB
                return {"error": "Media file exceeds maximum size limit"}
                
            media_result = self.upload_media(media_path)
            if "error" in media_result:
                return media_result
            payload["media"] = {"media_ids": [media_result["media_id"]]}
        
        # Add reply information if provided
        if reply_to_id:
            payload["reply"] = {"in_reply_to_tweet_id": reply_to_id}
        
        return self._make_request(
            "post",
            "tweets",
            json=payload
        )

    def like_tweet(self, tweet_id: str) -> Dict[str, Any]:
        """Like a tweet"""
        payload = {"tweet_id": tweet_id}
        return self._make_request(
            "post",
            f"users/{self.get_my_user_id()}/likes",
            json=payload
        )

    def unlike_tweet(self, tweet_id: str) -> Dict[str, Any]:
        """Unlike a tweet"""
        return self._make_request(
            "delete",
            f"users/{self.get_my_user_id()}/likes/{tweet_id}"
        )

    def get_my_user_id(self) -> str:
        """Get the authenticated user's ID"""
        result = self._make_request("get", "users/me")
        if "error" in result:
            raise ValueError(f"Failed to get user ID: {result['error']}")
        return result["data"]["id"]

    def get_user_info(self, username: str) -> Dict[str, Any]:
        """Get user information"""
        params = {
            "user.fields": "created_at,description,public_metrics,verified,location,url,profile_image_url,entities,pinned_tweet_id"
        }
        return self._make_request(
            "get",
            f"users/by/username/{username}",
            params=params
        )

    def get_user_tweets(self, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get user's tweets"""
        params = {
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics",
            "expansions": "author_id"
        }
        return self._make_request(
            "get",
            f"users/{user_id}/tweets",
            params=params
        )

    def search_tweets(self, query: str, limit: int = 10) -> Dict[str, Any]:
        """Search recent tweets"""
        params = {
            "query": query,
            "max_results": min(limit, 100),
            "tweet.fields": "created_at,public_metrics,author_id,text,context_annotations,entities,geo,lang,referenced_tweets",
            "expansions": "author_id,referenced_tweets.id,attachments.media_keys,entities.mentions.username",
            "user.fields": "username,name,verified,profile_image_url",
            "media.fields": "type,url,preview_image_url"
        }
        
        return self._make_request(
            "get",
            "tweets/search/recent",
            params=params
        )

    def get_user_followers(self, user_id: str, limit: int = 10) -> Dict[str, Any]:
        """Get user's followers with pagination support"""
        params = {
            "max_results": min(limit, 100),
            "user.fields": "created_at,description,public_metrics,verified,location,url",
            "expansions": "pinned_tweet_id",
            "tweet.fields": "created_at,public_metrics"
        }

        # Add proper headers for API v2
        headers = {
            "User-Agent": "v2FollowersLookupPython"
        }

        return self._make_request(
            "get",
            f"users/{user_id}/followers",
            params=params,
            headers=headers
        )

    def get_tweet(self, tweet_id: str) -> Dict[str, Any]:
        """Get a single tweet by ID"""
        params = {
            "tweet.fields": "created_at,public_metrics,author_id,text"
        }
        return self._make_request(
            "get",
            f"tweets/{tweet_id}",
            params=params
        )

def format_tweet(tweet: Dict[str, Any]) -> str:
    """Format a tweet for display"""
    created_at = tweet.get("created_at", "Unknown date")
    metrics = tweet.get("public_metrics", {})
    
    return (
        f"\n🐦 Tweet ID: {tweet.get('id')}\n"
        f"👤 Author ID: {tweet.get('author_id')}\n"
        f"📅 Created: {created_at}\n"
        f"📝 Text: {tweet.get('text')}\n"
        f"📊 Metrics: {json.dumps(metrics, indent=2)}\n"
        f"{'-' * 50}"
    )

def format_user(user: Dict[str, Any]) -> str:
    """Format a user for display"""
    metrics = user.get("public_metrics", {})
    created_at = user.get("created_at", "Unknown date")
    
    return (
        f"\n👤 User: @{user.get('username')}\n"
        f"📛 Name: {user.get('name')}\n"
        f"🆔 ID: {user.get('id')}\n"
        f"📅 Joined: {created_at}\n"
        f"📊 Metrics: {json.dumps(metrics, indent=2)}\n"
        f"{'-' * 50}"
    )

def setup_argparse() -> argparse.ArgumentParser:
    """Setup command line argument parsing"""
    parser = argparse.ArgumentParser(
        description='Twitter CLI Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Commands')

    # Add reset-cache command
    reset_cache_parser = subparsers.add_parser('reset-cache', help='Reset cached authentication tokens')

    # User info command
    user_parser = subparsers.add_parser('user', help='Get user information')
    user_parser.add_argument('username', help='Twitter username')

    # Tweets command
    tweets_parser = subparsers.add_parser('tweets', help='Get user tweets')
    tweets_parser.add_argument('username', help='Twitter username')
    tweets_parser.add_argument('--limit', type=int, default=10, help='Number of tweets to retrieve')

    # Search command
    search_parser = subparsers.add_parser('search', help='Search tweets')
    search_parser.add_argument('query', help='Search query')
    search_parser.add_argument('--limit', type=int, default=10, help='Number of tweets to retrieve')

    # Followers command
    followers_parser = subparsers.add_parser('followers', help='Get user followers')
    followers_parser.add_argument('username', help='Twitter username')
    followers_parser.add_argument('--limit', type=int, default=10, help='Number of followers to retrieve')

    # Post command
    post_parser = subparsers.add_parser('post', help='Create a new tweet')
    post_parser.add_argument('text', help='Tweet text (max 280 characters)')
    post_parser.add_argument('--media', help='Path to media file to upload with tweet')
    post_parser.add_argument('--reply-to', help='Tweet ID to reply to')

    # Like/Unlike commands
    like_parser = subparsers.add_parser('like', help='Like a tweet')
    like_parser.add_argument('tweet_id', help='ID of tweet to like')

    unlike_parser = subparsers.add_parser('unlike', help='Unlike a tweet')
    unlike_parser.add_argument('tweet_id', help='ID of tweet to unlike')

    return parser

def main():
    parser = setup_argparse()
    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return

    try:
        if args.command == 'reset-cache':
            auth = TwitterAuth()
            if os.path.exists(auth.token_cache_file):
                os.remove(auth.token_cache_file)
                print("✅ Authentication cache cleared successfully")
            else:
                print("ℹ️ No cache file found")
            return

        twitter = TwitterAPI()
        
        if args.command == 'user':
            result = twitter.get_user_info(args.username)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(format_user(result['data']))

        elif args.command == 'tweets':
            # First get user ID
            user_result = twitter.get_user_info(args.username)
            if 'error' in user_result:
                print(f"❌ Error: {user_result['error']}")
                return
                
            user_id = user_result['data']['id']
            result = twitter.get_user_tweets(user_id, args.limit)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                for tweet in result.get('data', []):
                    print(format_tweet(tweet))

        elif args.command == 'search':
            result = twitter.search_tweets(args.query, args.limit)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                if not result.get('data'):
                    print(f"No tweets found for query: {args.query}")
                    return
                print(f"Found {len(result['data'])} tweets:")
                for tweet in result.get('data', []):
                    print(format_tweet(tweet))

        elif args.command == 'followers':
            # First get user ID
            user_result = twitter.get_user_info(args.username)
            if 'error' in user_result:
                print(f"❌ Error getting user info: {user_result['error']}")
                if '403' in str(user_result['error']):
                    print("💡 Tip: This may be due to protected tweets or API access level restrictions")
                return
                
            user_id = user_result['data']['id']
            result = twitter.get_user_followers(user_id, args.limit)
            if 'error' in result:
                print(f"❌ Error getting followers: {result['error']}")
                if '403' in str(result['error']):
                    print("💡 Tip: This may be due to protected tweets or API access level restrictions")
            else:
                if not result.get('data'):
                    print(f"No followers found for user: {args.username}")
                    return
                print(f"Found {len(result['data'])} followers:")
                for follower in result.get('data', []):
                    print(format_user(follower))
                
                # Show pagination info if available
                meta = result.get('meta', {})
                if meta.get('next_token'):
                    print(f"\nℹ️ More followers available. Use --limit to retrieve more.")

        elif args.command == 'post':
            result = twitter.create_tweet(
                text=args.text,
                media_path=args.media,
                reply_to_id=args.reply_to
            )
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                tweet_id = result['data']['id']
                tweet = twitter.get_tweet(tweet_id)
                if 'error' in tweet:
                    print(f"✅ Tweet posted with ID: {tweet_id}")
                else:
                    print(format_tweet(tweet['data']))

        elif args.command == 'like':
            result = twitter.like_tweet(args.tweet_id)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Successfully liked tweet: {args.tweet_id}")

        elif args.command == 'unlike':
            result = twitter.unlike_tweet(args.tweet_id)
            if 'error' in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"✅ Successfully unliked tweet: {args.tweet_id}")

    except KeyboardInterrupt:
        print("\n👋 Goodbye!")
        sys.exit(0)
    except Exception as e:
        print(f"❌ An error occurred: {str(e)}")
        sys.exit(1)

if __name__ == "__main__":
    main()