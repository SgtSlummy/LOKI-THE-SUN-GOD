# CodeRabbit Review Flow

CodeRabbit is part of the LOKI quality gate, but it is not authenticated in this local environment by default.

1. Authenticate:

```bash
coderabbit auth login --agent
```

2. Run local checks first:

```bash
python -m pytest
python -m compileall .
```

3. Ask CodeRabbit to review the branch or pull request after the GitHub repo exists.

Do not treat manual review output as CodeRabbit output. If authentication is missing, record that CodeRabbit review is blocked.
