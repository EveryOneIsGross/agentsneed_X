![image](https://github.com/user-attachments/assets/0af0645c-1021-45ee-9a6e-8fb0a8207f91)

# Twitter API CLI Interface

A command-line interface for Twitter API v2 operations using OAuth1 authentication.

## Core Architecture

1. **Authentication (TwitterAuth)**
   - Handles OAuth1 flow with PIN verification
   - Implements token caching for persistence
   - Clear separation between auth and API operations

2. **API Layer (TwitterAPI)**
   - Central request handler with rate limiting
   - Unified error management
   - Media handling support

## Key Operations Flow

```
Authentication → API Operations → Data Formatting → CLI Output
```

```shell
# User information
twitter_cli.py user <username>

# Post tweet
twitter_cli.py post "Hello Twitter" --media image.jpg

# Search tweets
twitter_cli.py search "python" --limit 10

# Engagement
twitter_cli.py like <tweet_id>
twitter_cli.py unlike <tweet_id>
```

## Rate Management
- Built-in rate limit detection
- Automatic retry mechanism
- Window-based throttling

## Command Structure
```python
CLI Commands
├── User Management
│   ├── user (profile info)
│   └── followers
├── Content Operations
│   ├── post (with media support)
│   ├── search
│   └── tweets
└── Engagement
    ├── like
    └── unlike
```

## TODO
1. Add pagination support
2. Implement async operations
3. Add batch operation capability

---

![image](https://github.com/user-attachments/assets/51cc9863-a650-4bce-afbd-7a3fefc6e2d6)

# Autonomous X Agent Architecture

## System Overview
Scratch code for a autonomous agent that manages social media actions based on `needs` (engagement, reach, etc.) while respecting rate limits.

## Core Components
1. **XAgent**: Main controller
   - Analyzes context, decides actions, executes
   - Manages Xenvironment state and interactions

2. **XEnvironment**: State manager
   - Tracks needs and metrics
   - Manages available actions
   - Updates based on outcomes

3. **Decision Engine**: Action selector
   - Prioritizes actions by need
   - Considers rate limits and utility
   - Sorts execution queue

## Rate Limits
- **Content (24h window)**:
  - 17 tweets/replies total
  
- **Engagement (15m window)**:
  - 1 action per window (likes, retweets)
  
- **Analysis (15m window)**:
  - 1 context scan
  - 3 user lookups
  - 25 metric collections/24h

## Need States
```python
ENGAGEMENT: 50% decay/cycle
REACH:     30% decay/cycle
RELEVANCE: 20% decay/cycle
AUTHORITY: 10% decay/cycle
CONVERSION: 40% decay/cycle
```

## Action Flow
```
1. XAgent analyzes context
2. XEnvironment updates needs
3. Decision engine selects action
4. Rate limits checked
5. Action executed
6. State updated
```

## Key Relationships
- XAgent controls XEnvironment
- XEnvironment manages Needs and Actions
- Decision Engine prioritizes based on Needs
- Rate Manager controls execution timing
