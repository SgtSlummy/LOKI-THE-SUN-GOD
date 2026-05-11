# Loki System Architecture

## High-Level Overview

Loki is a three-tier Discord bot ecosystem with integrated web dashboard and desktop control panel.

```
┌─────────────────────────────────────────────────────────┐
│                   Discord Guild                         │
│  (Members, Channels, Roles, Messages, Reactions)        │
└────────────────┬────────────────────────────────────────┘
                 │
                 │ discord.py
                 │
┌────────────────▼────────────────────────────────────────┐
│              Discord Bot (bot.py)                        │
│  • Event listeners (messages, reactions, joins)         │
│  • Command handlers                                     │
│  • Database persistence                                 │
│  • Audit logging                                        │
└────┬──────────┬──────────────────┬─────────────────────┘
     │          │                  │
     │          │                  │
┌────▼──┐  ┌────▼─────┐  ┌────────▼────────┐
│ Forms │  │ Tickets  │  │ Events/Streams  │
│ Mgmt  │  │ System   │  │ Tracking        │
└──┬────┘  └────┬─────┘  └────┬────────────┘
   │            │             │
   └────────┬───┴──────┬──────┘
            │          │
            │ Database (SQLite/SQL)
            │
┌───────────┴──────────────────────────────────┐
│                                               │
│  ┌──────────────────────────────────────┐   │
│  │    Web Dashboard (Flask)             │   │
│  │    Port: 5000                        │   │
│  │  • Guild configuration               │   │
│  │  • Forms & submissions               │   │
│  │  • Ticket management                 │   │
│  │  • Audit log viewer                  │   │
│  │  • AutoMod settings                  │   │
│  └──────────────────────────────────────┘   │
│                                               │
│  ┌──────────────────────────────────────┐   │
│  │  Desktop Control Panel (desktop.py)  │   │
│  │    Port: 7331                        │   │
│  │  • Service monitoring                │   │
│  │  • Emergency controls                │   │
│  │  • System status                     │   │
│  └──────────────────────────────────────┘   │
│                                               │
└───────────────────────────────────────────────┘
```

## Component Architecture

### 1. Discord Bot (Core)
- **File:** `bot.py`
- **Role:** Primary Discord integration
- **Responsibilities:**
  - Listen to Discord events
  - Execute commands
  - Track guild activity
  - Manage warnings and notes
  - Emit events to dashboard

**Key Components:**
- Event handlers (on_ready, on_message, on_member_join, on_reaction_add)
- Command framework (slash commands, prefix commands)
- Database abstraction layer
- Audit logger

### 2. Web Dashboard (Flask)
- **File:** `dashboard/app.py`
- **Port:** 5000
- **Role:** Administrative interface for guild management

**Routes (inferred from templates):**
```
GET  /guilds                     # List user's guilds
GET  /guild/<id>                 # Guild configuration page
POST /guild/<id>/save            # Save config changes
GET  /guild/<id>/embed           # Embed builder
GET  /guild/<id>/forms           # Forms management
GET  /guild/<id>/tickets         # Tickets management
GET  /guild/<id>/events          # Events calendar
GET  /guild/<id>/streams         # Stream tracking
GET  /guild/<id>/audit           # Audit log viewer
```

**Templates Provided:**
- `base.html` - Master layout
- `_sidebar.html` - Navigation sidebar
- `guild.html` - Configuration dashboard
- `audit.html` - Audit log timeline

### 3. Desktop Control Panel
- **File:** `desktop/app.py`
- **Port:** 7331
- **Role:** Local system administration

**Functions:**
- Service health monitoring
- Process restart control
- System status dashboard

## Data Flow Patterns

### Guild Configuration Update
```
User Browser
    ↓
POST /guild/<id>/save (Flask)
    ↓
Validate input
    ↓
Database UPDATE
    ↓
Return confirmation
    ↓
User Browser (redirect to /guild/<id>)
```

### Form Submission
```
Discord User (reaction/modal)
    ↓
bot.py event handler
    ↓
Database INSERT (forms table)
    ↓
Audit log: form-submit
    ↓
Dashboard notification (real-time or page refresh)
    ↓
Admin views in /guild/<id>/forms
    ↓
Admin approves/denies
    ↓
Bot sends DM to user
    ↓
Audit log: form-approved/form-denied
```

### Ticket Lifecycle
```
User creates ticket
    ↓
bot.py handles command
    ↓
Database INSERT (ticket)
    ↓
Create channel
    ↓
Audit log: ticket-open
    ↓
Admin manages in /guild/<id>/tickets
    ↓
Admin closes
    ↓
bot.py closes channel
    ↓
Database UPDATE (ticket.closed = true)
    ↓
Audit log: ticket-close
```

## Database Schema (Inferred)

### Core Tables
```sql
guilds
  id (SNOWFLAKE/PRIMARY)
  config (JSON: prefix, starboard_channel, welcome_channel, etc.)
  automod (JSON: anti_spam, anti_caps, anti_mention settings)
  created_at
  updated_at

audit_logs
  id (AUTOINCREMENT/PRIMARY)
  guild_id (FOREIGN KEY)
  type (warning|note|ticket-open|ticket-close|form-submit|form-approved|form-denied)
  subject (user ID or entity)
  actor (mod ID)
  detail (text)
  timestamp

forms
  id (AUTOINCREMENT/PRIMARY)
  guild_id
  name
  status (draft|active|archived)
  submissions (count)
  created_at

form_submissions
  id (AUTOINCREMENT/PRIMARY)
  form_id
  user_id
  data (JSON)
  status (pending|approved|denied)
  submitted_at
  reviewed_by
  reviewed_at

tickets
  id (AUTOINCREMENT/PRIMARY)
  guild_id
  channel_id
  user_id
  status (open|closed)
  created_at
  closed_at

events
  id (AUTOINCREMENT/PRIMARY)
  guild_id
  name
  date
  reminder_enabled

streams
  id (AUTOINCREMENT/PRIMARY)
  guild_id
  user_id
  url
  active (bool)
  created_at
```

## Service Orchestration

### Startup Sequence
1. `restart_all.ps1` executes
2. Kill matching Python processes (cleanup)
3. Wait 2 seconds
4. Start `bot.py` (service 1, no port required)
5. Wait 1 second
6. Start `dashboard/app.py` (service 2, port 5000)
7. Wait 1 second
8. Start `desktop/app.py` (service 3, port 7331)
9. Wait 6 seconds
10. Health check ports 5000 and 7331
11. Report status

### Process Management
```
pythonw bot.py
  → Daemonized (no console)
  → Maintains Discord connection
  → Processes events indefinitely

pythonw dashboard/app.py
  → Flask development or production server
  → Listens on 0.0.0.0:5000
  → Serves HTTP requests

pythonw desktop/app.py
  → Desktop environment-specific
  → Listens on 0.0.0.0:7331
  → System tray or window
```

## Authentication & Authorization

**Discord OAuth (inferred):**
- Dashboard likely uses Discord OAuth for user authentication
- Users must own or have admin role in guild to configure it

**Permission Model:**
```
Guild Owner
  └─ Full access to all features

Server Admin (role-based)
  └─ Access to guild configuration
  └─ Access to mod tools
  └─ View audit logs

Members
  └─ Submit forms
  └─ Create tickets
  └─ Receive warnings/notes

Bot
  └─ Service account
  └─ All Discord operations
```

## Audit Logging Architecture

**Events Logged:**
- Warnings issued (actor, target, detail)
- Notes added (actor, target, text)
- Ticket operations (open/close with timestamps)
- Form submissions (user, form ID, data)
- Form decisions (reviewer, user, decision)

**Audit Trail Access:**
- Members: Limited (own submissions)
- Mods: Full view via `/guild/<id>/audit`
- API: Queryable by type, date range, actor

**Real-time Features:**
- Filters by event type
- Full-text search (user ID, message content)
- Timestamp conversion to local timezone
- Color-coded event types

## Configuration Management

**Guild Config Storage:**
```json
{
  "prefix": "!",
  "starboard_channel": 123456789,
  "star_threshold": 3,
  "welcome_channel": 987654321,
  "welcome_msg": "Welcome {user}!",
  "goodbye_msg": "Bye {username}",
  "log_channel": 111222333,
  "level_enabled": true,
  "automod": {
    "anti_invite": true,
    "anti_spam": true,
    "spam_threshold": 5,
    "anti_caps": true,
    "caps_percent": 70,
    "anti_mention": true,
    "max_mentions": 5
  }
}
```

**Configuration Sources:**
- Defaults (hardcoded in app)
- Database (guild-specific overrides)
- Environment (API tokens, secrets)
- Admin UI (guild configuration form)

## Scalability Considerations

### Current Architecture (Single Guild)
- Single SQLite database file
- Bot runs as single process
- Dashboard serves one user at a time (dev mode)

### For Production Scaling
1. **Database:** Migrate to PostgreSQL/MySQL
2. **Cache:** Redis for session data, frequently accessed config
3. **Workers:** Celery for async tasks (form processing, notifications)
4. **Load Balancing:** Multiple dashboard instances
5. **Sharding:** Discord.py sharding for 10k+ guilds

## Security Considerations

1. **API Token Security:**
   - Discord token in environment variable
   - Database credentials in .env file
   - No secrets in code

2. **Input Validation:**
   - Form inputs sanitized before DB
   - Discord ID validation
   - Channel ID range checks

3. **CSRF Protection:**
   - Flask session-based (inferred)
   - Form tokens on POST requests

4. **SQL Injection:**
   - Parameterized queries (SQLAlchemy ORM)
   - No string concatenation in queries

5. **Access Control:**
   - Guild ownership verification
   - Role-based permission checks
   - Audit logging of admin actions

---

**Architecture Version:** 1.0  
**Last Updated:** 2026-04-26
