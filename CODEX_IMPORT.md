# Codex Import Guide

This package is ready for upload to Codex knowledge base system.

## Package Contents

**Archive:** `loki_export.zip` (24 KB)

**File Structure:**
```
loki_export/
├── README.md                    # Project overview
├── EXPORT_MANIFEST.md           # Detailed file manifest
├── CODEX_IMPORT.md             # This file
│
├── templates/                   # Flask Jinja2 templates
│   ├── audit.html              # Audit log timeline UI
│   ├── _sidebar.html           # Reusable nav component
│   └── guild.html              # Guild config dashboard
│
├── scripts/                     # PowerShell service management
│   ├── restart_all.ps1         # Master restart script
│   └── restart_dash.ps1        # Dashboard-only restart
│
└── docs/                        # Comprehensive documentation
    ├── ARCHITECTURE.md         # System design, DB schema, data flows
    ├── DEPLOYMENT.md           # Setup, configuration, troubleshooting
    ├── API.md                  # Endpoint reference (Flask + Discord.py)
    └── FEATURES.md             # Detailed feature descriptions & workflows
```

## Upload Instructions

### Option 1: Direct Upload
1. Download `loki_export.zip` from Desktop
2. In Codex, select "Import Knowledge Base" or "Upload Package"
3. Choose zip file → import
4. Codex auto-extracts directory structure

### Option 2: Folder Import
1. Extract zip to a folder
2. In Codex, select "Add Knowledge Folder"
3. Point to extracted `loki_export/` directory

## Codex Integration Points

### For Semantic Search
Key documents index well:
- **ARCHITECTURE.md** - Database schema, service interaction, data flows
- **FEATURES.md** - Audit log, forms, automod, tickets workflows
- **API.md** - All REST endpoints, Discord commands, event types

Tag suggestions in Codex:
- `discord-bot`, `flask-dashboard`, `python`
- `audit-logging`, `form-submissions`, `automod`
- `sqlite`, `jinja2`, `alpine.js`
- `service-orchestration`, `windows-powershell`

### Useful Codex Queries

Once imported, ask Codex:
- "How does audit logging work?"
- "What are all the form submission states?"
- "Show me the AutoMod configuration options"
- "What database tables does Loki use?"
- "How do I deploy Loki?"
- "What Discord events does the bot listen for?"
- "How is the dashboard organized?"

## File Roles in Codex

| File | Purpose | Search Queries |
|------|---------|-----------------|
| README.md | Quick overview, project summary | "What is Loki?", "Project structure" |
| ARCHITECTURE.md | Deep technical context | "Database schema", "How does data flow?", "Service architecture" |
| API.md | Endpoint/command reference | "API endpoints", "Discord commands", "Form submission endpoint" |
| DEPLOYMENT.md | Setup & troubleshooting | "How to deploy?", "Port configuration", "Database setup" |
| FEATURES.md | Feature workflows & examples | "How do forms work?", "Audit log features", "Whitelist workflow" |
| Templates | UI/layout reference | "Dashboard layout", "Sidebar navigation", "Audit timeline HTML" |
| Scripts | Service management | "Service restart", "Process management", "Port health check" |

## Codex-Specific Tips

### Markdown Formatting
All docs use standard markdown:
- Headers (# ## ###) for structure
- Code blocks with language tags (```python, ```sql)
- Tables for schemas and comparison
- Bullet lists for configuration options

Codex will parse these automatically for indexing.

### Code Examples
Look for embedded:
- SQL CREATE TABLE statements (ARCHITECTURE.md)
- JSON config structure (DEPLOYMENT.md, FEATURES.md)
- PowerShell scripts (scripts/ folder)
- Flask route examples (API.md)
- HTML template fragments (templates/)

All are searchable in Codex's code index.

### Cross-References
Docs link together:
- README → ARCHITECTURE → DEPLOYMENT
- README → API → FEATURES
- DEPLOYMENT → ARCHITECTURE (database schema)
- FEATURES → API (endpoint workflows)

Codex will maintain these relationships for better context.

## Quality Checklist

✅ All templates included (3 files)
✅ All scripts included (2 files)
✅ Comprehensive documentation (4 docs)
✅ Proper markdown formatting
✅ Code examples with syntax highlighting
✅ Database schema documented
✅ All API endpoints listed
✅ Feature workflows explained
✅ Deployment guide provided
✅ Architecture diagram (text) included
✅ Troubleshooting section added
✅ File manifest included

## Version Info

- **Export Date:** April 26, 2026
- **Loki Version:** Single-guild deployment
- **Technology Stack:** Python 3.9+, Discord.py, Flask, SQLite, Jinja2, Tailwind CSS, Alpine.js
- **Architecture:** Three services (Bot, Dashboard, Desktop)
- **Services:** 2 HTTP (ports 5000, 7331), 1 Discord connection

## Support

For questions about Loki functionality:
- See DEPLOYMENT.md for setup issues
- See API.md for endpoint details
- See FEATURES.md for workflow descriptions
- See ARCHITECTURE.md for system design
- See troubleshooting sections in each doc

---

**Ready to import. All files present. Codex will automatically index documentation and make it searchable.**
