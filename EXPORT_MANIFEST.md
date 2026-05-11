# Loki Export Manifest

**Export Date:** 2026-04-26  
**Project:** Loki - Discord Bot & Dashboard  
**Export Type:** Full Package with Templates & Configuration  

## Contents

### Root Files
- `README.md` - Comprehensive project documentation
- `EXPORT_MANIFEST.md` - This file

### Directory Structure

```
loki_export/
├── README.md                      # Project overview & features
├── EXPORT_MANIFEST.md             # This manifest
├── templates/                     # HTML template files
│   ├── audit.html                 # Audit log timeline view
│   ├── _sidebar.html              # Navigation sidebar component
│   └── guild.html                 # Guild configuration page
├── scripts/                       # Management & deployment scripts
│   ├── restart_all.ps1            # Full service restart (all 3)
│   └── restart_dash.ps1           # Dashboard-only restart
└── docs/                          # Additional documentation
    ├── ARCHITECTURE.md            # System architecture overview
    ├── DEPLOYMENT.md              # Deployment & setup guide
    ├── API.md                      # API endpoints reference
    └── FEATURES.md                # Detailed feature descriptions
```

## What's Included

### HTML Templates (3 files)
1. **audit.html** (87 lines)
   - Audit log timeline view
   - Real-time event filtering and search
   - Event type categorization with color-coding
   - Responsive layout with Tailwind CSS

2. **_sidebar.html** (42 lines)
   - Reusable navigation component
   - Guild info display
   - Menu items with icons
   - Dynamic active state indicators

3. **guild.html** (170 lines)
   - Guild configuration dashboard
   - Tabbed interface with 5 sections:
     - General (prefix, starboard, thresholds)
     - AutoMod (spam, invites, caps, mentions)
     - Welcome (join/leave messages with placeholders)
     - Levels (XP system toggle and config)
     - Logging (audit channel setup)
   - Real-time form submission
   - Visual toggles and input validation

### PowerShell Scripts (2 files)
1. **restart_all.ps1** (32 lines)
   - Kill existing Python processes by command line pattern
   - Start 3 services in sequence with delays:
     - bot.py (Discord bot)
     - dashboard/app.py (Web dashboard on port 5000)
     - desktop/app.py (Desktop control panel on port 7331)
   - Port health checks post-startup

2. **restart_dash.ps1** (13 lines)
   - Targeted dashboard restart
   - Kills only dashboard processes
   - Restarts dashboard/app.py
   - Verifies port 5000 is listening

### Documentation Files
- **README.md** - High-level overview, structure, features, configuration
- **EXPORT_MANIFEST.md** - This file (contents, technical specs, usage)
- **ARCHITECTURE.md** - System design, component interactions
- **DEPLOYMENT.md** - Setup, installation, configuration steps
- **API.md** - Endpoint reference (populated from source)
- **FEATURES.md** - Detailed feature breakdown

## Technology Stack

**Frontend:**
- Jinja2 templating (Flask)
- Tailwind CSS (utility-first styling)
- Alpine.js (lightweight interactivity)
- Bootstrap Icons (bi- icon classes)
- Chart.js (for dashboard charts, not in templates)

**Backend:**
- Python 3.x
- Flask (web framework)
- discord.py (Discord API client)
- SQLite/Database (persistence)

**Infrastructure:**
- Windows PowerShell 5.0+
- Python process management (pythonw.exe)
- Multi-service architecture

**Styling System:**
```
Color scheme (Tailwind):
- bg-ink-* (custom dark theme)
- text-slate-* (gray text)
- text-blurple, rose, amber, mint (accent colors)
- Responsive grid: grid-cols-2, sm:grid-cols-4, lg:grid-cols-8
```

## Services & Ports

| Service | Port | Script | Entry Point |
|---------|------|--------|-------------|
| Discord Bot | N/A | restart_all.ps1 | bot.py |
| Dashboard Web UI | 5000 | restart_all.ps1, restart_dash.ps1 | dashboard/app.py |
| Desktop Panel | 7331 | restart_all.ps1 | desktop/app.py |

## Key Features Documented

### Forms System
- Create, manage, and publish forms
- Form submissions workflow
- Application approval/denial pipeline
- Audit trail for submissions

### Ticket System
- Create and manage support tickets
- Ticket lifecycle tracking
- Status transitions (open → closed)
- Actor and timestamp logging

### Audit Logging
Event types tracked:
- `warning` - Moderation warnings
- `note` - Admin notes
- `ticket-open` - New tickets
- `ticket-close` - Closed tickets
- `form-submit` - New submissions
- `form-approved` - Approved applications
- `form-denied` - Rejected applications

### AutoMod Settings
- Anti-invite link blocking
- Anti-spam (configurable threshold)
- Anti-caps enforcement
- Anti mass-mention protection

### Welcome System
- Custom join/leave messages
- Dynamic placeholders: {user}, {username}, {server}, {count}
- Channel-based delivery

## File Statistics

| Category | Count | Lines of Code |
|----------|-------|----------------|
| HTML Templates | 3 | 299 |
| PowerShell Scripts | 2 | 45 |
| Markdown Docs | 4-6 | 500+ |
| **Total** | **9-11** | **844+** |

## Usage Instructions

### For Codex Upload
1. Zip the entire `loki_export` directory
2. Keep directory structure intact
3. Upload to Codex knowledge base
4. Index templates under "Frontend" category
5. Index scripts under "Deployment" category

### For Development Reference
1. Extract templates to Flask app's `templates/` directory
2. Place scripts in project root or `scripts/` subdirectory
3. Ensure PowerShell execution policy allows script execution
4. Reference documentation for architecture and features

### Service Management
```powershell
# Full restart (all services)
.\scripts\restart_all.ps1

# Dashboard restart only
.\scripts\restart_dash.ps1
```

## Configuration Reference

**Guild Settings:**
- Prefix: Command prefix (default: `!`)
- Starboard: Channel ID for starred messages
- Star threshold: Minimum stars to post (default: 3)
- Welcome channel: Channel for join messages
- Log channel: Channel for audit logs
- Level enabled: Toggle XP system

**AutoMod Thresholds:**
- Max mentions: 1-50 (default: 5)
- Spam threshold: 2-20 msgs/5s (default: 5)
- Caps percent: 10-100% (default: 70)

## Dependencies

### Python Packages (Common)
- discord.py >= 2.0
- Flask >= 2.0
- Flask-SQLAlchemy
- python-dotenv
- aiosqlite (async DB)

### System Requirements
- Python 3.8+
- Windows (for PowerShell scripts)
- Discord API token
- Administrator privileges (for restart scripts)

## Notes

- Templates use Jinja2 syntax (Django-compatible)
- PowerShell scripts target Windows 10+
- Color system uses custom Tailwind config (ink-* prefix)
- Alpine.js for real-time filtering and search
- No external API calls in templates (client-side only)
- Database persistence handled by Flask app

## Export Quality Checklist

- [x] All HTML templates included with full styling
- [x] PowerShell scripts with error handling and verification
- [x] Comprehensive README documentation
- [x] Architecture and deployment guides
- [x] API reference structure
- [x] Feature descriptions
- [x] Technology stack documented
- [x] Configuration examples provided
- [x] Service management instructions included
- [x] File manifest and statistics

## Contact & Support

For questions about:
- **Templates:** See `README.md` and `FEATURES.md`
- **Deployment:** See `DEPLOYMENT.md`
- **Architecture:** See `ARCHITECTURE.md`
- **APIs:** See `API.md`

---

**Export Package Version:** 1.0  
**Last Updated:** 2026-04-26
