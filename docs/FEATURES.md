# Features & Workflows

## Dashboard Features

### Guild Configuration

Central admin panel for all guild settings. Organized in tabs:

**General Tab**
- Command prefix (1-10 chars, default `!`)
- Starboard channel ID (cross-post high-reaction messages)
- Star threshold (min reactions to post to starboard, default 3)

**AutoMod Tab**
Moderation automation with 4 toggleable detectors:
- **Anti-Invite**: Block messages containing Discord invite links
- **Anti-Spam**: Detect rapid message flooding (configurable threshold)
- **Anti-Caps**: Flag messages exceeding caps % threshold
- **Anti-Mention**: Block mass-mention spam (limit max mentions per message)

Numeric configs:
- Max mentions: 1-50 (default 5)
- Spam threshold: 2-20 messages per 5s window (default 5)
- Caps %: 10-100% threshold (default 70%)

**Welcome Tab**
Member join/leave messages with placeholders:
- {user} - User mention
- {username} - Display name
- {server} - Guild name
- {count} - Total member count

**Levels Tab**
XP leveling system toggle. When enabled, members earn XP from messages. Granular per-role config via `/level` slash command.

**Logging Tab**
Audit log channel. All mod actions (warns, notes, bans) post here with timestamp and executor.

### Forms (Application System)

Build custom application forms for member vetting.

**Workflow:**
1. Create form with custom questions
2. Members fill form via bot command `/form fill <form_id>`
3. Submission appears in Dashboard Forms tab
4. Admin reviews, approves/denies (triggers audit event)
5. Member receives approval/denial DM

**Features:**
- Multi-question support (text responses)
- Search submissions by user/text
- Approval/denial workflow with audit trail
- Pending apps KPI shows count in main dashboard

### Tickets

Support/issue tracking system.

**Workflow:**
1. User opens ticket via `!ticket create` command
2. Bot creates private channel with user + admins
3. User describes issue in channel
4. Admin resolves and runs `!ticket close <id>`
5. Channel archived, logged to audit

**Features:**
- Open/closed filtering
- Private channel per ticket (auto-named)
- Per-ticket discussion thread
- Close timestamp logged

### Audit Log

Real-time timeline of all moderation actions. Searchable, filterable, timezone-aware.

**Events Tracked:**
- `warning` - Warn issued via `!warn` command
- `note` - Admin note added via `!note` command
- `ticket-open` - Support ticket opened
- `ticket-close` - Support ticket closed
- `form-submit` - User submitted form
- `form-approved` - Admin approved form submission
- `form-denied` - Admin denied form submission

**Features:**
- Full-text search (by user ID, actor, detail text)
- Type filter chips (All, Warnings, Notes, Tickets, Submissions, Approved, Denied)
- Color-coded event types (rose for denials, mint for approvals, etc.)
- Timestamp shown in user's timezone (via JavaScript `toLocaleString()`)
- Sortable ascending/descending
- Hover shows full detail

**Access:**
- Admins: `/guild/<id>/audit` page
- Audit data: JSON API at `/api/guild/<id>/audit.json`

## Bot Features

### Moderation

**Warn System**
```
!warn @user [reason]
```
Issues formal warning. Logs to audit log as type=warning. Executor stored as actor.

**Notes**
```
!note @user [text]
```
Admin-only note attachment. No punishment, just record-keeping. Type=note audit event.

**AutoMod Detection**
Automatic responses (no command needed):
- Anti-spam: Message deleted + reaction
- Anti-caps: Message flagged with reaction
- Anti-invite: Message deleted + DM user policy
- Anti-mention: Message deleted if exceeds threshold

### Starboard

Cross-post popular messages. When emoji reaction count reaches threshold, bot reposts to starboard channel with original author credit.

**Config:**
```
!starboard #channel-name
!star_threshold 5
```

**Behavior:**
- Listens for configured emoji (default ⭐)
- Watches reaction count
- Auto-posts when threshold met
- Embeds original message, links to source
- Archives in starboard channel (permanent record of high-engagement posts)

### Member Lifecycle

**Join**
- Send configurable welcome message to join channel
- Log member join to audit channel with timestamp
- Trigger welcome DM if configured

**Leave**
- Send configurable goodbye message (notifies when member leaves)
- Log member leave with timestamp
- Clean up any open tickets (auto-archive)

### Leveling

**What it Does:**
- Track XP per member (1 XP per message)
- Award roles at level milestones
- Leaderboard command

**Per-Guild Config:**
```
/level enable
/level role-reward <role_id> <level>
/level blacklist #channel (no XP earned here)
/level rate-limit <msgs_per_minute> (stop XP abuse)
```

**Commands:**
```
!level                  -- Show your XP, level, progress
!leaderboard           -- Top 10 members by XP
!level info @user      -- Check another member's level
```

## Desktop Control Panel

Minimal UI for service status and restarts.

**Status Dashboard:**
- Bot online status (guild count)
- Dashboard uptime
- Desktop memory usage

**Actions:**
- Restart bot
- Restart dashboard
- Restart all services
- View logs

## Data Export

### Audit Export
```
GET /api/guild/<id>/audit.json?format=csv
```
Returns CSV with columns: timestamp, type, subject, actor, detail

### Form Submissions Export
```
GET /api/guild/<id>/forms/<id>/submissions.json?format=csv
```
Download all submissions for a form as CSV.

### Ticket Export
```
GET /api/guild/<id>/tickets/export.json
```
All tickets with transcript (channel messages).

## Advanced Workflows

### Whitelist Application Process

1. **Admin creates form:**
   ```
   !form create "Whitelist Application"
   Questions: "Why do you want to join?", "Experience level?"
   ```

2. **User submits:**
   ```
   !form fill <form_id>
   ```

3. **Form audit trail:**
   - Submission logged as form-submit event
   - ID, user ID, answers recorded

4. **Admin reviews:**
   - Dashboard /guild/<id>/forms tab
   - See all submissions pending

5. **Admin decision:**
   - Click Approve → form-approved event, DM user success message
   - Click Deny → form-denied event, DM user rejection message

### Incident Response

1. **Spam attack detected:**
   - AutoMod anti-spam triggers (rapid messages deleted)
   - `!warn @spammer Spam attack` → warning event
   - `!note @spammer Spam bots, IP range X.X.X.X` → note event

2. **Audit trail:**
   - All actions visible in /guild/<id>/audit
   - Timeline shows: detection → warning → note
   - Actor column shows who ran manual commands
   - Timestamp shows incident window

3. **Export for records:**
   - Export audit as CSV for records
   - Share with server team/stakeholders

### Member Support Escalation

1. **User opens ticket:**
   ```
   !ticket create
   ```
   Bot creates private channel for support conversation.

2. **Support conversation:**
   - User describes issue in channel
   - Admins discuss privately
   - Resolution discussed

3. **Closure:**
   ```
   !ticket close <ticket_id>
   ```
   - Channel archived
   - ticket-close audit event created
   - Timestamp recorded

4. **Audit record:**
   - Full conversation history in channel
   - Event timeline in audit log
   - Searchable by user/date

## Scalability

Current feature set supports:
- **Single guild** efficiently
- **Up to ~500 active members** with basic leveling/automod
- **~100 forms** per guild
- **~1000 audit events** before dashboard performance degrades

**To scale:**
- Migrate to PostgreSQL (replace SQLite)
- Add Redis for caching/rate-limit tracking
- Implement queue system (Celery) for bulk form processing
- Shard bot across multiple Discord.py instances
- Separate dashboard to dedicated server
